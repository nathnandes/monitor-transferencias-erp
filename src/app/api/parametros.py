from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Empresa
from app.dominio.intervalo import Intervalo, IntervaloInvalido


def intervalo_de(
    nome_inicio: str, inicio: date | None, nome_fim: str, fim: date | None
) -> Intervalo | None:
    if inicio is None and fim is None:
        return None
    if inicio is None or fim is None:
        raise IntervaloInvalido(f"Informe `{nome_inicio}` e `{nome_fim}` juntos.")
    return Intervalo(inicio, fim)


def empresa_por_codigo(db: Session, codigo: str) -> Empresa:
    empresa = db.scalar(select(Empresa).where(Empresa.codigo == codigo))
    if empresa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Empresa {codigo} não encontrada.")
    return empresa
