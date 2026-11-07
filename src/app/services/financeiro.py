from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import ColumnElement, and_, func, literal, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.database.models import Empresa, VendaTitulo
from app.dominio.intervalo import Intervalo
from app.services.vendas import Cobertura, cobertura


@dataclass(frozen=True)
class FormaVendida:
    forma: str
    valor: Decimal
    valor_pago: Decimal
    valor_pendente: Decimal
    parcelas: int


@dataclass(frozen=True)
class VendasPagas:
    valor: Decimal
    valor_pago: Decimal
    valor_pendente: Decimal
    parcelas: int
    formas: list[FormaVendida]


@dataclass(frozen=True)
class FormaRecebida:
    forma: str
    valor: Decimal
    titulos: int


@dataclass(frozen=True)
class Recebidos:
    total: Decimal

    de_vendas_anteriores: Decimal

    de_boletos: Decimal
    das_vendas_do_periodo: Decimal
    outros_anteriores: Decimal
    juros: Decimal
    titulos: int
    formas: list[FormaRecebida]


@dataclass(frozen=True)
class ResumoFinanceiro:
    gerado_em: datetime
    vendas: VendasPagas
    recebidos: Recebidos
    cobertura: Cobertura


def _decimal(valor: object) -> Decimal:
    return Decimal(str(valor)) if valor is not None else Decimal(0)


def _e_boleto() -> ColumnElement[bool]:
    return func.upper(VendaTitulo.forma).like("BOLETO%")


def _condicoes(
    empresa: Empresa | None,
    periodo: Intervalo | None,
    coluna_data: InstrumentedAttribute[date] | InstrumentedAttribute[date | None],
) -> list[ColumnElement[bool]]:
    condicoes: list[ColumnElement[bool]] = []
    if empresa is not None:
        condicoes.append(VendaTitulo.empresa_id == empresa.id)
    if periodo is not None:
        condicoes.append(coluna_data.between(periodo.inicio, periodo.fim))
    return condicoes


def _vendas(db: Session, empresa: Empresa | None, periodo: Intervalo | None) -> VendasPagas:
    valor = func.sum(VendaTitulo.valor)
    linhas = db.execute(
        select(
            VendaTitulo.forma,
            valor,
            func.sum(VendaTitulo.valor_pago),
            func.sum(VendaTitulo.valor_pendente),
            func.count(),
        )
        .where(*_condicoes(empresa, periodo, VendaTitulo.dia_lancamento))
        .group_by(VendaTitulo.forma)
        .order_by(valor.desc(), VendaTitulo.forma)
    ).all()
    formas = [
        FormaVendida(forma, _decimal(v), _decimal(pago), _decimal(pendente), int(n or 0))
        for forma, v, pago, pendente, n in linhas
    ]
    return VendasPagas(
        valor=sum((f.valor for f in formas), Decimal(0)),
        valor_pago=sum((f.valor_pago for f in formas), Decimal(0)),
        valor_pendente=sum((f.valor_pendente for f in formas), Decimal(0)),
        parcelas=sum(f.parcelas for f in formas),
        formas=formas,
    )


def _recebidos(db: Session, empresa: Empresa | None, periodo: Intervalo | None) -> Recebidos:
    valor = func.sum(VendaTitulo.valor_pago)
    pago = VendaTitulo.valor_pago
    lancado_fora = (
        ~VendaTitulo.dia_lancamento.between(periodo.inicio, periodo.fim)
        if periodo is not None
        else literal(False)
    )
    boleto = _e_boleto()
    linhas = db.execute(
        select(
            VendaTitulo.forma,
            valor,
            func.count(),
            func.sum(VendaTitulo.juros),
            func.coalesce(func.sum(pago).filter(lancado_fora), 0),
            func.coalesce(func.sum(pago).filter(boleto), 0),
            func.coalesce(func.sum(pago).filter(~boleto, lancado_fora), 0),
        )
        .where(
            and_(VendaTitulo.dia_pagamento.is_not(None), VendaTitulo.valor_pago > 0),
            *_condicoes(empresa, periodo, VendaTitulo.dia_pagamento),
        )
        .group_by(VendaTitulo.forma)
        .order_by(valor.desc(), VendaTitulo.forma)
    ).all()

    def soma(i: int) -> Decimal:
        return sum((_decimal(linha[i]) for linha in linhas), Decimal(0))

    total, de_boletos, outros = soma(1), soma(5), soma(6)
    return Recebidos(
        total=total,
        de_vendas_anteriores=soma(4),
        de_boletos=de_boletos,
        das_vendas_do_periodo=total - de_boletos - outros,
        outros_anteriores=outros,
        juros=soma(3),
        titulos=sum(int(linha[2] or 0) for linha in linhas),
        formas=[
            FormaRecebida(linha[0], _decimal(linha[1]), int(linha[2] or 0)) for linha in linhas
        ],
    )


def resumo_financeiro(
    db: Session, empresa: Empresa | None, periodo: Intervalo | None
) -> ResumoFinanceiro:
    return ResumoFinanceiro(
        gerado_em=datetime.now(UTC),
        vendas=_vendas(db, empresa, periodo),
        recebidos=_recebidos(db, empresa, periodo),
        cobertura=cobertura(db, empresa),
    )


DataParcela = Literal["lancamento", "pagamento"]
SituacaoParcela = Literal["todas", "pagas", "pendentes"]


@dataclass(frozen=True)
class Parcela:
    empresa_codigo: str
    empresa_nome: str
    documento: str
    titulo: str
    parcela: str
    forma: str
    dia_lancamento: date
    vencimento: date | None
    dia_pagamento: date | None
    valor: Decimal
    valor_pago: Decimal
    valor_pendente: Decimal
    juros: Decimal
    desconto: Decimal


@dataclass(frozen=True)
class PaginaParcelas:
    total: int
    valor: Decimal
    valor_pago: Decimal
    valor_pendente: Decimal
    itens: list[Parcela]


def _filtro_parcelas(
    empresa: Empresa | None,
    periodo: Intervalo | None,
    data_por: DataParcela,
    situacao: SituacaoParcela,
    forma: str | None,
) -> list[ColumnElement[bool]]:
    coluna = VendaTitulo.dia_pagamento if data_por == "pagamento" else VendaTitulo.dia_lancamento
    condicoes = _condicoes(empresa, periodo, coluna)
    if data_por == "pagamento":
        condicoes += [VendaTitulo.dia_pagamento.is_not(None), VendaTitulo.valor_pago > 0]
    if situacao == "pagas":
        condicoes.append(VendaTitulo.valor_pendente <= 0)
    elif situacao == "pendentes":
        condicoes.append(VendaTitulo.valor_pendente > 0)
    if forma:
        condicoes.append(VendaTitulo.forma == forma)
    return condicoes


def listar_parcelas(
    db: Session,
    empresa: Empresa | None,
    periodo: Intervalo | None,
    *,
    data_por: DataParcela = "lancamento",
    situacao: SituacaoParcela = "todas",
    forma: str | None = None,
    pagina: int = 1,
    tamanho_pagina: int = 50,
) -> PaginaParcelas:
    condicoes = _filtro_parcelas(empresa, periodo, data_por, situacao, forma)
    total, valor, pago, pendente = db.execute(
        select(
            func.count(),
            func.sum(VendaTitulo.valor),
            func.sum(VendaTitulo.valor_pago),
            func.sum(VendaTitulo.valor_pendente),
        ).where(*condicoes)
    ).one()
    coluna = VendaTitulo.dia_pagamento if data_por == "pagamento" else VendaTitulo.dia_lancamento
    linhas = db.execute(
        select(VendaTitulo, Empresa.codigo, Empresa.nome)
        .join(Empresa, Empresa.id == VendaTitulo.empresa_id)
        .where(*condicoes)
        .order_by(
            coluna.desc().nulls_last(),
            Empresa.codigo,
            VendaTitulo.id_planilha,
            VendaTitulo.id_titulo,
            VendaTitulo.parcela,
        )
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    itens = [
        Parcela(
            empresa_codigo=codigo,
            empresa_nome=nome,
            documento=t.id_planilha,
            titulo=t.id_titulo,
            parcela=t.parcela,
            forma=t.forma,
            dia_lancamento=t.dia_lancamento,
            vencimento=t.vencimento,
            dia_pagamento=t.dia_pagamento,
            valor=t.valor,
            valor_pago=t.valor_pago,
            valor_pendente=t.valor_pendente,
            juros=t.juros,
            desconto=t.desconto,
        )
        for t, codigo, nome in linhas
    ]
    return PaginaParcelas(
        total=int(total or 0),
        valor=_decimal(valor),
        valor_pago=_decimal(pago),
        valor_pendente=_decimal(pendente),
        itens=itens,
    )
