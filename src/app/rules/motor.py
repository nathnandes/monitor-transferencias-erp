from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import Alerta
from app.notifications.outbox import enfileirar
from app.rules.config import Configuracao, carregar
from app.rules.regras import NIVEL_SEVERIDADE, REGRAS, Ocorrencia, Regra

logger = get_logger(__name__)

SEVERIDADE_MINIMA_NOTIFICACAO = "WARNING"

_LOCK_MOTOR = 4_201_001


@dataclass
class ResultadoAvaliacao:
    abertos: int = 0
    escalados: int = 0
    resolvidos: int = 0
    mantidos: int = 0

    desligadas: int = 0


def _notifica(severidade: str) -> bool:
    return NIVEL_SEVERIDADE[severidade] >= NIVEL_SEVERIDADE[SEVERIDADE_MINIMA_NOTIFICACAO]


def _empresas(alerta: Alerta) -> list[int]:
    return list((alerta.detalhes or {}).get("empresas_ids") or [])


def _notificar(
    db: Session, config: Configuracao, alerta: Alerta, tipo: str, agora: datetime
) -> int:
    if not _notifica(alerta.severidade):
        return 0
    destinos = config.destinos_para(alerta.regra, alerta.severidade, _empresas(alerta))
    for destino in destinos:
        enfileirar(db, alerta, tipo, agora, destino)
    return len(destinos)


def _abrir(db: Session, o: Ocorrencia, agora: datetime, config: Configuracao) -> Alerta:
    alerta = Alerta(
        regra=o.regra,
        chave=o.chave,
        severidade=o.severidade,
        status="ABERTO",
        titulo=o.titulo,
        mensagem=o.mensagem,
        detalhes=o.detalhes,
        empresa_id=o.empresa_id,
        transferencia_id=o.transferencia_id,
        aberto_em=agora,
        visto_em=agora,
    )
    db.add(alerta)
    db.flush()
    _notificar(db, config, alerta, "ABERTURA", agora)
    return alerta


def avaliar(
    db: Session, agora: datetime, regras: dict[str, Regra] | None = None
) -> ResultadoAvaliacao:
    regras = REGRAS if regras is None else regras
    db.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": _LOCK_MOTOR})
    config = carregar(db)

    resultado = ResultadoAvaliacao()
    abertos = {
        a.chave: a
        for a in db.scalars(
            select(Alerta).where(Alerta.status == "ABERTO", Alerta.regra.in_(list(regras)))
        )
    }

    vistas: set[str] = set()
    desligadas: set[str] = set()
    for nome, regra in regras.items():
        if not config.regra(nome).ativo:
            desligadas.add(nome)
            continue
        for o in regra(db, agora):
            if o.chave in vistas:
                continue
            vistas.add(o.chave)
            alerta = abertos.get(o.chave)
            if alerta is None:
                _abrir(db, o, agora, config)
                resultado.abertos += 1
                continue

            subiu = NIVEL_SEVERIDADE[o.severidade] > NIVEL_SEVERIDADE[alerta.severidade]
            alerta.severidade = o.severidade
            alerta.titulo = o.titulo
            alerta.mensagem = o.mensagem
            alerta.detalhes = o.detalhes
            alerta.visto_em = agora
            if subiu and _notifica(o.severidade):
                _notificar(db, config, alerta, "ESCALADA", agora)
                resultado.escalados += 1
            else:
                resultado.mantidos += 1
        logger.debug("regra %s avaliada", nome)

    for chave, alerta in abertos.items():
        if chave in vistas:
            continue
        alerta.status = "RESOLVIDO"
        alerta.resolvido_em = agora
        resultado.resolvidos += 1
        if alerta.regra in desligadas:
            continue

        avisados = {
            n.destino_id: n.destino
            for n in alerta.notificacoes
            if n.tipo in ("ABERTURA", "ESCALADA")
        }
        for destino in avisados.values():
            enfileirar(db, alerta, "RESOLUCAO", agora, destino)
    resultado.desligadas = len(desligadas)

    db.flush()
    if resultado.abertos or resultado.escalados or resultado.resolvidos:
        logger.info(
            "alertas: %d abertos, %d escalados, %d resolvidos, %d mantidos",
            resultado.abertos,
            resultado.escalados,
            resultado.resolvidos,
            resultado.mantidos,
        )
    return resultado
