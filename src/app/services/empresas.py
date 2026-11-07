from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Empresa


def listar_empresas(db: Session, ativo: bool | None = None) -> Sequence[Empresa]:
    stmt = select(Empresa).order_by(Empresa.codigo)
    if ativo is not None:
        stmt = stmt.where(Empresa.ativo == ativo)
    return db.scalars(stmt).all()
