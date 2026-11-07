from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.mascaramento import mascarar_texto
from app.database.models import Alerta, AlertaDestino, MensagemAvulsa, Notificacao
from app.notifications import modelos
from app.notifications.enviador import Enviador, ErroEnvio
from app.notifications.mensagens import montar_texto, montar_texto_atividade
from app.notifications.variaveis_mensagem import preencher

if TYPE_CHECKING:
    from app.rules.config import Configuracao

logger = get_logger(__name__)

CANAL_PADRAO = "telegram"
VALIDADE = timedelta(hours=6)
MAX_TENTATIVAS = 8
ESPERA_INICIAL = timedelta(minutes=1)
ESPERA_MAXIMA = timedelta(hours=1)


@dataclass
class ResultadoDespacho:
    enviadas: int = 0
    reagendadas: int = 0
    falhas: int = 0
    descartadas: int = 0


def enfileirar(
    db: Session,
    alerta: Alerta,
    tipo: str,
    agora: datetime,
    destino: AlertaDestino | None = None,
) -> Notificacao:
    notificacao = Notificacao(
        alerta=alerta,
        destino=destino,
        canal=canal_do_destino(destino),
        tipo=tipo,
        status="PENDENTE",
        proxima_tentativa_em=agora,
        created_at=agora,
    )
    db.add(notificacao)
    return notificacao


def enfileirar_mensagem(
    db: Session, mensagem: MensagemAvulsa, destinos: list[AlertaDestino], momento: datetime
) -> list[Notificacao]:
    notificacoes = [
        Notificacao(
            mensagem=mensagem,
            destino=destino,
            canal=canal_do_destino(destino),
            tipo="MENSAGEM",
            status="PENDENTE",
            proxima_tentativa_em=momento,
            created_at=momento,
        )
        for destino in destinos
    ]
    db.add_all(notificacoes)
    return notificacoes


def canal_do_destino(destino: AlertaDestino | None) -> str:
    return destino.canal if destino is not None and destino.canal else CANAL_PADRAO


def _espera(tentativas: int) -> timedelta:
    espera: timedelta = ESPERA_INICIAL * (2 ** (tentativas - 1))
    return min(espera, ESPERA_MAXIMA)


def _motivo_descarte(n: Notificacao, agora: datetime) -> str | None:
    referencia = n.created_at
    if n.mensagem is not None and n.mensagem.horario is None:
        referencia = max(referencia, n.mensagem.agendada_para)
    if agora - referencia > VALIDADE:
        return "obsoleta: mais antiga que a validade"
    if n.destino is not None and not n.destino.ativo:
        return "destino desligado"
    if n.mensagem is not None:
        return "mensagem cancelada" if n.mensagem.cancelada_em is not None else None
    alerta = n.alerta
    if alerta is None:
        return None
    if n.tipo in ("ABERTURA", "ESCALADA") and alerta.status == "RESOLVIDO":
        return "alerta ja resolvido antes do envio"
    if n.tipo == "RESOLUCAO" and not any(
        o.tipo in ("ABERTURA", "ESCALADA")
        and o.status == "ENVIADA"
        and o.destino_id == n.destino_id
        for o in alerta.notificacoes
    ):
        return "abertura do alerta nunca foi enviada a este destino"
    return None


def _texto(
    db: Session,
    n: Notificacao,
    config: "Configuracao",
    textos: dict[str, str],
    tz: ZoneInfo,
    agora: datetime,
    avulsas: dict[int, str],
) -> str:
    if n.mensagem is not None:
        if n.mensagem.id not in avulsas:
            avulsas[n.mensagem.id] = preencher(db, n.mensagem.texto, agora, tz)
        return avulsas[n.mensagem.id]
    if n.atividade is not None:
        tipo = n.atividade.tipo
        campos = config.regra(tipo).campos
        return montar_texto_atividade(n.atividade, tz, campos, textos.get(f"{tipo}:aviso"))
    assert n.alerta is not None
    sufixo = "resolucao" if n.tipo == "RESOLUCAO" else "aviso"
    modelo = textos.get(f"{n.alerta.regra}:{sufixo}")
    return montar_texto(n.alerta, n.tipo, tz, config.regra(n.alerta.regra).campos, modelo)


def processar_pendentes(
    db: Session, enviador: Enviador, agora: datetime, tz: ZoneInfo, lote: int = 10
) -> ResultadoDespacho:

    from app.rules.config import carregar

    resultado = ResultadoDespacho()
    pendentes = db.scalars(
        select(Notificacao)
        .where(
            Notificacao.status == "PENDENTE",
            Notificacao.canal == enviador.canal,
            Notificacao.proxima_tentativa_em <= agora,
        )
        .order_by(Notificacao.id)
        .limit(lote)
        .with_for_update(skip_locked=True, of=Notificacao)
    ).all()
    config = carregar(db) if pendentes else None
    textos = modelos.carregar(db) if pendentes else {}
    avulsas: dict[int, str] = {}

    for n in pendentes:
        motivo = _motivo_descarte(n, agora)
        if motivo:
            n.status = "DESCARTADA"
            n.ultimo_erro = motivo
            resultado.descartadas += 1
            continue

        assert config is not None
        chat = n.destino.chat_id if n.destino is not None else None
        try:
            enviador.enviar(_texto(db, n, config, textos, tz, agora, avulsas), chat_id=chat)
        except ErroEnvio as erro:
            n.tentativas += 1
            n.ultimo_erro = mascarar_texto(str(erro))[:500]
            if erro.transitorio and n.tentativas < MAX_TENTATIVAS:
                n.proxima_tentativa_em = agora + _espera(n.tentativas)
                resultado.reagendadas += 1
            else:
                n.status = "FALHA"
                resultado.falhas += 1
                logger.error(
                    "notificacao %d (alerta %s, atividade %s) falhou de vez: %s",
                    n.id,
                    n.alerta_id,
                    n.atividade_id,
                    n.ultimo_erro,
                )
            continue
        except Exception as erro:
            logger.exception("notificacao %d (alerta %s) quebrou no envio", n.id, n.alerta_id)
            n.tentativas += 1
            n.status = "FALHA"
            n.ultimo_erro = mascarar_texto(f"{type(erro).__name__}: {erro}")[:500]
            resultado.falhas += 1
            continue

        n.tentativas += 1
        n.status = "ENVIADA"
        n.enviada_em = agora
        n.ultimo_erro = None
        resultado.enviadas += 1

    db.flush()
    if pendentes:
        logger.info(
            "notificacoes: %d enviadas, %d reagendadas, %d falhas, %d descartadas",
            resultado.enviadas,
            resultado.reagendadas,
            resultado.falhas,
            resultado.descartadas,
        )
    return resultado
