from math import ceil
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api import schemas
from app.api.autorizacao import exigir_modulo
from app.api.deps import SessionLeituraDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.dominio.modulos import Modulo
from app.services import alertas as service

router = APIRouter(
    tags=["alertas"],
    dependencies=[Depends(exigir_modulo(Modulo.ALERTAS))],
    responses=RESPOSTAS_PROTEGIDAS,
)

TAMANHO_PAGINA_MAXIMO = 100


@router.get(
    "/alertas",
    summary="Lista alertas com filtros e paginação",
    description="Ordenação: abertos primeiro; depois o aberto mais recentemente.",
)
def listar_alertas(
    db: SessionLeituraDep,
    status_: Annotated[
        schemas.StatusAlerta | None, Query(alias="status", description="ABERTO ou RESOLVIDO.")
    ] = None,
    severidade: Annotated[schemas.Severidade | None, Query()] = None,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["01"])] = None,
    pagina: Annotated[int, Query(ge=1, description="Página, começando em 1.")] = 1,
    tamanho_pagina: Annotated[
        int, Query(ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Itens por página.")
    ] = 20,
) -> schemas.PaginaAlertas:
    filtros = service.FiltrosAlerta(status=status_, severidade=severidade, empresa=empresa)
    resultado = service.listar_alertas(db, filtros, pagina=pagina, tamanho_pagina=tamanho_pagina)
    return schemas.PaginaAlertas(
        total=resultado.total,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
        total_paginas=ceil(resultado.total / tamanho_pagina),
        itens=[schemas.Alerta.model_validate(a) for a in resultado.itens],
    )


@router.get("/alertas/resumo", summary="Quantos alertas estão abertos, por severidade")
def resumo_alertas(db: SessionLeituraDep) -> schemas.ResumoAlertas:
    contagem = service.contar_abertos(db)
    return schemas.ResumoAlertas(abertos=sum(contagem.values()), por_severidade=contagem)
