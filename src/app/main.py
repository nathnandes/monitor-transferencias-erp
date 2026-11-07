from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api import health, v1
from app.api.autenticacao import criar_contexto_auth
from app.api.erros import validacao_sem_segredos
from app.api.middleware import MiddlewareRequisicao
from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

_DESCRICAO = """\
Monitoramento de processos do ERP via ERPAPI.

API interna: a consulta é **somente leitura** e lê apenas o PostgreSQL próprio.

**Autenticação no /docs:** chame `POST /api/v1/auth/login`, copie o `access_token`
da resposta, clique em **Authorize** e cole só o token (sem a palavra `Bearer`).
As rotas com cadeado passam a enviar `Authorization: Bearer <token>`.

**Permissões:** `/dashboard/*` e `/empresas` exigem o módulo `DASHBOARD`;
`/transferencias` exige `TRANSFERENCIAS`; `/admin/users` exige papel `ADMIN` e o módulo
`ADMINISTRACAO`. Sem token (ou token inválido): **401**.
Token válido sem o módulo: **403**. Veja os seus em `GET /api/v1/auth/permissions`.
Públicos: `/health/live`, `/health/ready` e `POST /api/v1/auth/login`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "iniciando %s | env=%s | tz=%s",
        settings.app_name,
        settings.app_env,
        settings.tz,
    )
    yield
    logger.info("encerrando %s", settings.app_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title="ERP Automation",
        description=_DESCRICAO,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings

    app.state.auth = criar_contexto_auth(settings)

    app.add_exception_handler(RequestValidationError, validacao_sem_segredos)  # type: ignore[arg-type]
    app.add_middleware(MiddlewareRequisicao)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
