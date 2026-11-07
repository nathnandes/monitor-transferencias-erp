from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import ColumnElement, and_, func, not_, or_

from app.database.models import Transferencia
from app.dominio.transferencias import (
    STATUS_CANCELADA,
    STATUS_ERRO,
    STATUS_PENDENTE,
    STATUS_PROCESSADA,
)

SituacaoCoi = Literal["CORRETO", "ERRADO", "AGUARDANDO"]
SITUACOES_COI: tuple[SituacaoCoi, ...] = ("CORRETO", "ERRADO", "AGUARDANDO")

EstadoEtapa = Literal["concluida", "atual", "falha", "pendente"]


@dataclass(frozen=True)
class Etapa:
    chave: str
    rotulo: str
    estado: EstadoEtapa
    momento: datetime | None = None
    detalhe: str | None = None


def _normalizar(valor: str | None) -> str:
    return (valor or "").strip().upper()


def _preenchido(valor: str | None) -> bool:
    return bool(valor and valor.strip())


def situacao_coi(
    status: str | None, problemas: Sequence[str] | None, coi_entrada: str | None
) -> SituacaoCoi:
    if problemas and _normalizar(status) != STATUS_CANCELADA:
        return "ERRADO"
    if _preenchido(coi_entrada):
        return "CORRETO"
    return "AGUARDANDO"


def condicao_situacao_coi(situacao: SituacaoCoi) -> ColumnElement[bool]:

    nao_cancelada = or_(
        Transferencia.status.is_(None),
        Transferencia.status != STATUS_CANCELADA,
    )
    errado = and_(func.jsonb_array_length(Transferencia.problemas_coi) > 0, nao_cancelada)
    if situacao == "ERRADO":
        return errado
    com_entrada = func.coalesce(func.btrim(Transferencia.coi_entrada), "") != ""
    if situacao == "CORRETO":
        return and_(not_(errado), com_entrada)
    return and_(not_(errado), not_(com_entrada))


def etapas(
    status: str | None,
    problemas: Sequence[str] | None,
    coi_entrada: str | None,
    data_criacao: datetime | None,
    data_processamento: datetime | None,
) -> list[Etapa]:
    status_ = _normalizar(status)
    situacao = situacao_coi(status, problemas, coi_entrada)
    recebida = _preenchido(coi_entrada) or status_ == STATUS_PROCESSADA

    if status_ == STATUS_CANCELADA:
        return [
            Etapa("criada", "Saída emitida", "falha", data_criacao, "Nota de saída cancelada"),
            Etapa("processamento", "Entrada no destino", "pendente"),
            Etapa("coi", "COIs conferidos", "pendente"),
            Etapa("concluida", "Concluída", "pendente"),
        ]

    criada = Etapa("criada", "Saída emitida", "concluida", data_criacao)

    if recebida:
        processamento = Etapa(
            "processamento", "Entrada no destino", "concluida", data_processamento
        )
    elif status_ == STATUS_ERRO:
        processamento = Etapa(
            "processamento", "Entrada no destino", "falha", detalhe="Erro no processamento"
        )
    else:
        detalhe = (
            "Aguardando a entrada" if status_ in ("", STATUS_PENDENTE) else f"Status: {status_}"
        )
        processamento = Etapa("processamento", "Entrada no destino", "atual", detalhe=detalhe)

    if situacao == "ERRADO":
        etapa_coi = Etapa(
            "coi", "COIs conferidos", "falha", detalhe="; ".join(problemas or ()) or None
        )
    elif situacao == "CORRETO":
        etapa_coi = Etapa(
            "coi", "COIs conferidos", "concluida", detalhe="COIs de saída e entrada certos"
        )
    else:
        etapa_coi = Etapa("coi", "COIs conferidos", "pendente")

    if situacao == "CORRETO" and recebida:
        concluida = Etapa("concluida", "Concluída", "concluida", data_processamento)
    else:
        concluida = Etapa("concluida", "Concluída", "pendente")

    return [criada, processamento, etapa_coi, concluida]
