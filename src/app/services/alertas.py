from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, joinedload

from app.database.models import SEVERIDADES_EVENTO, Alerta, Empresa


@dataclass(frozen=True)
class FiltrosAlerta:
    status: str | None = None
    severidade: str | None = None
    empresa: str | None = None


@dataclass(frozen=True)
class Pagina:
    total: int
    itens: Sequence[Alerta]


def _condicoes(filtros: FiltrosAlerta) -> list[ColumnElement[bool]]:
    condicoes: list[ColumnElement[bool]] = []
    if filtros.status:
        condicoes.append(Alerta.status == filtros.status)
    if filtros.severidade:
        condicoes.append(Alerta.severidade == filtros.severidade)
    if filtros.empresa:
        condicoes.append(
            Alerta.empresa_id.in_(select(Empresa.id).where(Empresa.codigo == filtros.empresa))
        )
    return condicoes


def listar_alertas(
    db: Session, filtros: FiltrosAlerta, *, pagina: int, tamanho_pagina: int
) -> Pagina:
    condicoes = _condicoes(filtros)
    total = db.scalar(select(func.count()).select_from(Alerta).where(*condicoes)) or 0
    itens = db.scalars(
        select(Alerta)
        .options(joinedload(Alerta.empresa), joinedload(Alerta.transferencia))
        .where(*condicoes)
        .order_by((Alerta.status == "ABERTO").desc(), Alerta.aberto_em.desc(), Alerta.id.desc())
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
    ).all()
    return Pagina(total=total, itens=itens)


def contar_abertos(db: Session) -> dict[str, int]:
    linhas = db.execute(
        select(Alerta.severidade, func.count())
        .where(Alerta.status == "ABERTO")
        .group_by(Alerta.severidade)
    ).all()
    contagem = dict.fromkeys(SEVERIDADES_EVENTO, 0)
    contagem.update({severidade: total for severidade, total in linhas})
    return contagem
