from dataclasses import dataclass

from sqlalchemy import ColumnElement, false, or_, select

from app.core.config import get_settings
from app.database.models import Empresa, EstoqueEmpresaLocalLote


@dataclass(frozen=True)
class LocalPerda:
    empresa: str
    local: str
    motivo: str


def locais_de_perda() -> tuple[LocalPerda, ...]:
    return tuple(LocalPerda(*x) for x in get_settings().locais_perda)


def em_local_de_perda(
    e: type[EstoqueEmpresaLocalLote] = EstoqueEmpresaLocalLote,
) -> ColumnElement[bool]:
    condicoes = [
        e.empresa_id.in_(select(Empresa.id).where(Empresa.codigo == x.empresa))
        & (e.id_local_estoque == x.local)
        for x in locais_de_perda()
    ]
    return or_(*condicoes) if condicoes else false()


def fora_da_perda(
    e: type[EstoqueEmpresaLocalLote] = EstoqueEmpresaLocalLote,
) -> ColumnElement[bool]:
    return ~em_local_de_perda(e)


def motivo_perda(linha: EstoqueEmpresaLocalLote) -> str | None:
    for x in locais_de_perda():
        if linha.empresa.codigo == x.empresa and linha.id_local_estoque == x.local:
            return x.motivo
    return None
