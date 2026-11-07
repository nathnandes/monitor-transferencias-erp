import ipaddress
import socket
from collections.abc import Iterator
from contextlib import contextmanager

TENTATIVAS: list[str] = []


class RedeBloqueadaError(AssertionError):
    pass


def _eh_local(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    texto = str(host).strip().lower()
    if texto in {"", "localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(texto.split("%")[0]).is_loopback
    except ValueError:
        return False


def _recusar(host: object, porta: object = None) -> None:
    alvo = f"{host}:{porta}" if porta is not None else str(host)
    TENTATIVAS.append(alvo)
    raise RedeBloqueadaError(f"acesso a rede externa bloqueado nos testes: {alvo}")


def _host_do_endereco(familia: int, endereco: object) -> tuple[object, object] | None:
    if familia in (socket.AF_INET, socket.AF_INET6) and isinstance(endereco, tuple):
        return endereco[0], endereco[1] if len(endereco) > 1 else None
    return None


@contextmanager
def bloquear_rede_externa() -> Iterator[list[str]]:
    connect_original = socket.socket.connect
    connect_ex_original = socket.socket.connect_ex
    create_connection_original = socket.create_connection
    getaddrinfo_original = socket.getaddrinfo

    def connect(self: socket.socket, endereco, *args, **kwargs):
        alvo = _host_do_endereco(self.family, endereco)
        if alvo is not None and not _eh_local(alvo[0]):
            _recusar(*alvo)
        return connect_original(self, endereco, *args, **kwargs)

    def connect_ex(self: socket.socket, endereco, *args, **kwargs):
        alvo = _host_do_endereco(self.family, endereco)
        if alvo is not None and not _eh_local(alvo[0]):
            _recusar(*alvo)
        return connect_ex_original(self, endereco, *args, **kwargs)

    def create_connection(endereco, *args, **kwargs):
        if not _eh_local(endereco[0]):
            _recusar(endereco[0], endereco[1])
        return create_connection_original(endereco, *args, **kwargs)

    def getaddrinfo(host, porta, *args, **kwargs):
        if not _eh_local(host):
            _recusar(host, porta)
        return getaddrinfo_original(host, porta, *args, **kwargs)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.create_connection = create_connection  # type: ignore[assignment]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    try:
        yield TENTATIVAS
    finally:
        socket.socket.connect = connect_original  # type: ignore[method-assign]
        socket.socket.connect_ex = connect_ex_original  # type: ignore[method-assign]
        socket.create_connection = create_connection_original  # type: ignore[assignment]
        socket.getaddrinfo = getaddrinfo_original  # type: ignore[assignment]
