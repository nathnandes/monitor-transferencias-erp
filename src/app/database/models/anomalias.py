from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import _created_at, _updated_at
from app.database.models.transferencias import Transferencia

STATUS_EXECUCAO_ANOMALIAS = ("sucesso", "sem_historico", "erro")


class AnomaliaExecucao(Base):
    __tablename__ = "anomalias_execucoes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sucesso', 'sem_historico', 'erro')",
            name="ck_anomalias_execucoes_status",
        ),
        Index("ix_anomalias_execucoes_concluida_em", "concluida_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    concluida_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))

    versao_modelo: Mapped[str] = mapped_column(String(100))
    notas_treino: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    notas_avaliadas: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    notas_sinalizadas: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    limiar: Mapped[float | None] = mapped_column(Double)
    mensagem: Mapped[str | None] = mapped_column(Text)


class AnomaliaTransferencia(Base):
    __tablename__ = "anomalias_transferencias"
    __table_args__ = (
        Index(
            "ix_anomalias_transferencias_sinalizadas",
            "score",
            postgresql_where=text("sinalizada"),
        ),
    )

    transferencia_id: Mapped[int] = mapped_column(
        ForeignKey("transferencias.id", ondelete="CASCADE"), primary_key=True
    )
    execucao_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomalias_execucoes.id", ondelete="SET NULL"),
        index=True,
    )
    score: Mapped[float] = mapped_column(Double)
    limiar: Mapped[float] = mapped_column(Double)
    sinalizada: Mapped[bool] = mapped_column(Boolean)
    com_entrada: Mapped[bool] = mapped_column(Boolean)

    motivos: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    avaliada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    transferencia: Mapped[Transferencia] = relationship()
