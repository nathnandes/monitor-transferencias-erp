from sqlalchemy import ColumnElement

from app.database.models import Transferencia


def condicao_entre_empresas() -> ColumnElement[bool]:
    return Transferencia.entre_empresas.is_(True)
