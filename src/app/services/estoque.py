from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import (
    ColumnElement,
    Integer,
    Numeric,
    Select,
    Subquery,
    case,
    exists,
    false,
    func,
    literal,
    null,
    or_,
    select,
    true,
    tuple_,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import InstrumentedAttribute, Session, contains_eager

from app.core.config import get_settings
from app.database import locais_perda
from app.database.locais_perda import fora_da_perda
from app.database.models import (
    Empresa,
    EstoqueConsolidado,
    EstoqueEmpresaLocalLote,
    MovimentoEstoque,
    MovimentoEstoqueDia,
    NotaMovimento,
    PrecoProdutoEmpresa,
    Produto,
    Sincronizacao,
    Venda,
    VendaDia,
    VendaItem,
)
from app.dominio.operacoes_estoque import CATALOGO, VERSAO_LIVRO
from app.services import excecoes_cobertura as excecoes

Situacao = Literal["com_saldo", "sem_saldo", "negativo", "com_reserva"]
Ordenacao = Literal["produto", "maior_saldo", "menor_saldo", "menor_cobertura", "maior_cobertura"]
StatusCobertura = Literal["ruptura", "critica", "baixa", "adequada", "excesso", "sem_giro"]
STATUS_COBERTURA: tuple[StatusCobertura, ...] = (
    "ruptura",
    "critica",
    "baixa",
    "adequada",
    "excesso",
    "sem_giro",
)


FonteMedia = Literal["vendas", "baixa"]


COIS_VENDA_BAIXA = tuple(
    sorted(c for (_, c), o in CATALOGO.items() if o.categoria == "venda" and o.afeta)
)
COIS_BAIXA = tuple(
    sorted(
        c
        for (_, c), o in CATALOGO.items()
        if o.categoria in ("venda", "devolucao_venda") and o.afeta
    )
)


COBERTURA_CRITICA_DIAS = 7
COBERTURA_BAIXA_DIAS = 15
COBERTURA_EXCESSO_DIAS = 90
JANELA_VENDAS_PADRAO = 30


_CHAVES_POR_CONSULTA = 500

TIPOS_ESTOQUE = ("estoque", "estoque_completo")
TIPOS_PRECOS = ("precos", "precos_completo")


def descricao_item() -> ColumnElement[str | None]:
    return func.coalesce(func.nullif(Produto.descricao_resumida, ""), Produto.descricao)


def texto_descricao(produto: Produto | None) -> str | None:
    if produto is None:
        return None
    return produto.descricao_resumida or produto.descricao


def descricao_do_produto(db: Session, id_produto: str, id_subproduto: str) -> str | None:
    return db.scalar(
        select(descricao_item()).where(
            Produto.id_produto == id_produto, Produto.id_subproduto == id_subproduto
        )
    )


@dataclass(frozen=True)
class ResumoLocalPerda:
    empresa: Empresa
    id_local: str
    descricao: str | None
    motivo: str
    produtos: int
    valor: Decimal | None


def resumo_locais_perda(db: Session) -> list[ResumoLocalPerda]:
    resultado = []
    e = EstoqueEmpresaLocalLote
    pr = PrecoProdutoEmpresa
    for x in locais_perda.locais_de_perda():
        empresa = db.scalar(select(Empresa).where(Empresa.codigo == x.empresa).limit(1))
        if empresa is None:
            continue
        descricao, produtos, valor = db.execute(
            select(
                func.max(e.descricao_local_estoque),
                func.count().filter(e.saldo_atual > 0),
                func.sum(e.saldo_atual * pr.custo_gerencial).filter(e.saldo_atual > 0),
            )
            .outerjoin(
                pr,
                (pr.empresa_id == e.empresa_id)
                & (pr.id_produto == e.id_produto)
                & (pr.id_subproduto == e.id_subproduto),
            )
            .where(e.empresa_id == empresa.id, e.id_local_estoque == x.local, e.ativo.is_(True))
        ).one()
        resultado.append(
            ResumoLocalPerda(empresa, x.local, descricao, x.motivo, produtos or 0, valor)
        )
    return resultado


class EmpresaNaoEncontrada(LookupError):
    pass


@dataclass(frozen=True)
class FiltrosEstoque:
    produto: str | None = None
    empresa: str | None = None
    local: str | None = None
    situacao: Situacao | None = None
    ordenacao: Ordenacao = "produto"
    cobertura: StatusCobertura | None = None
    media: FonteMedia = "vendas"

    fornecedor: str | None = None

    so_locais_da_loja: bool = False


@dataclass(frozen=True)
class JanelaVendas:
    inicio: date
    fim: date

    @classmethod
    def ultimos(cls, dias: int, hoje: date) -> "JanelaVendas":
        return cls(hoje - timedelta(days=dias), hoje - timedelta(days=1))

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1


@dataclass(frozen=True)
class ItemEstoque:
    id_produto: str
    id_subproduto: str
    saldo_atual: Decimal | None
    saldo_reservado: Decimal | None
    saldo_disponivel: Decimal | None
    empresas_com_estoque: int
    descricao: str | None = None
    preco_varejo_min: Decimal | None = None
    preco_varejo_max: Decimal | None = None
    custo_gerencial: Decimal | None = None
    valor_custo: Decimal | None = None
    venda_media_diaria: Decimal | None = None
    cobertura_dias: Decimal | None = None
    status_cobertura: StatusCobertura | None = None
    fabricante: str | None = None

    fornecedor: str | None = None

    excecao: bool = False


@dataclass(frozen=True)
class PaginaEstoque:
    total: int
    itens: Sequence[ItemEstoque]
    janela: JanelaVendas | None = None

    tem_vendas: bool = True


def _ordem_codigo(coluna: ColumnElement[str] | InstrumentedAttribute[str]) -> list[Any]:
    return [func.length(coluna), coluna]


def _empresa_id(db: Session, empresa: str | None) -> int | None:
    if not empresa:
        return None
    empresa_id = db.scalar(select(Empresa.id).where(Empresa.codigo == empresa))
    if empresa_id is None:
        raise EmpresaNaoEncontrada(f"Empresa {empresa} não encontrada.")
    return empresa_id


def _locais_do_local(empresa: str, local: str) -> tuple[str, ...]:
    somados = get_settings().locais_somados
    outros = (o for (emp, o), destino in somados.items() if (emp, destino) == (empresa, local))
    return (local, *outros)


def _local_somado(
    e: type[EstoqueEmpresaLocalLote],
) -> ColumnElement[str] | InstrumentedAttribute[str]:
    somados = get_settings().locais_somados
    if not somados:
        return e.id_local_estoque
    return case(
        *(
            ((Empresa.codigo == emp) & (e.id_local_estoque == outro), literal(destino))
            for (emp, outro), destino in somados.items()
        ),
        else_=e.id_local_estoque,
    )


def fora_da_loja(
    e: type[EstoqueEmpresaLocalLote] = EstoqueEmpresaLocalLote,
) -> ColumnElement[bool]:
    descricao = func.upper(func.coalesce(e.descricao_local_estoque, ""))
    comecos = get_settings().locais_fora_da_loja
    return ~or_(*(descricao.startswith(p) for p in comecos)) if comecos else true()


FALTA: tuple[StatusCobertura, ...] = ("ruptura", "critica", "baixa")


def _saldo_nos_depositos() -> Select[*tuple[Any, ...]]:
    e = EstoqueEmpresaLocalLote
    depositos = select(Empresa.id).where(Empresa.codigo.in_(get_settings().depositos_abastecimento))
    return (
        select(e.id_produto, e.id_subproduto)
        .where(e.empresa_id.in_(depositos), e.ativo.is_(True), fora_da_perda(), fora_da_loja(e))
        .group_by(e.empresa_id, e.id_produto, e.id_subproduto)
        .having(func.sum(e.saldo_disponivel) > 0)
    )


def itens_com_saldo_nos_depositos(db: Session) -> set[tuple[str, str]]:
    return {(p, s) for p, s in db.execute(_saldo_nos_depositos())}


def com_saldo_nos_depositos(
    id_produto: ColumnElement[str], id_subproduto: ColumnElement[str]
) -> ColumnElement[bool]:
    saldos = _saldo_nos_depositos().subquery("saldo_depositos")
    return exists(
        select(saldos.c.id_produto).where(
            saldos.c.id_produto == id_produto, saldos.c.id_subproduto == id_subproduto
        )
    )


def _base(
    empresa_id: int | None,
    locais: Sequence[str] | None = None,
    so_locais_da_loja: bool = False,
) -> Select[*tuple[Any, ...]]:
    if empresa_id is None:
        c = EstoqueConsolidado
        return select(
            c.id_produto.label("id_produto"),
            c.id_subproduto.label("id_subproduto"),
            c.saldo_atual_total.label("saldo_atual"),
            c.saldo_reservado_total.label("saldo_reservado"),
            c.saldo_disponivel_total.label("saldo_disponivel"),
            c.empresas_com_estoque.label("empresas_com_estoque"),
        )

    e = EstoqueEmpresaLocalLote
    atual = func.sum(e.saldo_atual)
    consulta = (
        select(
            e.id_produto.label("id_produto"),
            e.id_subproduto.label("id_subproduto"),
            atual.label("saldo_atual"),
            func.sum(e.saldo_reservado).label("saldo_reservado"),
            func.sum(e.saldo_disponivel).label("saldo_disponivel"),
            case((atual > 0, 1), else_=0).cast(Integer).label("empresas_com_estoque"),
        )
        .where(e.empresa_id == empresa_id, e.ativo.is_(True), fora_da_perda())
        .group_by(e.id_produto, e.id_subproduto)
    )
    if locais is not None:
        consulta = consulta.where(e.id_local_estoque.in_(locais))
    if so_locais_da_loja:
        consulta = consulta.where(fora_da_loja(e))
    return consulta


def _janela(janela: JanelaVendas | None) -> JanelaVendas:
    return janela or JanelaVendas.ultimos(JANELA_VENDAS_PADRAO, date.today())


def _dias_baixa(janela: JanelaVendas, empresa_id: int | None) -> Subquery:
    d = MovimentoEstoqueDia
    m = MovimentoEstoque
    com_venda = exists(
        select(m.id).where(
            m.empresa_id == d.empresa_id,
            m.dia == d.dia,
            m.tipo == "venda",
            m.coi.in_(COIS_VENDA_BAIXA),
        )
    )
    com_notas = exists(
        select(VendaDia.dia).where(
            VendaDia.empresa_id == d.empresa_id, VendaDia.dia == d.dia, VendaDia.notas > 0
        )
    )
    lido_depois = func.date(func.timezone(get_settings().tz, d.sincronizado_em)) > d.dia
    consulta = (
        select(d.empresa_id.label("empresa_id"), d.dia.label("dia"), com_venda.label("com_venda"))
        .join(Empresa, Empresa.id == d.empresa_id)
        .where(
            d.dia.between(janela.inicio, janela.fim),
            d.versao >= VERSAO_LIVRO,
            Empresa.ativo.is_(True),
            lido_depois,
            ~(com_notas & ~com_venda),
        )
    )
    if empresa_id is not None:
        consulta = consulta.where(d.empresa_id == empresa_id)
    return consulta.subquery("dias_baixa")


def _dias_vendas(
    janela: JanelaVendas, empresa_id: int | None, fonte: FonteMedia = "vendas"
) -> Subquery:
    if fonte == "baixa":
        b = _dias_baixa(janela, empresa_id)
        return (
            select(b.c.empresa_id, func.count().label("dias"))
            .group_by(b.c.empresa_id)
            .having(func.bool_or(b.c.com_venda))
            .subquery("dias_vendas")
        )
    d = VendaDia
    consulta = (
        select(d.empresa_id.label("empresa_id"), func.count().label("dias"))
        .join(Empresa, Empresa.id == d.empresa_id)
        .where(d.dia.between(janela.inicio, janela.fim), Empresa.ativo.is_(True))
        .group_by(d.empresa_id)
        .having(func.sum(d.notas) > 0)
    )
    if empresa_id is not None:
        consulta = consulta.where(d.empresa_id == empresa_id)
    return consulta.subquery("dias_vendas")


def _vendido(
    janela: JanelaVendas, empresa_id: int | None, fonte: FonteMedia = "vendas"
) -> Subquery:
    if fonte == "baixa":
        m = MovimentoEstoque
        b = _dias_baixa(janela, empresa_id)
        return (
            select(
                m.empresa_id.label("empresa_id"),
                m.id_produto.label("id_produto"),
                m.id_subproduto.label("id_subproduto"),
                (-func.sum(m.quantidade)).label("quantidade"),
            )
            .join(b, (b.c.empresa_id == m.empresa_id) & (b.c.dia == m.dia))
            .where(m.tipo.in_(("venda", "devolucao_venda")), m.coi.in_(COIS_BAIXA))
            .group_by(m.empresa_id, m.id_produto, m.id_subproduto)
            .subquery("vendido")
        )
    vendido = (
        select(
            Venda.empresa_id.label("empresa_id"),
            VendaItem.id_produto.label("id_produto"),
            VendaItem.id_subproduto.label("id_subproduto"),
            func.sum(VendaItem.quantidade).label("quantidade"),
        )
        .join(Venda, Venda.id == VendaItem.venda_id)
        .where(Venda.cancelada.is_(False), Venda.data_venda.between(janela.inicio, janela.fim))
        .group_by(Venda.empresa_id, VendaItem.id_produto, VendaItem.id_subproduto)
    )
    if empresa_id is not None:
        vendido = vendido.where(Venda.empresa_id == empresa_id)
    return vendido.subquery("vendido")


def _media_vendas(
    janela: JanelaVendas, empresa_id: int | None, fonte: FonteMedia = "vendas"
) -> Subquery:
    dias = _dias_vendas(janela, empresa_id, fonte)
    v = _vendido(janela, empresa_id, fonte)
    return (
        select(
            v.c.id_produto,
            v.c.id_subproduto,
            func.sum(v.c.quantidade / dias.c.dias.cast(Numeric)).label("media"),
        )
        .join(dias, dias.c.empresa_id == v.c.empresa_id)
        .group_by(v.c.id_produto, v.c.id_subproduto)
        .having(func.sum(v.c.quantidade) > 0)
        .subquery("media_vendas")
    )


def _tem_vendas(
    db: Session, janela: JanelaVendas, empresa_id: int | None, fonte: FonteMedia = "vendas"
) -> bool:
    dias = _dias_vendas(janela, empresa_id, fonte)
    return bool(db.scalar(select(exists(select(dias.c.empresa_id)))))


def _com_cobertura(
    base: Select[*tuple[Any, ...]],
    media: Subquery,
    tem_vendas: bool,
    empresa_id: int | None = None,
    so_com_deposito: bool = False,
) -> Select[*tuple[Any, ...]]:
    linhas = base.subquery("saldos")
    c = linhas.c
    cobertura, status = _classificacao(c.saldo_disponivel, media.c.media)
    if not tem_vendas:
        status = null()
    excecao: ColumnElement[bool] = false()
    if empresa_id is not None:
        excecao = excecoes.em_excecao(empresa_id, c.id_produto, c.id_subproduto)
        status = case((excecao, null()), else_=status)
    if so_com_deposito:
        sem_deposito = ~com_saldo_nos_depositos(c.id_produto, c.id_subproduto)
        status = case((status.in_(FALTA) & sem_deposito, null()), else_=status)
    return select(
        linhas,
        func.round(media.c.media, 3).label("venda_media_diaria"),
        cobertura.label("cobertura_dias"),
        status.label("status_cobertura"),
        excecao.label("excecao"),
    ).outerjoin(
        media,
        (media.c.id_produto == c.id_produto) & (media.c.id_subproduto == c.id_subproduto),
    )


def _classificacao(
    saldo_disponivel: ColumnElement[Any], media: ColumnElement[Any]
) -> tuple[ColumnElement[Any], ColumnElement[Any]]:
    disponivel = func.coalesce(saldo_disponivel, 0)
    cobertura = case((media > 0, func.round(func.greatest(disponivel, 0) / media, 1)))
    status = case(
        (media.is_(None), case((disponivel > 0, literal("sem_giro")))),
        (disponivel <= 0, literal("ruptura")),
        (cobertura < COBERTURA_CRITICA_DIAS, literal("critica")),
        (cobertura < COBERTURA_BAIXA_DIAS, literal("baixa")),
        (cobertura > COBERTURA_EXCESSO_DIAS, literal("excesso")),
        else_=literal("adequada"),
    )
    return cobertura, status


def classificar_cobertura(
    disponivel: Decimal | None, media: Decimal | None
) -> tuple[Decimal | None, StatusCobertura | None]:
    saldo = disponivel or Decimal(0)
    if not media or media <= 0:
        return None, ("sem_giro" if saldo > 0 else None)
    cobertura = (max(saldo, Decimal(0)) / media).quantize(Decimal("0.1"), ROUND_HALF_UP)
    if saldo <= 0:
        return cobertura, "ruptura"
    if cobertura < COBERTURA_CRITICA_DIAS:
        return cobertura, "critica"
    if cobertura < COBERTURA_BAIXA_DIAS:
        return cobertura, "baixa"
    if cobertura > COBERTURA_EXCESSO_DIAS:
        return cobertura, "excesso"
    return cobertura, "adequada"


def listar_estoque(
    db: Session,
    filtros: FiltrosEstoque,
    *,
    pagina: int,
    tamanho_pagina: int,
    janela: JanelaVendas | None = None,
) -> PaginaEstoque:
    empresa_id = _empresa_id(db, filtros.empresa)
    janela = _janela(janela)
    tem_vendas = _tem_vendas(db, janela, empresa_id, filtros.media)
    media = _media_vendas(janela, empresa_id, filtros.media)
    base = _base(
        empresa_id,
        _locais_do_local(filtros.empresa, filtros.local)
        if filtros.empresa and filtros.local
        else None,
        filtros.so_locais_da_loja,
    )
    linhas = _com_cobertura(
        base, media, tem_vendas, empresa_id, so_com_deposito=filtros.so_locais_da_loja
    ).subquery("estoque")
    c = linhas.c

    condicoes: list[ColumnElement[bool]] = []
    if filtros.produto:
        codigo = filtros.produto.strip()

        condicoes.append(or_(c.id_produto == codigo, c.id_subproduto == codigo))
    if filtros.situacao == "com_saldo":
        condicoes.append(c.saldo_atual > 0)
    elif filtros.situacao == "sem_saldo":
        condicoes.append(func.coalesce(c.saldo_atual, 0) == 0)
    elif filtros.situacao == "negativo":
        condicoes.append(c.saldo_atual < 0)
    elif filtros.situacao == "com_reserva":
        condicoes.append(c.saldo_reservado > 0)
    if filtros.cobertura:
        condicoes.append(c.status_cobertura == filtros.cobertura)
    if filtros.fornecedor:
        do_fornecedor = (
            _compras()
            .with_only_columns(MovimentoEstoque.id_produto, MovimentoEstoque.id_subproduto)
            .where(NotaMovimento.cnpj_emitente == filtros.fornecedor)
            .distinct()
            .cte("do_fornecedor")
            .prefix_with("MATERIALIZED")
        )
        condicoes.append(
            tuple_(c.id_produto, c.id_subproduto).in_(
                select(do_fornecedor.c.id_produto, do_fornecedor.c.id_subproduto)
            )
        )

    por_produto = [*_ordem_codigo(c.id_produto), *_ordem_codigo(c.id_subproduto)]
    if filtros.ordenacao == "maior_saldo":
        ordem = [c.saldo_atual.desc().nulls_last(), *por_produto]
    elif filtros.ordenacao == "menor_saldo":
        ordem = [c.saldo_atual.asc().nulls_last(), *por_produto]
    elif filtros.ordenacao == "menor_cobertura":
        ordem = [
            c.cobertura_dias.asc().nulls_last(),
            c.venda_media_diaria.desc().nulls_last(),
            *por_produto,
        ]
    elif filtros.ordenacao == "maior_cobertura":
        ordem = [c.cobertura_dias.desc().nulls_last(), *por_produto]
    else:
        ordem = por_produto

    consulta = select(linhas).where(*condicoes)

    resultado = db.execute(
        consulta.add_columns(func.count().over().label("_total"))
        .order_by(*ordem)
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    itens = [
        ItemEstoque(**{k: v for k, v in linha._mapping.items() if k != "_total"})
        for linha in resultado
    ]
    if resultado:
        total = int(resultado[0]._total)
    elif pagina > 1:
        total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    else:
        total = 0
    return PaginaEstoque(
        total=total,
        itens=_com_valores(db, itens, empresa_id),
        janela=janela,
        tem_vendas=tem_vendas,
    )


@dataclass(frozen=True)
class ContagemCobertura:
    tem_vendas: bool

    produtos: dict[StatusCobertura, int]


def contar_cobertura(
    db: Session,
    janela: JanelaVendas | None = None,
    empresa: str | None = None,
    local: str | None = None,
    fonte: FonteMedia = "vendas",
) -> ContagemCobertura:
    empresa_id = _empresa_id(db, empresa)
    janela = _janela(janela)
    contagem: dict[StatusCobertura, int] = dict.fromkeys(STATUS_COBERTURA, 0)
    if not _tem_vendas(db, janela, empresa_id, fonte):
        return ContagemCobertura(False, contagem)
    media = _media_vendas(janela, empresa_id, fonte)
    base = _base(empresa_id, _locais_do_local(empresa, local) if empresa and local else None)
    linhas = _com_cobertura(base, media, True, empresa_id).subquery("estoque")
    for status, quantos in db.execute(
        select(linhas.c.status_cobertura, func.count())
        .where(linhas.c.status_cobertura.is_not(None))
        .group_by(linhas.c.status_cobertura)
    ):
        contagem[status] = quantos
    return ContagemCobertura(True, contagem)


@dataclass(frozen=True)
class CoberturaLocal:
    id_local: str
    descricao: str | None
    produtos_com_saldo: int
    produtos: dict[StatusCobertura, int]

    somados: list[tuple[str, str | None]]


@dataclass(frozen=True)
class CoberturaEmpresa:
    empresa: Empresa

    tem_vendas: bool

    produtos: dict[StatusCobertura, int]
    locais: list[CoberturaLocal]

    excecoes: int = 0

    desconsiderados: list[tuple[str, str | None]] = field(default_factory=list)


def cobertura_por_local(db: Session, janela: JanelaVendas | None = None) -> list[CoberturaEmpresa]:
    janela = _janela(janela)
    e = EstoqueEmpresaLocalLote
    local = _local_somado(e)

    saldos = (
        select(
            e.empresa_id.label("empresa_id"),
            local.label("id_local"),
            e.id_produto.label("id_produto"),
            e.id_subproduto.label("id_subproduto"),
            func.max(case((e.id_local_estoque == local, e.descricao_local_estoque))).label(
                "descricao"
            ),
            func.sum(e.saldo_atual).label("saldo_atual"),
            func.sum(e.saldo_disponivel).label("saldo_disponivel"),
        )
        .join(Empresa, Empresa.id == e.empresa_id)
        .where(Empresa.ativo.is_(True), e.ativo.is_(True), fora_da_perda(), fora_da_loja(e))
        .group_by(e.empresa_id, local, e.id_produto, e.id_subproduto)
        .subquery("saldos_local")
    )
    somados: dict[tuple[int, str], list[tuple[str, str | None]]] = defaultdict(list)
    if get_settings().locais_somados:
        for empresa_id, destino, id_local, descricao in db.execute(
            select(e.empresa_id, local, e.id_local_estoque, func.max(e.descricao_local_estoque))
            .join(Empresa, Empresa.id == e.empresa_id)
            .where(e.ativo.is_(True), e.id_local_estoque != local, fora_da_loja(e))
            .group_by(e.empresa_id, local, e.id_local_estoque)
            .order_by(*_ordem_codigo(e.id_local_estoque))
        ):
            somados[(empresa_id, destino)].append((id_local, descricao))
    desconsiderados: dict[int, list[tuple[str, str | None]]] = defaultdict(list)
    for empresa_id, id_local, descricao in db.execute(
        select(e.empresa_id, e.id_local_estoque, func.max(e.descricao_local_estoque))
        .where(e.ativo.is_(True), ~fora_da_loja(e))
        .group_by(e.empresa_id, e.id_local_estoque)
        .order_by(*_ordem_codigo(e.id_local_estoque))
    ):
        desconsiderados[empresa_id].append((id_local, descricao))
    dias = _dias_vendas(janela, None, "baixa")
    v = _vendido(janela, None, "baixa")

    com_venda: dict[int, int] = {
        empresa_id: n for empresa_id, n in db.execute(select(dias.c.empresa_id, dias.c.dias))
    }
    medias: dict[tuple[int, str, str], Decimal] = {
        (empresa_id, produto, sub): quantidade / com_venda[empresa_id]
        for empresa_id, produto, sub, quantidade in db.execute(
            select(v.c.empresa_id, v.c.id_produto, v.c.id_subproduto, v.c.quantidade).where(
                v.c.quantidade > 0
            )
        )
        if empresa_id in com_venda
    }

    def nova() -> dict[StatusCobertura, int]:
        return dict.fromkeys(STATUS_COBERTURA, 0)

    por_local: dict[tuple[int, str], dict[StatusCobertura, int]] = defaultdict(nova)
    descricoes: dict[tuple[int, str], str | None] = {}
    com_saldo: dict[tuple[int, str], int] = defaultdict(int)
    disponivel_empresa: dict[tuple[int, str, str], Decimal] = defaultdict(Decimal)
    em_excecao = excecoes.chaves(db)
    com_deposito = itens_com_saldo_nos_depositos(db)

    def conta(status: StatusCobertura | None, produto: str, sub: str) -> bool:

        return status is not None and (status not in FALTA or (produto, sub) in com_deposito)

    for empresa_id, id_local, produto, sub, descricao, atual, disponivel in db.execute(
        select(saldos)
    ):
        chave = (empresa_id, id_local)
        anterior = descricoes.get(chave)
        descricoes[chave] = (
            max(anterior, descricao) if anterior and descricao else anterior or descricao
        )
        com_saldo[chave] += 1 if atual is not None and atual > 0 else 0
        contagem = por_local[chave]
        if empresa_id not in com_venda or (empresa_id, produto, sub) in em_excecao:
            continue
        _, status = classificar_cobertura(disponivel, medias.get((empresa_id, produto, sub)))
        if status and conta(status, produto, sub):
            contagem[status] += 1
        disponivel_empresa[(empresa_id, produto, sub)] += disponivel or 0
    por_empresa: dict[int, dict[StatusCobertura, int]] = defaultdict(nova)
    for (empresa_id, produto, sub), disponivel in disponivel_empresa.items():
        _, status = classificar_cobertura(disponivel, medias.get((empresa_id, produto, sub)))
        if status and conta(status, produto, sub):
            por_empresa[empresa_id][status] += 1

    locais: dict[int, list[CoberturaLocal]] = defaultdict(list)
    for empresa_id, id_local in sorted(por_local, key=lambda k: (k[0], len(k[1]), k[1])):
        chave = (empresa_id, id_local)
        locais[empresa_id].append(
            CoberturaLocal(
                id_local, descricoes[chave], com_saldo[chave], por_local[chave], somados[chave]
            )
        )
    empresas = db.scalars(
        select(Empresa).where(Empresa.id.in_(list(locais))).order_by(*_ordem_codigo(Empresa.codigo))
    )
    por_excecoes: dict[int, int] = defaultdict(int)
    for empresa_id, _, _ in em_excecao:
        por_excecoes[empresa_id] += 1
    return [
        CoberturaEmpresa(
            empresa,
            empresa.id in com_venda,
            dict(por_empresa[empresa.id]),
            locais[empresa.id],
            por_excecoes[empresa.id],
            desconsiderados[empresa.id],
        )
        for empresa in empresas
    ]


def media_vendas_por_empresa(
    db: Session, id_produto: str, id_subproduto: str, janela: JanelaVendas | None = None
) -> dict[int, Decimal]:
    janela = _janela(janela)
    dias = _dias_vendas(janela, None)
    vendido = func.coalesce(func.sum(VendaItem.quantidade), 0)
    return {
        empresa_id: quantidade / Decimal(n)
        for empresa_id, n, quantidade in db.execute(
            select(dias.c.empresa_id, dias.c.dias, vendido)
            .select_from(dias)
            .outerjoin(
                Venda,
                (Venda.empresa_id == dias.c.empresa_id)
                & Venda.cancelada.is_(False)
                & Venda.data_venda.between(janela.inicio, janela.fim),
            )
            .outerjoin(
                VendaItem,
                (VendaItem.venda_id == Venda.id)
                & (VendaItem.id_produto == id_produto)
                & (VendaItem.id_subproduto == id_subproduto),
            )
            .group_by(dias.c.empresa_id, dias.c.dias)
        )
    }


def _com_valores(
    db: Session, itens: list[ItemEstoque], empresa_id: int | None
) -> list[ItemEstoque]:
    if not itens:
        return itens
    if len(itens) > _CHAVES_POR_CONSULTA:
        return [
            completo
            for inicio in range(0, len(itens), _CHAVES_POR_CONSULTA)
            for completo in _com_valores(
                db, itens[inicio : inicio + _CHAVES_POR_CONSULTA], empresa_id
            )
        ]
    chaves = [(i.id_produto, i.id_subproduto) for i in itens]
    cadastro = {
        (p, s): (d, marca)
        for p, s, d, marca in db.execute(
            select(
                Produto.id_produto, Produto.id_subproduto, descricao_item(), Produto.marca
            ).where(tuple_(Produto.id_produto, Produto.id_subproduto).in_(chaves))
        )
    }
    fornecedores = ultimo_fornecedor(db, chaves)
    pr = PrecoProdutoEmpresa
    na_pagina = tuple_(pr.id_produto, pr.id_subproduto).in_(chaves)
    valores: dict[tuple[str, str], dict[str, Decimal | None]] = {}
    if empresa_id is not None:
        for p, s, varejo, custo in db.execute(
            select(pr.id_produto, pr.id_subproduto, pr.preco_varejo, pr.custo_gerencial).where(
                pr.empresa_id == empresa_id, na_pagina
            )
        ):
            valores[(p, s)] = {"min": varejo, "max": varejo, "custo": custo}
    else:
        for p, s, minimo, maximo in db.execute(
            select(
                pr.id_produto,
                pr.id_subproduto,
                func.min(pr.preco_varejo),
                func.max(pr.preco_varejo),
            )
            .join(Empresa, Empresa.id == pr.empresa_id)
            .where(Empresa.ativo.is_(True), na_pagina)
            .group_by(pr.id_produto, pr.id_subproduto)
        ):
            valores[(p, s)] = {"min": minimo, "max": maximo, "custo": None}
        e = EstoqueEmpresaLocalLote
        for p, s, valor, saldo in db.execute(
            select(
                e.id_produto,
                e.id_subproduto,
                func.sum(e.saldo_atual * pr.custo_gerencial),
                func.sum(e.saldo_atual).filter(pr.custo_gerencial.is_not(None)),
            )
            .join(
                pr,
                (pr.empresa_id == e.empresa_id)
                & (pr.id_produto == e.id_produto)
                & (pr.id_subproduto == e.id_subproduto),
            )
            .join(Empresa, Empresa.id == e.empresa_id)
            .where(
                e.ativo.is_(True),
                Empresa.ativo.is_(True),
                tuple_(e.id_produto, e.id_subproduto).in_(chaves),
                fora_da_perda(),
            )
            .group_by(e.id_produto, e.id_subproduto)
        ):
            v = valores.setdefault((p, s), {"min": None, "max": None, "custo": None})
            v["valor"] = valor
            v["custo"] = (valor / saldo) if valor is not None and saldo and saldo > 0 else None

    resultado = []
    for item in itens:
        chave = (item.id_produto, item.id_subproduto)
        v = valores.get(chave, {})
        custo = v.get("custo")
        if empresa_id is not None:
            valor = (
                item.saldo_atual * custo
                if item.saldo_atual is not None and custo is not None
                else None
            )
        else:
            valor = v.get("valor")
        descricao, fabricante = cadastro.get(chave, (None, None))
        resultado.append(
            replace(
                item,
                descricao=descricao,
                fabricante=fabricante,
                fornecedor=fornecedores.get(chave),
                preco_varejo_min=v.get("min"),
                preco_varejo_max=v.get("max"),
                custo_gerencial=custo,
                valor_custo=valor,
            )
        )
    return resultado


def _compras() -> Select[*tuple[Any, ...]]:
    m, n = MovimentoEstoque, NotaMovimento
    return (
        select(m)
        .join(n, (n.empresa_id == m.empresa_id) & (n.id_planilha == m.id_planilha))
        .where(m.tipo == "compra", n.nome_emitente.is_not(None))
    )


def ultimo_fornecedor(db: Session, chaves: Sequence[tuple[str, str]]) -> dict[tuple[str, str], str]:
    m, n = MovimentoEstoque, NotaMovimento
    consulta = (
        _compras()
        .with_only_columns(m.id_produto, m.id_subproduto, n.nome_emitente)
        .where(tuple_(m.id_produto, m.id_subproduto).in_(chaves))
        .ext(distinct_on(m.id_produto, m.id_subproduto))
        .order_by(m.id_produto, m.id_subproduto, m.dia.desc(), m.id.desc())
    )
    return {(p, s): nome for p, s, nome in db.execute(consulta) if nome}


@dataclass(frozen=True)
class FornecedorEstoque:
    cnpj: str
    nome: str
    itens: int


def listar_fornecedores(db: Session) -> list[FornecedorEstoque]:
    m, n = MovimentoEstoque, NotaMovimento
    nome = func.max(n.nome_emitente)
    consulta = (
        _compras()
        .with_only_columns(
            n.cnpj_emitente,
            nome,
            func.count(tuple_(m.id_produto, m.id_subproduto).distinct()),
        )
        .where(n.cnpj_emitente.is_not(None))
        .group_by(n.cnpj_emitente)
        .order_by(nome, n.cnpj_emitente)
    )
    return [
        FornecedorEstoque(c, nome_, itens)
        for c, nome_, itens in db.execute(consulta)
        if c and nome_
    ]


@dataclass(frozen=True)
class FornecedorDoProduto:
    nome: str
    cnpj: str | None
    compras: int
    quantidade: Decimal | None
    ultima_compra: date
    ultima_empresa: Empresa

    custo_ultima: Decimal | None


def fornecedores_do_produto(
    db: Session, id_produto: str, id_subproduto: str
) -> list[FornecedorDoProduto]:
    m, n = MovimentoEstoque, NotaMovimento
    linhas = db.execute(
        _compras()
        .with_only_columns(
            n.cnpj_emitente, n.nome_emitente, m.id_planilha, m.dia, m.quantidade, m.valor, Empresa
        )
        .join(Empresa, Empresa.id == m.empresa_id)
        .where(m.id_produto == id_produto, m.id_subproduto == id_subproduto)
        .order_by(m.dia.desc(), m.id.desc())
    ).all()
    grupos: dict[str, list[Any]] = {}
    for linha in linhas:
        grupos.setdefault(linha.cnpj_emitente or linha.nome_emitente, []).append(linha)
    resultado = []
    for compras in grupos.values():
        ultima = compras[0]
        custo = (
            (ultima.valor / ultima.quantidade).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            if ultima.valor and ultima.quantidade
            else None
        )
        resultado.append(
            FornecedorDoProduto(
                nome=ultima.nome_emitente,
                cnpj=ultima.cnpj_emitente,
                compras=len({(c.Empresa.id, c.id_planilha) for c in compras}),
                quantidade=_soma(c.quantidade for c in compras),
                ultima_compra=ultima.dia,
                ultima_empresa=ultima.Empresa,
                custo_ultima=custo,
            )
        )
    return resultado


@dataclass(frozen=True)
class ResumoEmpresa:
    empresa: Empresa
    produtos_com_saldo: int
    linhas: int
    valor_custo: Decimal | None = None


@dataclass(frozen=True)
class ResumoEstoque:
    produtos: int
    produtos_com_saldo: int
    produtos_negativos: int
    produtos_com_reserva: int

    atualizado_em: datetime | None
    ultima_sincronizacao: Sincronizacao | None
    por_empresa: Sequence[ResumoEmpresa]

    valor_custo: Decimal | None = None

    linhas_sem_custo: int = 0
    precos_atualizados_em: datetime | None = None


_EXECUCAO_GLOBAL = (
    Sincronizacao.tipo.in_(TIPOS_ESTOQUE),
    Sincronizacao.empresa_id.is_(None),
    Sincronizacao.sincronizacao_pai_id.is_(None),
)


def ultima_atualizacao_precos(db: Session) -> datetime | None:
    return db.scalar(
        select(func.max(Sincronizacao.fim)).where(
            Sincronizacao.tipo.in_(TIPOS_PRECOS),
            Sincronizacao.empresa_id.is_(None),
            Sincronizacao.sincronizacao_pai_id.is_(None),
            Sincronizacao.status.in_(("sucesso", "parcial")),
        )
    )


def ultima_atualizacao(db: Session) -> datetime | None:
    return db.scalar(
        select(func.max(Sincronizacao.fim)).where(
            *_EXECUCAO_GLOBAL, Sincronizacao.status.in_(("sucesso", "parcial"))
        )
    )


def resumo_estoque(db: Session) -> ResumoEstoque:
    c = EstoqueConsolidado
    produtos, com_saldo, negativos, com_reserva = db.execute(
        select(
            func.count(),
            func.count().filter(c.saldo_atual_total > 0),
            func.count().filter(c.saldo_atual_total < 0),
            func.count().filter(c.saldo_reservado_total > 0),
        ).select_from(c)
    ).one()

    atualizado_em = ultima_atualizacao(db)
    ultima = db.scalar(
        select(Sincronizacao)
        .where(*_EXECUCAO_GLOBAL)
        .order_by(Sincronizacao.inicio.desc(), Sincronizacao.id.desc())
        .limit(1)
    )

    e = EstoqueEmpresaLocalLote

    por_produto = (
        select(
            e.empresa_id.label("empresa_id"),
            func.sum(e.saldo_atual).label("saldo"),
            func.count().label("linhas"),
        )
        .where(e.ativo.is_(True), fora_da_perda())
        .group_by(e.empresa_id, e.id_produto, e.id_subproduto)
        .subquery()
    )
    contagens = (
        select(
            por_produto.c.empresa_id,
            func.count().filter(por_produto.c.saldo > 0).label("com_saldo"),
            func.sum(por_produto.c.linhas).label("linhas"),
        )
        .group_by(por_produto.c.empresa_id)
        .subquery()
    )
    pr = PrecoProdutoEmpresa
    valores = (
        select(
            e.empresa_id.label("empresa_id"),
            func.sum(e.saldo_atual * pr.custo_gerencial).label("valor"),
            func.count().filter(pr.custo_gerencial.is_(None)).label("sem_custo"),
        )
        .outerjoin(
            pr,
            (pr.empresa_id == e.empresa_id)
            & (pr.id_produto == e.id_produto)
            & (pr.id_subproduto == e.id_subproduto),
        )
        .where(e.ativo.is_(True), e.saldo_atual > 0, fora_da_perda())
        .group_by(e.empresa_id)
        .subquery()
    )
    por_empresa = []
    sem_custo_total = 0
    for empresa, com_saldo_empresa, linhas, valor, sem_custo in db.execute(
        select(
            Empresa,
            contagens.c.com_saldo,
            contagens.c.linhas,
            valores.c.valor,
            valores.c.sem_custo,
        )
        .outerjoin(contagens, contagens.c.empresa_id == Empresa.id)
        .outerjoin(valores, valores.c.empresa_id == Empresa.id)
        .where(Empresa.ativo.is_(True))
        .order_by(*_ordem_codigo(Empresa.codigo))
    ):
        por_empresa.append(ResumoEmpresa(empresa, com_saldo_empresa or 0, int(linhas or 0), valor))
        sem_custo_total += int(sem_custo or 0)
    com_valor = [r.valor_custo for r in por_empresa if r.valor_custo is not None]
    return ResumoEstoque(
        produtos=produtos,
        produtos_com_saldo=com_saldo,
        produtos_negativos=negativos,
        produtos_com_reserva=com_reserva,
        atualizado_em=atualizado_em,
        ultima_sincronizacao=ultima,
        por_empresa=por_empresa,
        valor_custo=sum(com_valor, Decimal(0)) if com_valor else None,
        linhas_sem_custo=sem_custo_total,
        precos_atualizados_em=ultima_atualizacao_precos(db),
    )


@dataclass(frozen=True)
class DetalheProduto:
    id_produto: str
    id_subproduto: str
    consolidado: EstoqueConsolidado | None

    linhas: Sequence[EstoqueEmpresaLocalLote]
    produto: Produto | None = None

    precos: dict[int, PrecoProdutoEmpresa] | None = None


def obter_produto(db: Session, id_produto: str, id_subproduto: str) -> DetalheProduto | None:
    e = EstoqueEmpresaLocalLote
    linhas = db.scalars(
        select(e)
        .join(e.empresa)
        .options(contains_eager(e.empresa))
        .where(
            e.id_produto == id_produto,
            e.id_subproduto == id_subproduto,
            e.ativo.is_(True),
            Empresa.ativo.is_(True),
        )
        .order_by(*_ordem_codigo(Empresa.codigo), *_ordem_codigo(e.id_local_estoque))
    ).all()
    consolidado = db.scalar(
        select(EstoqueConsolidado).where(
            EstoqueConsolidado.id_produto == id_produto,
            EstoqueConsolidado.id_subproduto == id_subproduto,
        )
    )
    if not linhas and consolidado is None:
        return None
    produto = db.scalar(
        select(Produto).where(
            Produto.id_produto == id_produto, Produto.id_subproduto == id_subproduto
        )
    )
    pr = PrecoProdutoEmpresa
    precos = {
        p.empresa_id: p
        for p in db.scalars(
            select(pr)
            .join(Empresa, Empresa.id == pr.empresa_id)
            .where(
                pr.id_produto == id_produto,
                pr.id_subproduto == id_subproduto,
                Empresa.ativo.is_(True),
            )
        )
    }
    return DetalheProduto(id_produto, id_subproduto, consolidado, linhas, produto, precos)


def _soma(valores: Iterable[Decimal | None]) -> Decimal | None:
    presentes = [v for v in valores if v is not None]
    return sum(presentes, Decimal(0)) if presentes else None


@dataclass(frozen=True)
class EmpresaDoProduto:
    empresa: Empresa
    saldo_atual: Decimal | None
    saldo_reservado: Decimal | None
    saldo_disponivel: Decimal | None

    venda_media_diaria: Decimal | None
    cobertura_dias: Decimal | None
    status_cobertura: StatusCobertura | None
    preco: PrecoProdutoEmpresa | None
    valor_custo: Decimal | None

    locais: list[tuple[EstoqueEmpresaLocalLote, str | None]]


@dataclass(frozen=True)
class ProdutoDetalhado:
    detalhe: DetalheProduto
    empresas: list[EmpresaDoProduto]
    saldo_atual: Decimal | None
    saldo_reservado: Decimal | None
    saldo_disponivel: Decimal | None
    venda_media_diaria: Decimal | None
    cobertura_dias: Decimal | None
    status_cobertura: StatusCobertura | None
    empresas_com_estoque: int
    atualizado_em: datetime | None
    fornecedores: list[FornecedorDoProduto]


def detalhar_produto(
    db: Session, id_produto: str, id_subproduto: str, janela: JanelaVendas | None = None
) -> ProdutoDetalhado | None:
    detalhe = obter_produto(db, id_produto, id_subproduto)
    if detalhe is None:
        return None

    por_empresa: dict[int, list[EstoqueEmpresaLocalLote]] = defaultdict(list)
    for linha in detalhe.linhas:
        por_empresa[linha.empresa_id].append(linha)
    precos = detalhe.precos or {}
    medias = media_vendas_por_empresa(db, id_produto, id_subproduto, janela)

    empresas = []
    for empresa_id, linhas in por_empresa.items():
        locais = [(x, locais_perda.motivo_perda(x)) for x in linhas]
        validas = [x for x, perda in locais if not perda]
        preco = precos.get(empresa_id)
        custo = preco.custo_gerencial if preco else None
        saldo = _soma(x.saldo_atual for x in validas)
        disponivel = _soma(x.saldo_disponivel for x in validas)
        media = medias.get(empresa_id) or None
        cobertura, situacao = (
            classificar_cobertura(disponivel, media) if empresa_id in medias else (None, None)
        )
        empresas.append(
            EmpresaDoProduto(
                empresa=linhas[0].empresa,
                saldo_atual=saldo,
                saldo_reservado=_soma(x.saldo_reservado for x in validas),
                saldo_disponivel=disponivel,
                venda_media_diaria=media,
                cobertura_dias=cobertura,
                status_cobertura=situacao,
                preco=preco,
                valor_custo=saldo * custo if saldo is not None and custo is not None else None,
                locais=locais,
            )
        )

    c = detalhe.consolidado
    disponivel_total = (
        c.saldo_disponivel_total if c else _soma(e.saldo_disponivel for e in empresas)
    )
    media_total = sum(medias.values(), Decimal(0)) or None
    cobertura_total, situacao_total = (
        classificar_cobertura(disponivel_total, media_total) if medias else (None, None)
    )
    return ProdutoDetalhado(
        detalhe=detalhe,
        empresas=empresas,
        saldo_atual=c.saldo_atual_total if c else _soma(e.saldo_atual for e in empresas),
        saldo_reservado=(
            c.saldo_reservado_total if c else _soma(e.saldo_reservado for e in empresas)
        ),
        saldo_disponivel=disponivel_total,
        venda_media_diaria=media_total,
        cobertura_dias=cobertura_total,
        status_cobertura=situacao_total,
        empresas_com_estoque=(
            c.empresas_com_estoque if c else sum(1 for e in empresas if (e.saldo_atual or 0) > 0)
        ),
        atualizado_em=c.atualizado_em if c else None,
        fornecedores=fornecedores_do_produto(db, id_produto, id_subproduto),
    )
