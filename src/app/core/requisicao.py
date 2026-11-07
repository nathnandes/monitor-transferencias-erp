from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_ip_cliente: ContextVar[str | None] = ContextVar("ip_cliente", default=None)


def request_id_atual() -> str | None:
    return _request_id.get()


def definir_request_id(valor: str | None) -> Token[str | None]:
    return _request_id.set(valor)


def restaurar_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def ip_cliente_atual() -> str | None:
    return _ip_cliente.get()


def definir_ip_cliente(valor: str | None) -> Token[str | None]:
    return _ip_cliente.set(valor)


def restaurar_ip_cliente(token: Token[str | None]) -> None:
    _ip_cliente.reset(token)
