import argparse
import signal
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast, get_args
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger, setup_logging
from app.services import sincronizacao as pedidos
from app.sync import (
    ResultadoSincronizacao,
    TipoSincronizacao,
    erpapi_habilitado,
    executar,
    trava_sincronizacao,
)

logger = get_logger(__name__)

Fabrica = Callable[[], Session]
Executor = Callable[[TipoSincronizacao], ResultadoSincronizacao]


def _agora() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Agendado:
    tipo: TipoSincronizacao
    gatilho: Callable[[Settings], int | str]
    diario: bool = False

    def intervalo(self, settings: Settings) -> int:
        valor = self.gatilho(settings)
        assert isinstance(valor, int)
        return valor

    def horario(self, settings: Settings) -> str:
        valor = self.gatilho(settings)
        assert isinstance(valor, str)
        return valor


AGENDA: tuple[Agendado, ...] = (
    Agendado("empresas", lambda s: s.sync_empresas_intervalo_segundos),
    Agendado("transferencias", lambda s: s.sync_transferencias_intervalo_segundos),
    Agendado("estoque_completo", lambda s: s.sync_estoque_completo_horario, diario=True),
    Agendado("estoque", lambda s: s.sync_estoque_intervalo_segundos),
    Agendado("precos_completo", lambda s: s.sync_precos_completo_horario, diario=True),
    Agendado("precos", lambda s: s.sync_precos_intervalo_segundos),
    Agendado("vendas", lambda s: s.sync_vendas_intervalo_segundos),
    Agendado("movimentos_estoque", lambda s: s.sync_movimentos_intervalo_segundos),
)


def executar_ciclo(
    fabrica: Fabrica,
    executor: Executor,
    settings: Settings,
    *,
    agendamento: bool,
    agora: Callable[[], datetime] = _agora,
) -> list[ResultadoSincronizacao]:
    feitas: list[ResultadoSincronizacao] = []
    with trava_sincronizacao(fabrica) as obtida:
        if not obtida:
            logger.debug("sincronizacao ja em andamento em outro processo")
            return feitas

        with fabrica() as db, db.begin():
            orfas = pedidos.encerrar_orfas(db, agora())
        if orfas:
            logger.warning("sync.orfas_encerradas execucoes=%s", orfas)

        with fabrica() as db, db.begin():
            pedido = pedidos.reivindicar_proximo(db, agora())
            pedido_id, tipo = (pedido.id, pedido.tipo) if pedido else (None, None)

        if pedido_id is not None:
            logger.info("sync.pedido id=%s tipo=%s", pedido_id, tipo)
            resultado = None
            try:
                resultado = executor(cast(TipoSincronizacao, tipo))
                feitas.append(resultado)
            finally:
                with fabrica() as db, db.begin():
                    pedidos.concluir(
                        db, pedido_id, resultado.sincronizacao_id if resultado else None, agora()
                    )
            return feitas

        if not agendamento:
            return feitas
        for job in AGENDA:
            with fabrica() as db:
                if job.diario:
                    vencida = pedidos.leitura_completa_vencida(
                        db, job.tipo, job.horario(settings), ZoneInfo(settings.tz), agora()
                    )
                else:
                    vencida = pedidos.execucao_vencida(
                        db, job.tipo, job.intervalo(settings), agora()
                    )
            if vencida:
                logger.info("sync.agendada tipo=%s", job.tipo)
                feitas.append(executor(job.tipo))
    return feitas


def rodar(
    settings: Settings,
    fabrica: Fabrica,
    executor: Executor,
    parar: threading.Event,
    *,
    agendamento: bool,
    uma_vez: bool = False,
) -> None:
    while not parar.is_set():
        try:
            executar_ciclo(fabrica, executor, settings, agendamento=agendamento)
        except Exception:
            logger.exception("ciclo de sincronizacao falhou")
        if uma_vez:
            return
        parar.wait(settings.sync_verificacao_segundos)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker de sincronizacao ERP/ERPAPI")
    parser.add_argument("--uma-vez", action="store_true", help="roda um ciclo e sai")
    parser.add_argument(
        "--executar",
        choices=get_args(TipoSincronizacao),
        help="executa esta sincronizacao agora (ignora agendamento e pedidos) e sai",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    from app.database.session import SessionLocal

    def executor(tipo: TipoSincronizacao) -> ResultadoSincronizacao:
        return executar(tipo, SessionLocal, settings=settings)

    if args.executar:
        with trava_sincronizacao(SessionLocal) as obtida:
            if not obtida:
                logger.error("outra sincronizacao esta em andamento; tente de novo depois")
                return 2
            resultado = executor(args.executar)
        logger.info(
            "sincronizacao %s id=%s status=%s %s",
            args.executar,
            resultado.sincronizacao_id,
            resultado.status,
            resultado.mensagem or "",
        )
        return 0 if resultado.status == "sucesso" else 1

    agendamento = erpapi_habilitado()
    logger.info(
        "sincronizador iniciando | empresas=%s | agendamento=%s | estoque a cada %ss | "
        "leitura completa as %s | empresas a cada %ss | transferencias a cada %ss | "
        "precos a cada %ss, completa as %s | vendas a cada %ss | movimentos a cada %ss",
        ",".join(settings.empresas_sincronizadas),
        "ligado" if agendamento else "desligado (ERPAPI_ENABLED=false)",
        settings.sync_estoque_intervalo_segundos,
        settings.sync_estoque_completo_horario or "desligada",
        settings.sync_empresas_intervalo_segundos,
        settings.sync_transferencias_intervalo_segundos,
        settings.sync_precos_intervalo_segundos,
        settings.sync_precos_completo_horario or "desligada",
        settings.sync_vendas_intervalo_segundos,
        settings.sync_movimentos_intervalo_segundos,
    )

    parar = threading.Event()

    def _sinal(numero: int, _frame: object) -> None:
        logger.info("sinal %s recebido: encerrando apos o ciclo atual", numero)
        parar.set()

    signal.signal(signal.SIGINT, _sinal)
    signal.signal(signal.SIGTERM, _sinal)

    rodar(settings, SessionLocal, executor, parar, agendamento=agendamento, uma_vez=args.uma_vez)
    logger.info("sincronizador encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
