from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api import schemas
from app.api.autorizacao import exigir_modulo
from app.api.deps import SessionLeituraDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.dominio.modulos import Modulo
from app.services import empresas as service

router = APIRouter(
    tags=["empresas"],
    dependencies=[Depends(exigir_modulo(Modulo.DASHBOARD))],
    responses=RESPOSTAS_PROTEGIDAS,
)


@router.get("/empresas", summary="Lista as empresas, ordenadas por código")
def listar_empresas(
    db: SessionLeituraDep,
    ativo: Annotated[bool | None, Query(description="Filtra por empresas ativas/inativas.")] = None,
) -> list[schemas.Empresa]:
    return [schemas.Empresa.model_validate(e) for e in service.listar_empresas(db, ativo)]
