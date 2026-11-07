import argparse
import signal
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.anomalias.modelo import DetectorAnomalias
from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger, setup_logging
from app.database.models import AnomaliaExecucao
from app.services import anomalias as service
from app.services.anomalias import ResultadoGravavel

logger = get_logger(__name__)

Fabrica = Callable[[], Session]


_LOCK_DETECTOR = 4_201_002

_ESPERA_SEGUNDOS = 60


@dataclass(frozen=True)
class ResumoRodada:
    id: int
    status: str
    mensagem: str | None


def _resumo(execucao: AnomaliaExecucao) -> ResumoRodada:
    return ResumoRodada(execucao.id, execucao.status, execucao.mensagem)


def _agora() -> datetime:
    return datetime.now(UTC)


def _versao(detector: DetectorAnomalias) -> str:
    return (
        f"isolation-forest n={detector.n_estimators} "
        f"amostra={detector.max_samples} alerta={detector.fracao_alerta}"
    )


def rodar_detector(db: Session, settings: Settings, agora: datetime) -> AnomaliaExecucao:
    tz = ZoneInfo(settings.tz)
    inicio_avaliacao = agora - timedelta(days=settings.anomalias_janela_avaliacao_dias)
    detector = DetectorAnomalias(fracao_alerta=settings.anomalias_fracao_alerta)
    treino = service.carregar_treino(
        db,
        inicio=agora - timedelta(days=settings.anomalias_historico_dias),
        fim=inicio_avaliacao,
        tz=tz,
    )
    if len(treino) < settings.anomalias_minimo_treino:
        return service.registrar_execucao(
            db,
            agora=agora,
            status="sem_historico",
            versao_modelo=_versao(detector),
            notas_treino=len(treino),
            mensagem=(
                f"{len(treino)} notas de histórico; o mínimo é "
                f"{settings.anomalias_minimo_treino}. Nada foi avaliado."
            ),
        )

    detector.treinar(treino)
    assert detector.limiar is not None
    avaliaveis = service.carregar_para_avaliar(db, inicio=inicio_avaliacao, tz=tz)
    resultados = detector.analisar(avaliaveis)
    execucao = service.registrar_execucao(
        db,
        agora=agora,
        status="sucesso",
        versao_modelo=_versao(detector),
        notas_treino=len(treino),
        notas_avaliadas=len(resultados),
        notas_sinalizadas=sum(r.sinalizada for r in resultados),
        limiar=detector.limiar,
    )
    service.gravar_resultados(
        db,
        execucao,
        (
            ResultadoGravavel(
                transferencia_id=int(r.registro.id),
                score=r.score,
                sinalizada=r.sinalizada,
                com_entrada=not r.registro.pendente,
                motivos=[
                    {"feature": m.feature, "contribuicao": m.contribuicao, "texto": m.texto}
                    for m in r.motivos
                ],
            )
            for r in resultados
        ),
        limiar=detector.limiar,
        agora=agora,
    )
    logger.info(
        "anomalias: treino=%d avaliadas=%d sinalizadas=%d",
        execucao.notas_treino,
        execucao.notas_avaliadas,
        execucao.notas_sinalizadas,
    )
    return execucao


def executar_ciclo(
    fabrica: Fabrica,
    settings: Settings,
    *,
    forcar: bool = False,
    agora: Callable[[], datetime] = _agora,
) -> ResumoRodada | None:
    try:
        with fabrica() as db, db.begin():
            obtida = db.scalar(
                text("SELECT pg_try_advisory_xact_lock(:chave)"), {"chave": _LOCK_DETECTOR}
            )
            if not obtida:
                logger.debug("detector ja em andamento em outro processo")
                return None
            if not forcar and not service.execucao_vencida(
                db, settings.anomalias_intervalo_segundos, agora()
            ):
                return None
            return _resumo(rodar_detector(db, settings, agora()))
    except Exception as exc:
        logger.exception("rodada do detector de anomalias falhou")
        with fabrica() as db, db.begin():
            return _resumo(
                service.registrar_execucao(
                    db,
                    agora=agora(),
                    status="erro",
                    versao_modelo="desconhecida",
                    mensagem=f"{type(exc).__name__}: {exc}"[:500],
                )
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker do detector de anomalias")
    parser.add_argument("--uma-vez", action="store_true", help="roda agora e sai")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    from app.database.session import SessionLocal

    if args.uma_vez:
        execucao = executar_ciclo(SessionLocal, settings, forcar=True)
        if execucao is None:
            logger.error("outra rodada esta em andamento; tente de novo depois")
            return 2
        logger.info("rodada %s: %s %s", execucao.id, execucao.status, execucao.mensagem or "")
        return 1 if execucao.status == "erro" else 0

    parar = threading.Event()

    def _sinal(numero: int, _frame: object) -> None:
        logger.info("sinal %s recebido: encerrando apos a rodada atual", numero)
        parar.set()

    signal.signal(signal.SIGINT, _sinal)
    signal.signal(signal.SIGTERM, _sinal)

    logger.info("detector iniciando | a cada %ss", settings.anomalias_intervalo_segundos)
    while not parar.is_set():
        try:
            executar_ciclo(SessionLocal, settings)
        except Exception:
            logger.exception("ciclo do detector falhou")
        parar.wait(_ESPERA_SEGUNDOS)
    logger.info("detector encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
