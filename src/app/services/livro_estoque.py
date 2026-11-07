from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, aliased

from app.database.locais_perda import fora_da_perda
from app.database.models import (
    Empresa,
    EstoqueEmpresaLocalLote,
    MovimentoEstoque,
    MovimentoEstoqueDia,
    NotaMovimento,
    Produto,
)
from app.dominio.intervalo import Intervalo
from app.dominio.operacoes_estoque import CATALOGO, VERSAO_LIVRO, Categoria, cois_que_afetam
from app.services.estoque import descricao_item
from app.services.notas_empresa_errada import condicao_empresa_errada

LIMITE_EXTRATO = 1000


def afeta(coi: int) -> bool | None:
    for saida in (True, False):
        if (saida, coi) in CATALOGO:
            return CATALOGO[(saida, coi)].afeta
    return None


def dias_sem_leitura(db: Session, empresa_id: int, periodo: Intervalo) -> list[date]:
    lidos = set(
        db.scalars(
            select(MovimentoEstoqueDia.dia).where(
                MovimentoEstoqueDia.empresa_id == empresa_id,
                MovimentoEstoqueDia.dia.between(periodo.inicio, periodo.fim),
                MovimentoEstoqueDia.versao >= VERSAO_LIVRO,
            )
        )
    )
    faltam = []
    dia = periodo.inicio
    while dia <= periodo.fim:
        if dia not in lidos:
            faltam.append(dia)
        dia += timedelta(days=1)
    return faltam


def empresas_ativas(db: Session) -> list[Empresa]:
    return list(db.scalars(select(Empresa).where(Empresa.ativo.is_(True))))


@dataclass(frozen=True)
class LinhaLivro:
    empresa: Empresa
    coi: int
    operacao: str | None
    categoria: Categoria
    afeta: bool | None
    documentos: int
    itens: int
    valor: Decimal | None


def resumo_livro(
    db: Session,
    periodo: Intervalo,
    empresa: Empresa | None = None,
    categoria: Categoria | None = None,
) -> list[LinhaLivro]:
    m = MovimentoEstoque
    consulta = (
        select(
            m.empresa_id,
            m.coi,
            func.max(m.operacao),
            func.max(m.tipo),
            func.count(func.distinct(m.id_planilha)),
            func.count(),
            func.sum(m.valor),
        )
        .where(m.dia.between(periodo.inicio, periodo.fim))
        .group_by(m.empresa_id, m.coi)
    )
    if empresa is not None:
        consulta = consulta.where(m.empresa_id == empresa.id)
    if categoria is not None:
        consulta = consulta.where(m.tipo == categoria)
    linhas = db.execute(consulta).all()
    empresas = {
        e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_({x[0] for x in linhas})))
    }
    resultado = [
        LinhaLivro(
            empresa=empresas[empresa_id],
            coi=coi,
            operacao=(nome or "").strip() or None,
            categoria=cast(Categoria, categoria),
            afeta=afeta(coi),
            documentos=documentos,
            itens=itens,
            valor=valor,
        )
        for empresa_id, coi, nome, categoria, documentos, itens, valor in linhas
    ]
    resultado.sort(key=lambda x: (len(x.empresa.codigo), x.empresa.codigo, x.coi))
    return resultado


@dataclass(frozen=True)
class FiltrosNotas:
    periodo: Intervalo
    empresa: Empresa | None = None
    categoria: Categoria | None = None
    coi: int | None = None

    empresa_errada: bool = False


@dataclass(frozen=True)
class NotaLivro:
    empresa: Empresa
    id_planilha: str
    dia: date
    coi: int
    operacao: str | None
    categoria: Categoria
    afeta: bool | None
    itens: int
    valor: Decimal | None
    numero: str | None
    momento: datetime | None
    usuario: str | None
    destinatario: str | None = None

    destino_empresa: str | None = None
    empresa_errada: bool = False


@dataclass(frozen=True)
class PaginaNotas:
    total: int
    notas: Sequence[NotaLivro]


@dataclass(frozen=True)
class ItemDaNota:
    movimento: MovimentoEstoque
    descricao: str | None


def _condicoes_notas(f: FiltrosNotas) -> list[ColumnElement[bool]]:
    m = MovimentoEstoque
    condicoes: list[ColumnElement[bool]] = [m.dia.between(f.periodo.inicio, f.periodo.fim)]
    if f.empresa is not None:
        condicoes.append(m.empresa_id == f.empresa.id)
    if f.categoria is not None:
        condicoes.append(m.tipo == f.categoria)
    if f.coi is not None:
        condicoes.append(m.coi == f.coi)
    return condicoes


def listar_notas(db: Session, f: FiltrosNotas, *, pagina: int, tamanho_pagina: int) -> PaginaNotas:
    m = MovimentoEstoque
    n = NotaMovimento
    condicoes = _condicoes_notas(f)
    documentos = (
        select(
            m.empresa_id,
            m.id_planilha,
            func.max(m.dia).label("dia"),
            func.min(m.coi).label("coi"),
            func.max(m.operacao).label("operacao"),
            func.max(m.tipo).label("tipo"),
            func.count().label("itens"),
            func.sum(m.valor).label("valor"),
        )
        .where(*condicoes)
        .group_by(m.empresa_id, m.id_planilha)
        .subquery()
    )
    destino = aliased(Empresa)
    destino_empresa = (
        select(destino.codigo)
        .where(destino.cnpj == n.cnpj_destinatario, destino.id != n.empresa_id)
        .limit(1)
        .scalar_subquery()
    )
    errada = condicao_empresa_errada(documentos.c.tipo, n)
    juncao = (n.empresa_id == documentos.c.empresa_id) & (n.id_planilha == documentos.c.id_planilha)
    filtro_errada = [errada] if f.empresa_errada else []
    total = (
        db.scalar(
            select(func.count()).select_from(documentos).outerjoin(n, juncao).where(*filtro_errada)
        )
        or 0
    )
    linhas = db.execute(
        select(
            documentos,
            n.numero,
            n.momento,
            n.usuario,
            n.nome_destinatario,
            destino_empresa.label("destino_empresa"),
            func.coalesce(errada, False).label("empresa_errada"),
        )
        .outerjoin(n, juncao)
        .where(*filtro_errada)
        .order_by(
            documentos.c.dia.desc(),
            n.momento.desc().nulls_last(),
            func.length(documentos.c.id_planilha).desc(),
            documentos.c.id_planilha.desc(),
            documentos.c.empresa_id,
        )
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    empresas = {
        e.id: e
        for e in db.scalars(select(Empresa).where(Empresa.id.in_({x.empresa_id for x in linhas})))
    }
    return PaginaNotas(
        total=total,
        notas=[
            NotaLivro(
                empresa=empresas[x.empresa_id],
                id_planilha=x.id_planilha,
                dia=x.dia,
                coi=x.coi,
                operacao=(x.operacao or "").strip() or None,
                categoria=cast(Categoria, x.tipo),
                afeta=afeta(x.coi),
                itens=x.itens,
                valor=x.valor,
                numero=x.numero,
                momento=x.momento,
                usuario=(x.usuario or "").strip() or None,
                destinatario=(x.nome_destinatario or "").strip() or None,
                destino_empresa=x.destino_empresa,
                empresa_errada=x.empresa_errada,
            )
            for x in linhas
        ],
    )


def itens_da_nota(db: Session, empresa: Empresa, id_planilha: str) -> list[ItemDaNota]:
    m = MovimentoEstoque
    linhas = db.execute(
        select(m, func.coalesce(m.descricao_produto, descricao_item()))
        .outerjoin(
            Produto,
            (Produto.id_produto == m.id_produto) & (Produto.id_subproduto == m.id_subproduto),
        )
        .where(m.empresa_id == empresa.id, m.id_planilha == id_planilha)
        .order_by(func.length(m.sequencia), m.sequencia, m.id)
    ).all()
    return [ItemDaNota(mov, desc) for mov, desc in linhas]


@dataclass(frozen=True)
class LinhaExtrato:
    movimento: MovimentoEstoque
    afeta: bool | None

    saldo_fim_dia: Decimal | None


@dataclass(frozen=True)
class TotalCategoria:
    categoria: Categoria
    afeta: bool | None
    itens: int
    quantidade: Decimal


@dataclass(frozen=True)
class Extrato:
    empresa: Empresa
    periodo: Intervalo
    saldo_atual: Decimal | None

    saldo_inicial: Decimal | None

    saldo_final: Decimal | None
    entradas: Decimal
    saidas: Decimal
    por_categoria: Sequence[TotalCategoria]
    itens: Sequence[LinhaExtrato]
    total_itens: int

    dias_sem_leitura: Sequence[date]


def extrato(
    db: Session,
    empresa: Empresa,
    id_produto: str,
    id_subproduto: str,
    periodo: Intervalo,
    hoje: date,
) -> Extrato:
    e = EstoqueEmpresaLocalLote
    saldo_atual = db.scalar(
        select(func.sum(e.saldo_atual)).where(
            e.empresa_id == empresa.id,
            e.id_produto == id_produto,
            e.id_subproduto == id_subproduto,
            e.ativo.is_(True),
            fora_da_perda(),
        )
    )
    m = MovimentoEstoque
    do_produto = (
        m.empresa_id == empresa.id,
        m.id_produto == id_produto,
        m.id_subproduto == id_subproduto,
    )

    efeito_por_dia: dict[date, Decimal] = defaultdict(Decimal)
    for dia, soma in db.execute(
        select(m.dia, func.sum(m.quantidade))
        .where(*do_produto, m.dia >= periodo.inicio, m.coi.in_(cois_que_afetam()))
        .group_by(m.dia)
    ):
        efeito_por_dia[dia] = soma or Decimal(0)

    def saldo_fim(dia: date) -> Decimal | None:
        if saldo_atual is None:
            return None
        depois = sum((v for d, v in efeito_por_dia.items() if d > dia), Decimal(0))
        return saldo_atual - depois

    no_periodo = (*do_produto, m.dia.between(periodo.inicio, periodo.fim))
    total_itens = db.scalar(select(func.count()).select_from(m).where(*no_periodo)) or 0
    movimentos = db.scalars(
        select(m)
        .where(*no_periodo)
        .order_by(m.dia.desc(), m.id_planilha.desc(), m.sequencia.desc(), m.id.desc())
        .limit(LIMITE_EXTRATO)
    ).all()
    saldos: dict[date, Decimal | None] = {}
    itens = []
    for mov in movimentos:
        if mov.dia not in saldos:
            saldos[mov.dia] = saldo_fim(mov.dia)
        itens.append(LinhaExtrato(mov, afeta(mov.coi), saldos[mov.dia]))

    itens_cat: dict[tuple[Categoria, bool | None], int] = defaultdict(int)
    qtd_cat: dict[tuple[Categoria, bool | None], Decimal] = defaultdict(Decimal)
    for coi, categoria, n, soma in db.execute(
        select(m.coi, m.tipo, func.count(), func.sum(m.quantidade))
        .where(*no_periodo)
        .group_by(m.coi, m.tipo)
    ):
        chave = (cast(Categoria, categoria), afeta(coi))
        itens_cat[chave] += n
        qtd_cat[chave] += soma or Decimal(0)

    entradas, saidas = db.execute(
        select(
            func.coalesce(func.sum(m.quantidade).filter(m.quantidade > 0), 0),
            func.coalesce(func.sum(m.quantidade).filter(m.quantidade < 0), 0),
        ).where(*no_periodo, m.coi.in_(cois_que_afetam()))
    ).one()
    return Extrato(
        empresa=empresa,
        periodo=periodo,
        saldo_atual=saldo_atual,
        saldo_inicial=saldo_fim(periodo.inicio - timedelta(days=1)),
        saldo_final=saldo_fim(periodo.fim),
        entradas=entradas or Decimal(0),
        saidas=saidas or Decimal(0),
        por_categoria=[
            TotalCategoria(cat, a, itens_cat[(cat, a)], qtd_cat[(cat, a)])
            for cat, a in sorted(itens_cat, key=lambda x: x[0])
        ],
        itens=itens,
        total_itens=total_itens,
        dias_sem_leitura=dias_sem_leitura(db, empresa.id, Intervalo(periodo.inicio, hoje)),
    )
