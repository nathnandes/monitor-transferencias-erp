import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import get_logger
from app.core.requisicao import (
    definir_ip_cliente,
    definir_request_id,
    restaurar_ip_cliente,
    restaurar_request_id,
)

logger = get_logger("app.http")

HEADER = b"x-request-id"
_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _id_recebido(scope: Scope) -> str | None:
    for nome, valor in scope.get("headers", []):
        if nome == HEADER:
            texto = valor.decode("latin-1")
            return texto if _ID_VALIDO.match(texto) else None
    return None


class MiddlewareRequisicao:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _id_recebido(scope) or uuid.uuid4().hex
        token = definir_request_id(rid)
        cliente = scope.get("client")
        token_ip = definir_ip_cliente(cliente[0] if cliente else None)
        inicio = time.perf_counter()
        status_code = 500

        async def enviar(mensagem: Message) -> None:
            nonlocal status_code
            if mensagem["type"] == "http.response.start":
                status_code = mensagem["status"]
                mensagem["headers"] = [*mensagem.get("headers", []), (HEADER, rid.encode())]
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        finally:
            caminho = scope.get("path", "")
            if not caminho.startswith("/health"):
                metodo = scope.get("method", "")
                duracao_ms = round((time.perf_counter() - inicio) * 1000, 1)
                logger.info(
                    "%s %s %s %.1fms",
                    metodo,
                    caminho,
                    status_code,
                    duracao_ms,
                    extra={
                        "metodo": metodo,
                        "caminho": caminho,
                        "status": status_code,
                        "duracao_ms": duracao_ms,
                    },
                )
            restaurar_ip_cliente(token_ip)
            restaurar_request_id(token)
