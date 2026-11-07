import logging
import threading
from typing import Any

from app.core.mascaramento import mascarar_texto

LOGGER_NOME = "app.erp.erpapi"
MASCARA = "***"


CAMPOS_PERMITIDOS = frozenset(
    {
        "rota",
        "metodo",
        "status",
        "duracao_ms",
        "pagina",
        "tem_proxima",
        "registros",
        "tentativa",
        "validade_s",
        "erro",
        "motivo",
        "base_url",
    }
)


class MascaradorSegredos:
    def __init__(self) -> None:
        self._valores: set[str] = set()
        self._lock = threading.Lock()

    def registrar(self, valor: str) -> None:

        if valor and len(valor) >= 4:
            with self._lock:
                self._valores.add(valor)

    def mascarar(self, texto: str) -> str:
        with self._lock:
            valores = sorted(self._valores, key=len, reverse=True)
        for valor in valores:
            if valor in texto:
                texto = texto.replace(valor, MASCARA)
        return mascarar_texto(texto)


class FiltroSegredos(logging.Filter):
    def __init__(self, mascarador: MascaradorSegredos) -> None:
        super().__init__()
        self._mascarador = mascarador

    def filter(self, record: logging.LogRecord) -> bool:
        mensagem = record.getMessage()
        limpa = self._mascarador.mascarar(mensagem)
        if limpa != mensagem:
            record.msg = limpa
            record.args = None
        return True


MASCARADOR = MascaradorSegredos()
logger = logging.getLogger(LOGGER_NOME)
if not any(isinstance(f, FiltroSegredos) for f in logger.filters):
    logger.addFilter(FiltroSegredos(MASCARADOR))


def registrar(nivel: int, evento: str, **campos: Any) -> None:
    proibidos = set(campos) - CAMPOS_PERMITIDOS
    if proibidos:
        raise ValueError(f"campos nao permitidos em log do ERPAPI: {sorted(proibidos)}")
    if not logger.isEnabledFor(nivel):
        return
    pares = " ".join(f"{k}={v}" for k, v in campos.items())
    mensagem = f"erpapi.{evento}" + (f" {pares}" if pares else "")
    logger.log(nivel, mensagem, extra={"erpapi": {"evento": evento, **campos}})
