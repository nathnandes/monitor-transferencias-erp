from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.database.models import (
    Empresa,
    MovimentoEstoque,
    MovimentoEstoqueDia,
    Produto,
    Sincronizacao,
)
from app.dominio.intervalo import Intervalo
from app.services.balancos_estoque import produto_com_asterisco
from app.services.estoque import descricao_item

TipoMovimento = Literal["entrada_avulsa", "saida_avulsa", "balanco"]

FiltroTipo = Literal["entrada_avulsa", "saida_avulsa", "balanco", "avulsas"]

COI_ENTRADA_AVULSA = 80
COI_SAIDA_AVULSA = 8080
COI_BALANCO = 2000

TIPOS: dict[int, TipoMovimento] = {
    COI_ENTRADA_AVULSA: "entrada_avulsa",
    COI_SAIDA_AVULSA: "saida_avulsa",
    COI_BALANCO: "balanco",
}


TIPO_SINCRONIZACAO = "movimentos_estoque"


@dataclass(frozen=True)
class FiltrosMovimentos:
    periodo: Intervalo | None = None
    empresa: Empresa | None = None
    tipo: FiltroTipo | None = None
    produto: str | None = None
    subproduto: str | None = None

    sem_asterisco: bool = False


@dataclass(frozen=True)
class LinhaMovimento:
    movimento: MovimentoEstoque
    empresa: Empresa

    descricao: str | None


@dataclass(frozen=True)
class PaginaMovimentos:
    total: int
    itens: Sequence[LinhaMovimento]


@dataclass(frozen=True)
class ResumoDia:
    empresa: Empresa
    dia: date
    tipo: TipoMovimento
    itens: int
    quantidade: Decimal | None
    valor: Decimal | None
    falta_itens: int
    falta_quantidade: Decimal | None
    falta_valor: Decimal | None
    sobra_itens: int
    sobra_quantidade: Decimal | None
    sobra_valor: Decimal | None


@dataclass(frozen=True)
class Cobertura:
    desde: date | None
    ate: date | None
    atualizado_em: datetime | None


def _ordem_codigo(coluna: Any) -> list[Any]:
    return [func.length(coluna), coluna]


def _condicoes(f: FiltrosMovimentos) -> list[ColumnElement[bool]]:
    m = MovimentoEstoque

    condicoes: list[ColumnElement[bool]] = [m.coi.in_(TIPOS)]
    if f.periodo:
        condicoes += [m.dia >= f.periodo.inicio, m.dia <= f.periodo.fim]
    if f.empresa:
        condicoes.append(m.empresa_id == f.empresa.id)
    if f.tipo == "avulsas":
        condicoes.append(m.coi.in_((COI_ENTRADA_AVULSA, COI_SAIDA_AVULSA)))
    elif f.tipo:
        condicoes.append(m.tipo == f.tipo)
    if f.produto:
        condicoes.append(or_(m.id_produto == f.produto, m.id_subproduto == f.produto))
    if f.subproduto:
        condicoes.append(m.id_subproduto == f.subproduto)
    if f.sem_asterisco:
        condicoes.append(~produto_com_asterisco())
    return condicoes


def listar_movimentos(
    db: Session, f: FiltrosMovimentos, *, pagina: int, tamanho_pagina: int
) -> PaginaMovimentos:
    m = MovimentoEstoque
    condicoes = _condicoes(f)
    total = db.scalar(select(func.count()).select_from(m).where(*condicoes)) or 0
    linhas = db.execute(
        select(m, Empresa, func.coalesce(m.descricao_produto, descricao_item()))
        .join(Empresa, Empresa.id == m.empresa_id)
        .outerjoin(
            Produto,
            (Produto.id_produto == m.id_produto) & (Produto.id_subproduto == m.id_subproduto),
        )
        .where(*condicoes)
        .order_by(
            m.dia.desc(),
            *_ordem_codigo(Empresa.codigo),
            m.tipo,
            *_ordem_codigo(m.id_planilha),
            *_ordem_codigo(m.sequencia),
            m.id,
        )
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    return PaginaMovimentos(
        total=total, itens=[LinhaMovimento(mov, emp, desc) for mov, emp, desc in linhas]
    )


def resumo_por_dia(db: Session, f: FiltrosMovimentos) -> list[ResumoDia]:
    m = MovimentoEstoque
    falta = m.quantidade < 0
    sobra = m.quantidade > 0
    valor = m.valor
    linhas = db.execute(
        select(
            m.empresa_id,
            m.dia,
            m.tipo,
            func.count(),
            func.sum(m.quantidade),
            func.sum(valor),
            func.count().filter(falta),
            func.sum(m.quantidade).filter(falta),
            func.sum(valor).filter(falta),
            func.count().filter(sobra),
            func.sum(m.quantidade).filter(sobra),
            func.sum(valor).filter(sobra),
        )
        .where(*_condicoes(f), m.quantidade != 0)
        .group_by(m.empresa_id, m.dia, m.tipo)
    ).all()
    if not linhas:
        return []
    empresas = {
        e.id: e
        for e in db.scalars(select(Empresa).where(Empresa.id.in_({linha[0] for linha in linhas})))
    }
    resumo = [
        ResumoDia(empresas[empresa_id], dia, cast(TipoMovimento, tipo), *numeros)
        for empresa_id, dia, tipo, *numeros in linhas
    ]
    resumo.sort(
        key=lambda r: (
            -r.dia.toordinal(),
            len(r.empresa.codigo),
            r.empresa.codigo,
            r.tipo,
        )
    )
    return resumo


def cobertura(db: Session) -> Cobertura:
    desde, ate = db.execute(
        select(func.min(MovimentoEstoqueDia.dia), func.max(MovimentoEstoqueDia.dia))
    ).one()
    atualizado_em = db.scalar(
        select(func.max(Sincronizacao.fim)).where(
            Sincronizacao.tipo == TIPO_SINCRONIZACAO,
            Sincronizacao.empresa_id.is_(None),
            Sincronizacao.sincronizacao_pai_id.is_(None),
            Sincronizacao.status.in_(("sucesso", "parcial")),
        )
    )
    return Cobertura(desde=desde, ate=ate, atualizado_em=atualizado_em)
