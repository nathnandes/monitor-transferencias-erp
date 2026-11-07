from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

CAMPOS_SENSIVEIS = {
    "password",
    "current_password",
    "new_password",
    "password_temporaria",
    "password_hash",
    "senha",
}
PREFIXOS_SENSIVEIS = ("/api/v1/auth", "/api/v1/admin")


def _sensivel(request: Request, erro: dict[str, Any]) -> bool:
    return request.url.path.startswith(PREFIXOS_SENSIVEIS) or any(
        str(parte) in CAMPOS_SENSIVEIS for parte in erro.get("loc", ())
    )


async def validacao_sem_segredos(request: Request, exc: RequestValidationError) -> JSONResponse:
    erros = list(exc.errors())
    if not any(_sensivel(request, e) for e in erros):
        return await request_validation_exception_handler(request, exc)

    limpos = [
        {k: v for k, v in e.items() if k not in {"input", "ctx", "url"}}
        if _sensivel(request, e)
        else e
        for e in erros
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(limpos)})
