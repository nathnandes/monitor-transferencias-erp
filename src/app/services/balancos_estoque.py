from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.database.models import Empresa, MovimentoEstoque, Produto
from app.dominio.intervalo import Intervalo
from app.dominio.operacoes_estoque import COI_BALANCO
from app.services.estoque import descricao_item

LIMITE_PRODUTOS = 20
LIMITE_PARES = 50
LIMITE_RECONTAGENS = 200


@dataclass(frozen=True)
class AjusteProduto:
    empresa: Empresa
    id_produto: str
    id_subproduto: str
    descricao: str | None
    quantidade: Decimal
    valor: Decimal
    custo_falta: Decimal | None = None


@dataclass(frozen=True)
class TotaisBalanco:
    perda: Decimal
    ganho: Decimal
    produtos_com_falta: int
    produtos_com_sobra: int
    itens: int
    balancos: int

    @property
    def resultado(self) -> Decimal:
        return self.perda + self.ganho


@dataclass(frozen=True)
class LojaBalanco:
    empresa: Empresa
    totais: TotaisBalanco


@dataclass(frozen=True)
class ParTransferencia:
    id_produto: str
    id_subproduto: str
    descricao: str | None
    falta: AjusteProduto
    sobra: AjusteProduto
    quantidade: Decimal
    valor: Decimal


@dataclass(frozen=True)
class ResumoBalancos:
    periodo: Intervalo
    totais: TotaisBalanco
    por_loja: Sequence[LojaBalanco]
    maiores_perdas: Sequence[AjusteProduto]
    maiores_ganhos: Sequence[AjusteProduto]
    pares: Sequence[ParTransferencia]

    valor_pares: Decimal


def resumo_balancos(
    db: Session, periodo: Intervalo, empresa: Empresa | None = None
) -> ResumoBalancos:
    m = MovimentoEstoque
    sub = m.id_subproduto
    valor = func.coalesce(m.valor, 0)
    itens = (
        select(
            m.empresa_id.label("empresa_id"),
            m.id_produto.label("id_produto"),
            sub.label("sub"),
            m.dia.label("dia"),
            m.quantidade.label("quantidade"),
            valor.label("valor"),
        )
        .where(
            m.coi == COI_BALANCO,
            m.dia.between(periodo.inicio, periodo.fim),
            m.quantidade != 0,
            ~produto_com_asterisco(),
        )
        .subquery("itens")
    )
    i = itens.c

    totais_loja = {
        eid: (perda or Decimal(0), ganho or Decimal(0), n, dias)
        for eid, perda, ganho, n, dias in db.execute(
            select(
                i.empresa_id,
                func.sum(i.valor).filter(i.valor < 0),
                func.sum(i.valor).filter(i.valor > 0),
                func.count(),
                func.count(func.distinct(i.dia)),
            ).group_by(i.empresa_id)
        )
    }

    linhas = db.execute(
        select(
            i.empresa_id,
            i.id_produto,
            i.sub,
            func.sum(i.quantidade),
            func.sum(i.valor),
            func.sum(i.valor).filter(i.quantidade < 0),
            func.sum(i.quantidade).filter(i.quantidade < 0),
            func.max(descricao_item()),
        )
        .outerjoin(Produto, (Produto.id_produto == i.id_produto) & (Produto.id_subproduto == i.sub))
        .group_by(i.empresa_id, i.id_produto, i.sub)
    ).all()
    empresas = {
        e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_({x[0] for x in linhas})))
    }
    ajustes = [
        AjusteProduto(
            empresas[eid],
            prod,
            s,
            desc,
            qtd or Decimal(0),
            soma or Decimal(0),
            (valor_falta / qtd_falta) if valor_falta is not None and qtd_falta else None,
        )
        for eid, prod, s, qtd, soma, valor_falta, qtd_falta, desc in linhas
    ]

    pares = _pares([a for a in ajustes if a.quantidade])
    if empresa is not None:
        pares = [p for p in pares if empresa.id in (p.falta.empresa.id, p.sobra.empresa.id)]
        ajustes = [a for a in ajustes if a.empresa.id == empresa.id]
        totais_loja = {k: v for k, v in totais_loja.items() if k == empresa.id}
    pares.sort(key=lambda p: p.valor, reverse=True)

    def totais(eids: set[int], da_loja: list[AjusteProduto]) -> TotaisBalanco:
        return TotaisBalanco(
            perda=sum((totais_loja[e][0] for e in eids), Decimal(0)),
            ganho=sum((totais_loja[e][1] for e in eids), Decimal(0)),
            produtos_com_falta=sum(1 for a in da_loja if a.quantidade < 0),
            produtos_com_sobra=sum(1 for a in da_loja if a.quantidade > 0),
            itens=sum(totais_loja[e][2] for e in eids),
            balancos=sum(totais_loja[e][3] for e in eids),
        )

    por_loja = [
        LojaBalanco(empresas[eid], totais({eid}, [a for a in ajustes if a.empresa.id == eid]))
        for eid in sorted(totais_loja, key=lambda e: (len(empresas[e].codigo), empresas[e].codigo))
    ]
    return ResumoBalancos(
        periodo=periodo,
        totais=totais(set(totais_loja), ajustes),
        por_loja=por_loja,
        maiores_perdas=sorted((a for a in ajustes if a.valor < 0), key=lambda a: a.valor)[
            :LIMITE_PRODUTOS
        ],
        maiores_ganhos=sorted((a for a in ajustes if a.valor > 0), key=lambda a: -a.valor)[
            :LIMITE_PRODUTOS
        ],
        pares=pares[:LIMITE_PARES],
        valor_pares=sum((p.valor for p in pares), Decimal(0)),
    )


@dataclass(frozen=True)
class Recontagem:
    empresa: Empresa
    id_produto: str
    id_subproduto: str
    descricao: str | None
    marca: str | None
    contagens: int
    dias: Sequence[date]
    quantidade: Decimal
    valor: Decimal


@dataclass(frozen=True)
class ResultadoRecontagens:
    total: int
    itens: Sequence[Recontagem]

    marcas: Sequence[tuple[str, int]]


def recontagens(
    db: Session,
    periodo: Intervalo,
    *,
    mais_de: int,
    desde: date | None = None,
    empresa: Empresa | None = None,
    marcas: Collection[str] = (),
    limite: int = LIMITE_RECONTAGENS,
) -> ResultadoRecontagens:
    m = MovimentoEstoque
    contagens = func.count(func.distinct(m.id_planilha))
    condicoes = [
        m.coi == COI_BALANCO,
        m.dia.between(periodo.inicio, periodo.fim),
        m.quantidade != 0,
        ~produto_com_asterisco(),
    ]
    if empresa is not None:
        condicoes.append(m.empresa_id == empresa.id)
    filtro = contagens > max(mais_de, 1)
    if desde is not None:
        filtro = filtro & (func.max(m.dia) >= desde)

    grupos = list(
        db.execute(
            select(
                m.empresa_id,
                m.id_produto,
                m.id_subproduto,
                contagens,
                func.array_agg(func.distinct(m.dia)),
                func.sum(m.quantidade),
                func.sum(func.coalesce(m.valor, 0)),
                func.max(descricao_item()),
                func.max(func.nullif(func.trim(Produto.marca), "")),
            )
            .outerjoin(
                Produto,
                (Produto.id_produto == m.id_produto) & (Produto.id_subproduto == m.id_subproduto),
            )
            .where(*condicoes)
            .group_by(m.empresa_id, m.id_produto, m.id_subproduto)
            .having(filtro)
        ).all()
    )
    por_marca = Counter(x[8] for x in grupos if x[8])
    if marcas:
        grupos = [x for x in grupos if x[8] in set(marcas)]

    grupos.sort(key=lambda x: (-x[3], -max(x[4]).toordinal(), x[0], x[1], x[2]))
    total = len(grupos)
    grupos = grupos[:limite]
    empresas = {
        e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_({x[0] for x in grupos})))
    }
    return ResultadoRecontagens(
        total=total,
        itens=[
            Recontagem(
                empresas[eid],
                prod,
                s,
                desc,
                marca,
                n,
                sorted(dias),
                qtd or Decimal(0),
                valor or Decimal(0),
            )
            for eid, prod, s, n, dias, qtd, valor, desc, marca in grupos
        ],
        marcas=sorted(por_marca.items(), key=lambda x: (-x[1], x[0])),
    )


def produto_com_asterisco() -> ColumnElement[bool]:
    m = MovimentoEstoque

    p = aliased(Produto)
    return or_(
        func.coalesce(m.descricao_produto, "").contains("*"),
        exists().where(
            p.id_produto == m.id_produto,
            p.id_subproduto == m.id_subproduto,
            or_(p.descricao.contains("*"), p.descricao_resumida.contains("*")),
        ),
    )


def _pares(ajustes: list[AjusteProduto]) -> list[ParTransferencia]:
    por_produto: dict[tuple[str, str], list[AjusteProduto]] = {}
    for a in ajustes:
        por_produto.setdefault((a.id_produto, a.id_subproduto), []).append(a)
    pares: list[ParTransferencia] = []
    for (prod, s), lista in por_produto.items():
        faltas = sorted((a for a in lista if a.quantidade < 0), key=lambda a: a.quantidade)
        sobras = sorted((a for a in lista if a.quantidade > 0), key=lambda a: -a.quantidade)
        restante = {id(a): abs(a.quantidade) for a in faltas + sobras}
        for f in faltas:
            for so in sobras:
                q = min(restante[id(f)], restante[id(so)])
                if q <= 0:
                    continue
                restante[id(f)] -= q
                restante[id(so)] -= q
                pares.append(
                    ParTransferencia(prod, s, f.descricao, f, so, q, q * (f.custo_falta or 0))
                )
    return pares
