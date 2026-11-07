from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.database.models import (
    Devolucao,
    Empresa,
    Produto,
    Venda,
    VendaDia,
    VendaItem,
    VendaTitulo,
    Vendedor,
)
from app.dominio.canais_venda import (
    Canal,
)
from app.dominio.intervalo import Intervalo, IntervaloInvalido
from app.services.estoque import descricao_item

ROTULO_CANAL: dict[str, str] = {
    "balcao": "Balcão (NFC-e)",
    "televendas": "Televendas",
    "faturamento": "Faturamento logística",
}


DIAS_SERIE_DIARIA = 62

MAX_DIAS_ESCOLHIDOS = 60
CATEGORIAS_NO_GRAFICO = 8
PRODUTOS_NO_RANKING = 10
SEM_CATEGORIA = "SEM CATEGORIA"
OUTRAS_CATEGORIAS = "OUTRAS"

Granularidade = Literal["dia", "mes"]

_CENTAVOS = Decimal("0.01")


@dataclass(frozen=True)
class FiltroVendas:
    empresa: Empresa | None = None
    periodo: Intervalo | None = None
    comparacao: Intervalo | None = None
    canal: Canal | None = None

    dias: tuple[date, ...] | None = None

    def __post_init__(self) -> None:
        if self.comparacao and not self.periodo:
            raise IntervaloInvalido("A comparação exige um período.")
        if self.dias is not None:
            if not self.dias:
                raise IntervaloInvalido("Informe ao menos um dia.")
            if len(self.dias) > MAX_DIAS_ESCOLHIDOS:
                raise IntervaloInvalido(f"No máximo {MAX_DIAS_ESCOLHIDOS} dias.")
            if self.comparacao:
                raise IntervaloInvalido("Dias escolhidos não aceitam comparação.")

    @classmethod
    def por_dias(
        cls, dias: list[date], empresa: Empresa | None = None, canal: Canal | None = None
    ) -> "FiltroVendas":
        unicos = tuple(sorted(set(dias)))
        periodo = Intervalo(unicos[0], unicos[-1]) if unicos else None
        return cls(empresa=empresa, periodo=periodo, canal=canal, dias=unicos)


@dataclass(frozen=True)
class Totais:
    faturamento: Decimal
    notas: int
    quantidade: Decimal
    desconto: Decimal

    devolucoes: Decimal | None = None

    @property
    def ticket_medio(self) -> Decimal | None:
        return (self.faturamento / self.notas).quantize(_CENTAVOS) if self.notas else None

    @property
    def liquido(self) -> Decimal:
        return self.faturamento - (self.devolucoes or Decimal(0))


@dataclass(frozen=True)
class PontoSerie:
    chave: str
    faturamento: Decimal
    notas: int
    quantidade: Decimal
    devolucoes: Decimal | None = None


@dataclass(frozen=True)
class Fatia:
    chave: str
    faturamento: Decimal
    notas: int
    quantidade: Decimal


@dataclass(frozen=True)
class FatiaEmpresa:
    empresa: Empresa
    faturamento: Decimal
    notas: int

    @property
    def ticket_medio(self) -> Decimal | None:
        return (self.faturamento / self.notas).quantize(_CENTAVOS) if self.notas else None


NOMES_VENDEDOR_GENERICO = frozenset({"VENDEDOR EXEMPLO"})


def eh_vendedor_generico(nome: str | None) -> bool:
    return nome is not None and " ".join(nome.split()).upper() in NOMES_VENDEDOR_GENERICO


@dataclass(frozen=True)
class FatiaVendedor:
    id_vendedor: str
    faturamento: Decimal
    notas: int
    empresas: list[Empresa]

    faturamento_comparacao: Decimal | None = None

    nome: str | None = None

    @property
    def ticket_medio(self) -> Decimal | None:
        return (self.faturamento / self.notas).quantize(_CENTAVOS) if self.notas else None


@dataclass(frozen=True)
class RankingVendedores:
    vendedores: list[FatiaVendedor]
    sem_vendedor_faturamento: Decimal
    sem_vendedor_notas: int

    @property
    def media(self) -> Decimal | None:
        if not self.vendedores:
            return None
        total = sum((v.faturamento for v in self.vendedores), Decimal(0))
        return (total / len(self.vendedores)).quantize(_CENTAVOS)


@dataclass(frozen=True)
class ProdutoVendido:
    id_produto: str
    id_subproduto: str | None
    descricao: str | None
    quantidade: Decimal
    faturamento: Decimal


@dataclass(frozen=True)
class FormaPagamento:
    forma: str
    valor: Decimal
    parcelas: int


@dataclass(frozen=True)
class Cobertura:
    desde: date | None
    ate: date | None
    atualizado_em: datetime | None


@dataclass(frozen=True)
class ResumoVendas:
    gerado_em: datetime
    totais: Totais
    comparacao: Totais | None
    granularidade: Granularidade
    serie: list[PontoSerie]
    por_canal: list[Fatia]
    por_categoria: list[Fatia]
    por_empresa: list[FatiaEmpresa]
    produtos: list[ProdutoVendido]
    cobertura: Cobertura
    vendedores: RankingVendedores

    formas_pagamento: list[FormaPagamento] | None = None


def _condicoes(filtro: FiltroVendas, periodo: Intervalo | None) -> list[ColumnElement[bool]]:
    condicoes: list[ColumnElement[bool]] = [Venda.cancelada.is_(False)]
    if filtro.empresa is not None:
        condicoes.append(Venda.empresa_id == filtro.empresa.id)
    if filtro.canal is not None:
        condicoes.append(Venda.canal == filtro.canal)
    if periodo is not None:
        condicoes.append(Venda.data_venda.between(periodo.inicio, periodo.fim))
    if filtro.dias is not None:
        condicoes.append(Venda.data_venda.in_(filtro.dias))
    return condicoes


def _condicoes_sem_canal(
    filtro: FiltroVendas,
    periodo: Intervalo | None,
    coluna_empresa: InstrumentedAttribute[int],
    coluna_data: InstrumentedAttribute[date],
) -> list[ColumnElement[bool]]:
    condicoes: list[ColumnElement[bool]] = []
    if filtro.empresa is not None:
        condicoes.append(coluna_empresa == filtro.empresa.id)
    if periodo is not None:
        condicoes.append(coluna_data.between(periodo.inicio, periodo.fim))
    if filtro.dias is not None:
        condicoes.append(coluna_data.in_(filtro.dias))
    return condicoes


def _decimal(valor: object) -> Decimal:
    return Decimal(str(valor)) if valor is not None else Decimal(0)


def _devolucoes(db: Session, filtro: FiltroVendas, periodo: Intervalo | None) -> Decimal | None:
    if filtro.canal is not None:
        return None
    condicoes = _condicoes_sem_canal(
        filtro, periodo, Devolucao.empresa_id, Devolucao.data_devolucao
    )
    return _decimal(db.scalar(select(func.sum(Devolucao.valor_total)).where(*condicoes)))


def _totais_do_periodo(db: Session, filtro: FiltroVendas, periodo: Intervalo | None) -> Totais:
    totais = _totais(db, _condicoes(filtro, periodo))
    return replace(totais, devolucoes=_devolucoes(db, filtro, periodo))


def totais_do_periodo(db: Session, periodo: Intervalo) -> Totais:
    return _totais_do_periodo(db, FiltroVendas(periodo=periodo), periodo)


def _totais(db: Session, condicoes: list[ColumnElement[bool]]) -> Totais:
    faturamento, notas, desconto = db.execute(
        select(func.sum(Venda.valor_total), func.count(), func.sum(Venda.valor_desconto)).where(
            *condicoes
        )
    ).one()
    quantidade = db.scalar(
        select(func.sum(VendaItem.quantidade))
        .join(Venda, Venda.id == VendaItem.venda_id)
        .where(*condicoes)
    )
    return Totais(_decimal(faturamento), notas, _decimal(quantidade), _decimal(desconto))


def _baldes(intervalo: Intervalo, granularidade: Granularidade) -> list[str]:
    if granularidade == "dia":
        dias = (intervalo.fim - intervalo.inicio).days + 1
        return [(intervalo.inicio + timedelta(days=n)).isoformat() for n in range(dias)]
    chaves: list[str] = []
    ano, mes = intervalo.inicio.year, intervalo.inicio.month
    while (ano, mes) <= (intervalo.fim.year, intervalo.fim.month):
        chaves.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return chaves


def _serie(
    db: Session, filtro: FiltroVendas, condicoes: list[ColumnElement[bool]]
) -> tuple[Granularidade, list[PontoSerie]]:
    intervalo = filtro.periodo
    granularidade: Granularidade = "mes"
    if filtro.dias is not None:
        granularidade = "dia"
    elif intervalo is None:
        inicio, fim = db.execute(
            select(func.min(Venda.data_venda), func.max(Venda.data_venda)).where(*condicoes)
        ).one()
        if inicio is None or fim is None:
            return granularidade, []
        intervalo = Intervalo(inicio, fim)
    elif (intervalo.fim - intervalo.inicio).days + 1 <= DIAS_SERIE_DIARIA:
        granularidade = "dia"
    formato = "YYYY-MM-DD" if granularidade == "dia" else "YYYY-MM"
    balde = func.to_char(Venda.data_venda, formato).label("balde")

    valores = {
        chave: (_decimal(fat), notas)
        for chave, fat, notas in db.execute(
            select(balde, func.sum(Venda.valor_total), func.count())
            .where(*condicoes)
            .group_by(balde)
        )
    }
    quantidades = {
        chave: _decimal(qtd)
        for chave, qtd in db.execute(
            select(balde, func.sum(VendaItem.quantidade))
            .join(Venda, Venda.id == VendaItem.venda_id)
            .where(*condicoes)
            .group_by(balde)
        )
    }
    devolucoes: dict[str, Decimal] | None = None
    if filtro.canal is None:
        balde_dev = func.to_char(Devolucao.data_devolucao, formato).label("balde")
        devolucoes = {
            chave: _decimal(valor)
            for chave, valor in db.execute(
                select(balde_dev, func.sum(Devolucao.valor_total))
                .where(
                    *_condicoes_sem_canal(
                        filtro, intervalo, Devolucao.empresa_id, Devolucao.data_devolucao
                    )
                )
                .group_by(balde_dev)
            )
        }
    baldes = (
        [d.isoformat() for d in filtro.dias]
        if filtro.dias is not None
        else _baldes(intervalo, granularidade)
        if intervalo is not None
        else []
    )
    serie = []
    for chave in baldes:
        faturamento, notas = valores.get(chave, (Decimal(0), 0))
        serie.append(
            PontoSerie(
                chave,
                faturamento,
                notas,
                quantidades.get(chave, Decimal(0)),
                devolucoes.get(chave, Decimal(0)) if devolucoes is not None else None,
            )
        )
    return granularidade, serie


def _por_canal(
    db: Session, condicoes: list[ColumnElement[bool]], canal: Canal | None = None
) -> list[Fatia]:
    linhas = db.execute(
        select(Venda.canal, func.sum(Venda.valor_total), func.count())
        .where(*condicoes)
        .group_by(Venda.canal)
    ).all()
    quantidades = {
        canal: _decimal(qtd)
        for canal, qtd in db.execute(
            select(Venda.canal, func.sum(VendaItem.quantidade))
            .join(Venda, Venda.id == VendaItem.venda_id)
            .where(*condicoes)
            .group_by(Venda.canal)
        )
    }
    fatias = [
        Fatia(canal, _decimal(fat), notas, quantidades.get(canal, Decimal(0)))
        for canal, fat, notas in linhas
    ]
    com_venda = {f.chave for f in fatias}
    esperados = [canal] if canal is not None else list(ROTULO_CANAL)
    fatias += [Fatia(c, Decimal(0), 0, Decimal(0)) for c in esperados if c not in com_venda]
    return sorted(fatias, key=lambda f: f.faturamento, reverse=True)


def _juncao_produto() -> ColumnElement[bool]:
    return and_(
        Produto.id_produto == VendaItem.id_produto,
        Produto.id_subproduto == VendaItem.id_subproduto,
    )


def _por_categoria(db: Session, condicoes: list[ColumnElement[bool]]) -> list[Fatia]:
    categoria = func.coalesce(Produto.divisao, SEM_CATEGORIA).label("categoria")
    faturamento = func.sum(VendaItem.valor_liquido)
    linhas = db.execute(
        select(
            categoria,
            faturamento,
            func.count(func.distinct(Venda.id)),
            func.sum(VendaItem.quantidade),
        )
        .select_from(VendaItem)
        .join(Venda, Venda.id == VendaItem.venda_id)
        .outerjoin(Produto, _juncao_produto())
        .where(*condicoes)
        .group_by(categoria)
        .order_by(faturamento.desc().nulls_last(), categoria)
    ).all()
    fatias = [
        Fatia(nome, _decimal(fat).quantize(_CENTAVOS), notas, _decimal(qtd))
        for nome, fat, notas, qtd in linhas
    ]
    if len(fatias) <= CATEGORIAS_NO_GRAFICO:
        return fatias
    principais, resto = fatias[: CATEGORIAS_NO_GRAFICO - 1], fatias[CATEGORIAS_NO_GRAFICO - 1 :]

    outras = Fatia(
        OUTRAS_CATEGORIAS,
        sum((f.faturamento for f in resto), Decimal(0)),
        0,
        sum((f.quantidade for f in resto), Decimal(0)),
    )
    return [*principais, outras]


def _por_empresa(db: Session, condicoes: list[ColumnElement[bool]]) -> list[FatiaEmpresa]:
    faturamento = func.sum(Venda.valor_total)
    linhas = db.execute(
        select(Empresa, faturamento, func.count())
        .join(Empresa, Empresa.id == Venda.empresa_id)
        .where(*condicoes)
        .group_by(Empresa.id)
        .order_by(faturamento.desc(), Empresa.codigo)
    ).all()
    return [FatiaEmpresa(empresa, _decimal(fat), notas) for empresa, fat, notas in linhas]


def _produtos(db: Session, condicoes: list[ColumnElement[bool]]) -> list[ProdutoVendido]:
    faturamento = func.sum(VendaItem.valor_liquido)
    linhas = db.execute(
        select(
            VendaItem.id_produto,
            VendaItem.id_subproduto,
            func.coalesce(func.max(descricao_item()), func.max(VendaItem.descricao_produto)),
            func.sum(VendaItem.quantidade),
            faturamento,
        )
        .select_from(VendaItem)
        .join(Venda, Venda.id == VendaItem.venda_id)
        .outerjoin(Produto, _juncao_produto())
        .where(*condicoes)
        .group_by(VendaItem.id_produto, VendaItem.id_subproduto)
        .order_by(faturamento.desc().nulls_last(), VendaItem.id_produto)
        .limit(PRODUTOS_NO_RANKING)
    ).all()
    return [
        ProdutoVendido(id_p, id_s, descricao, _decimal(qtd), _decimal(fat).quantize(_CENTAVOS))
        for id_p, id_s, descricao, qtd, fat in linhas
    ]


def _vendedores(db: Session, filtro: FiltroVendas) -> RankingVendedores:
    condicoes = _condicoes(filtro, filtro.periodo)
    faturamento = func.sum(Venda.valor_total)
    linhas = db.execute(
        select(
            Venda.id_vendedor,
            faturamento,
            func.count(),
            func.array_agg(func.distinct(Venda.empresa_id)),
        )
        .where(*condicoes)
        .group_by(Venda.id_vendedor)
        .order_by(faturamento.desc(), Venda.id_vendedor)
    ).all()
    comparacao: dict[str, Decimal] | None = None
    if filtro.comparacao is not None:
        comparacao = {
            vendedor: _decimal(fat)
            for vendedor, fat in db.execute(
                select(Venda.id_vendedor, func.sum(Venda.valor_total))
                .where(*_condicoes(filtro, filtro.comparacao))
                .group_by(Venda.id_vendedor)
            )
            if vendedor is not None
        }
    ids_empresas = {e for *_, empresas in linhas for e in empresas}
    empresas = {
        e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_(ids_empresas))).all()
    }
    vendedores: list[FatiaVendedor] = []
    nomes: dict[str, str | None] = {
        id_erp: nome
        for id_erp, nome in db.execute(
            select(Vendedor.id_erp, Vendedor.nome).where(
                Vendedor.id_erp.in_([v for v, *_ in linhas if v is not None])
            )
        )
    }
    sem_faturamento, sem_notas = Decimal(0), 0
    for vendedor, fat, notas, ids in linhas:
        if vendedor is None or eh_vendedor_generico(nomes.get(vendedor)):
            sem_faturamento += _decimal(fat)
            sem_notas += notas
            continue
        vendedores.append(
            FatiaVendedor(
                vendedor,
                _decimal(fat),
                notas,
                sorted((empresas[i] for i in ids), key=lambda e: e.codigo),
                comparacao.get(vendedor, Decimal(0)) if comparacao is not None else None,
                nomes.get(vendedor),
            )
        )
    return RankingVendedores(vendedores, sem_faturamento, sem_notas)


def formas_pagamento(db: Session, filtro: FiltroVendas) -> list[FormaPagamento] | None:
    if filtro.canal is not None:
        return None
    valor = func.sum(VendaTitulo.valor)
    linhas = db.execute(
        select(VendaTitulo.forma, valor, func.count())
        .where(
            *_condicoes_sem_canal(
                filtro, filtro.periodo, VendaTitulo.empresa_id, VendaTitulo.dia_lancamento
            )
        )
        .group_by(VendaTitulo.forma)
        .order_by(valor.desc(), VendaTitulo.forma)
    ).all()
    return [FormaPagamento(forma, _decimal(v), int(p or 0)) for forma, v, p in linhas]


@dataclass(frozen=True)
class DescontoNota:
    dia: date
    momento: datetime | None
    id_vendedor: str | None
    nome_vendedor: str | None
    desconto: Decimal
    valor_nota: Decimal
    loja: str
    numero_nota: str | None
    canal: str


def descontos_por_nota(db: Session, filtro: FiltroVendas) -> list[DescontoNota]:
    linhas = db.execute(
        select(
            Venda.data_venda,
            Venda.momento,
            Venda.id_vendedor,
            Vendedor.nome,
            Venda.valor_desconto,
            Venda.valor_total,
            Empresa.nome,
            Venda.numero_nota,
            Venda.canal,
        )
        .join(Empresa, Empresa.id == Venda.empresa_id)
        .outerjoin(Vendedor, Vendedor.id_erp == Venda.id_vendedor)
        .where(*_condicoes(filtro, filtro.periodo), Venda.valor_desconto > 0)
        .order_by(Venda.data_venda, Venda.momento, Venda.numero_nota)
    ).all()
    return [DescontoNota(*linha) for linha in linhas]


def cobertura(db: Session, empresa: Empresa | None = None) -> Cobertura:
    filtro = [VendaDia.empresa_id == empresa.id] if empresa else []
    primeiros = (
        db.execute(select(func.min(VendaDia.dia)).where(*filtro).group_by(VendaDia.empresa_id))
        .scalars()
        .all()
    )
    ate, atualizado_em = db.execute(
        select(func.max(VendaDia.dia), func.max(VendaDia.sincronizado_em)).where(*filtro)
    ).one()
    return Cobertura(max(primeiros) if primeiros else None, ate, atualizado_em)


def resumo_vendas(db: Session, filtro: FiltroVendas) -> ResumoVendas:
    condicoes = _condicoes(filtro, filtro.periodo)
    granularidade, serie = _serie(db, filtro, condicoes)
    return ResumoVendas(
        gerado_em=datetime.now(UTC),
        totais=_totais_do_periodo(db, filtro, filtro.periodo),
        comparacao=(
            _totais_do_periodo(db, filtro, filtro.comparacao) if filtro.comparacao else None
        ),
        granularidade=granularidade,
        serie=serie,
        por_canal=_por_canal(db, condicoes, filtro.canal),
        por_categoria=_por_categoria(db, condicoes),
        por_empresa=_por_empresa(db, condicoes),
        produtos=_produtos(db, condicoes),
        cobertura=cobertura(db, filtro.empresa),
        vendedores=_vendedores(db, filtro),
        formas_pagamento=formas_pagamento(db, filtro),
    )
