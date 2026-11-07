from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep, SettingsDep
from app.api.schemas import HealthLive, HealthReady
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness — não depende do banco")
def live(settings: SettingsDep) -> HealthLive:
    return HealthLive(status="ok", app=settings.app_name, env=settings.app_env)


router.add_api_route("/health", live, methods=["GET"], include_in_schema=False)


@router.get(
    "/health/ready",
    summary="Readiness — verifica o banco",
    response_model=HealthReady,
    responses={503: {"model": HealthReady, "description": "Banco inacessível."}},
)
def ready(session: SessionDep) -> Any:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("readiness falhou: banco inacessivel (%s)", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "indisponivel", "database": "erro"},
        )

    return HealthReady(status="ok", database="ok")
