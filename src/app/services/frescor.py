from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import Sincronizacao

SituacaoFrescor = Literal["EM_DIA", "ATRASADA", "PARADA", "NUNCA"]

STATUS_CONCLUIDA = ("sucesso", "parcial")


@dataclass(frozen=True)
class Frescor:
    tipo: str
    intervalo_segundos: int
    ultima_conclusao: datetime | None
    limite: timedelta
    situacao: SituacaoFrescor


def intervalos_agendados(settings: Settings) -> dict[str, int]:
    intervalos = {
        "transferencias": settings.sync_transferencias_intervalo_segundos,
        "estoque": settings.sync_estoque_intervalo_segundos,
        "precos": settings.sync_precos_intervalo_segundos,
        "vendas": settings.sync_vendas_intervalo_segundos,
        "movimentos_estoque": settings.sync_movimentos_intervalo_segundos,
    }
    return {tipo: segundos for tipo, segundos in intervalos.items() if segundos > 0}


def frescor(db: Session, settings: Settings, agora: datetime) -> list[Frescor]:
    intervalos = intervalos_agendados(settings)
    if not intervalos:
        return []
    concluida_em = func.max(func.coalesce(Sincronizacao.fim, Sincronizacao.inicio))
    ultimas: dict[str, datetime] = {
        tipo: momento
        for tipo, momento in db.execute(
            select(Sincronizacao.tipo, concluida_em)
            .where(Sincronizacao.tipo.in_(intervalos), Sincronizacao.status.in_(STATUS_CONCLUIDA))
            .group_by(Sincronizacao.tipo)
        )
    }
    minimo = timedelta(minutes=settings.alerta_sincronizacao_parada_minutos)
    resultado = []
    for tipo, segundos in intervalos.items():
        ultima = ultimas.get(tipo)
        limite = max(timedelta(seconds=3 * segundos), minimo)
        situacao: SituacaoFrescor
        if ultima is None:
            situacao = "NUNCA"
        elif agora - ultima > 3 * limite:
            situacao = "PARADA"
        elif agora - ultima > limite:
            situacao = "ATRASADA"
        else:
            situacao = "EM_DIA"
        resultado.append(Frescor(tipo, segundos, ultima, limite, situacao))
    return resultado
