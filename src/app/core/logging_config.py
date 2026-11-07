import json
import logging
import sys
from datetime import UTC, datetime

from app.core.mascaramento import mascarar_texto
from app.core.requisicao import request_id_atual

_FORMATO = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

_configurado = False


class FormatterMascarado(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        texto = super().format(record)
        rid = request_id_atual()
        if rid:
            texto = f"{texto} [req={rid}]"
        return mascarar_texto(texto)


_ATRIBUTOS_PADRAO = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class FormatterJson(FormatterMascarado):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_atual()
        if rid:
            evento["request_id"] = rid
        for chave, valor in vars(record).items():
            if chave not in _ATRIBUTOS_PADRAO and not chave.startswith("_"):
                evento[chave] = valor
        if record.exc_info:
            evento["excecao"] = self.formatException(record.exc_info)
        return mascarar_texto(json.dumps(evento, ensure_ascii=False, default=str))


def setup_logging(level: str = "INFO", formato: str = "texto") -> None:
    global _configurado
    if _configurado:
        return

    handler = logging.StreamHandler(sys.stdout)
    if formato == "json":
        handler.setFormatter(FormatterJson())
    else:
        handler.setFormatter(FormatterMascarado(fmt=_FORMATO, datefmt=_FORMATO_DATA))

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]

    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(nome)
        logger.handlers = []
        logger.propagate = True

    for nome in ("httpx2", "httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)

    _configurado = True


def get_logger(nome: str) -> logging.Logger:
    return logging.getLogger(nome)
