import argparse
import signal
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger, setup_logging
from app.notifications.enviador import Enviador
from app.notifications.outbox import ResultadoDespacho, processar_pendentes
from app.notifications.resumo_diario import processar_resumo_diario
from app.rules.motor import ResultadoAvaliacao, avaliar
from app.services import estoque_baixo, mensagens_avulsas, metas

logger = get_logger(__name__)


@dataclass
class ResultadoCiclo:
    avaliacao: ResultadoAvaliacao
    despacho: ResultadoDespacho | None

    resumo: str | None = None
    despacho_whatsapp: ResultadoDespacho | None = None


def _agora() -> datetime:
    return datetime.now(UTC)


def executar_ciclo(
    fabrica_sessao: Callable[[], Session],
    enviador: Enviador | None,
    tz: ZoneInfo,
    agora: Callable[[], datetime] = _agora,
    settings: Settings | None = None,
    whatsapp: Enviador | None = None,
) -> ResultadoCiclo:
    with fabrica_sessao() as db, db.begin():
        avaliacao = avaliar(db, agora())
    try:
        with fabrica_sessao() as db, db.begin():
            metas.avaliar_avisos(db, agora(), tz)
    except Exception:
        logger.exception("avisos de meta falharam neste ciclo")
    try:
        with fabrica_sessao() as db, db.begin():
            mensagens_avulsas.gerar_repetidas(db, agora(), tz)
    except Exception:
        logger.exception("mensagens repetidas falharam neste ciclo")
    try:
        with fabrica_sessao() as db, db.begin():
            estoque_baixo.processar(db, agora(), tz)
    except Exception:
        logger.exception("resumo de estoque baixo falhou neste ciclo")

    despacho = None
    resumo = None
    if enviador is not None:
        with fabrica_sessao() as db, db.begin():
            despacho = processar_pendentes(db, enviador, agora(), tz)
        if settings is not None:
            try:
                with fabrica_sessao() as db, db.begin():
                    resumo = processar_resumo_diario(db, enviador, agora(), settings)
            except Exception:
                logger.exception("resumo diario falhou neste ciclo")
    despacho_whatsapp = None
    if whatsapp is not None:
        try:
            with fabrica_sessao() as db, db.begin():
                despacho_whatsapp = processar_pendentes(db, whatsapp, agora(), tz)
        except Exception:
            logger.exception("despacho do WhatsApp falhou neste ciclo")
    return ResultadoCiclo(avaliacao, despacho, resumo, despacho_whatsapp)


def rodar(
    settings: Settings,
    fabrica_sessao: Callable[[], Session],
    enviador: Enviador | None,
    parar: threading.Event,
    uma_vez: bool = False,
    whatsapp: Enviador | None = None,
) -> None:
    tz = ZoneInfo(settings.tz)
    while not parar.is_set():
        try:
            executar_ciclo(fabrica_sessao, enviador, tz, settings=settings, whatsapp=whatsapp)
        except Exception:
            logger.exception("ciclo do monitor falhou")
        if uma_vez:
            return
        parar.wait(settings.monitor_interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker de monitoramento (regras + alertas)")
    parser.add_argument("--uma-vez", action="store_true", help="roda um ciclo e sai")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    from app.database.session import SessionLocal
    from app.telegram.cliente import criar_enviador
    from app.whatsapp.cliente import criar_enviador as criar_enviador_whatsapp

    enviador = criar_enviador(settings)
    whatsapp = criar_enviador_whatsapp(settings)
    logger.info(
        "monitor iniciando | intervalo=%ss | telegram=%s | whatsapp=%s",
        settings.monitor_interval_seconds,
        "ligado" if enviador else "desligado",
        "ligado" if whatsapp else "desligado",
    )

    parar = threading.Event()

    def _sinal(numero: int, _frame: object) -> None:
        logger.info("sinal %s recebido: encerrando apos o ciclo atual", numero)
        parar.set()

    signal.signal(signal.SIGINT, _sinal)
    signal.signal(signal.SIGTERM, _sinal)

    try:
        rodar(settings, SessionLocal, enviador, parar, uma_vez=args.uma_vez, whatsapp=whatsapp)
    finally:
        for canal in (enviador, whatsapp):
            if canal is not None:
                canal.close()
    logger.info("monitor encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
