from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import _created_at, _jsonb, _updated_at

if TYPE_CHECKING:
    from app.database.models.empresas import Empresa


class Transferencia(Base):
    __tablename__ = "transferencias"
    __table_args__ = (
        UniqueConstraint("empresa_origem_id", "id_erp", name="uq_transferencias_origem_id_erp"),
        CheckConstraint(
            "quantidade_itens IS NULL OR quantidade_itens >= 0",
            name="ck_transferencias_quantidade_itens",
        ),
        CheckConstraint("status = upper(status)", name="ck_transferencias_status_maiusculo"),
        Index("ix_transferencias_status_data_criacao", "status", "data_criacao"),
        Index(
            "uq_transferencias_chave_nfe",
            "chave_nfe",
            unique=True,
            postgresql_where=text("chave_nfe IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    id_erp: Mapped[str] = mapped_column(String(50), index=True)

    empresa_origem_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="RESTRICT"))

    empresa_destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="RESTRICT"), index=True
    )

    status: Mapped[str | None] = mapped_column(String(50))
    data_criacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    data_processamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    quantidade_itens: Mapped[int | None] = mapped_column(Integer)

    coi: Mapped[str | None] = mapped_column(String(50), index=True)

    chave_nfe: Mapped[str | None] = mapped_column(String(44))
    numero_nota: Mapped[str | None] = mapped_column(String(20))

    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    usuario_emissao: Mapped[str | None] = mapped_column(String(100))

    id_erp_entrada: Mapped[str | None] = mapped_column(String(50))
    coi_entrada: Mapped[str | None] = mapped_column(String(50))

    empresa_entrada_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="RESTRICT")
    )

    problemas_coi: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )

    entre_empresas: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), index=True
    )

    hash_payload: Mapped[str | None] = mapped_column(String(64))
    raw_data: Mapped[dict[str, Any]] = _jsonb()

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    empresa_origem: Mapped["Empresa"] = relationship(
        back_populates="transferencias_origem", foreign_keys=[empresa_origem_id]
    )
    empresa_destino: Mapped["Empresa | None"] = relationship(
        back_populates="transferencias_destino", foreign_keys=[empresa_destino_id]
    )
    empresa_entrada: Mapped["Empresa | None"] = relationship(foreign_keys=[empresa_entrada_id])

    itens: Mapped[list["TransferenciaItem"]] = relationship(
        back_populates="transferencia",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tratativas: Mapped[list["TransferenciaTratativa"]] = relationship(
        back_populates="transferencia",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TransferenciaTratativa.id",
    )

    def __repr__(self) -> str:
        return f"<Transferencia {self.id_erp} {self.status!r}>"


class TransferenciaItem(Base):
    __tablename__ = "transferencias_itens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transferencia_id: Mapped[int] = mapped_column(
        ForeignKey("transferencias.id", ondelete="CASCADE"), index=True
    )

    id_produto_erp: Mapped[str] = mapped_column(String(50), index=True)
    codigo_produto: Mapped[str | None] = mapped_column(String(50))
    descricao_produto: Mapped[str | None] = mapped_column(String(300))

    quantidade_solicitada: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantidade_processada: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cfop_saida: Mapped[str | None] = mapped_column(String(10))
    cfop_entrada: Mapped[str | None] = mapped_column(String(10))

    raw_data: Mapped[dict[str, Any]] = _jsonb()

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    transferencia: Mapped[Transferencia] = relationship(back_populates="itens")

    def __repr__(self) -> str:
        return f"<TransferenciaItem {self.id_produto_erp} {self.quantidade_solicitada}>"


SITUACOES_TRATATIVA = ("EM_ANALISE", "RESOLVIDA")


class TransferenciaTratativa(Base):
    __tablename__ = "transferencias_tratativas"
    __table_args__ = (
        CheckConstraint("situacao IN ('EM_ANALISE', 'RESOLVIDA')", name="ck_tratativas_situacao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transferencia_id: Mapped[int] = mapped_column(
        ForeignKey("transferencias.id", ondelete="CASCADE"), index=True
    )
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    usuario_nome: Mapped[str] = mapped_column(String(100))
    situacao: Mapped[str] = mapped_column(String(20))
    observacao: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    transferencia: Mapped[Transferencia] = relationship(back_populates="tratativas")


class PrazoRota(Base):
    __tablename__ = "prazos_rota"
    __table_args__ = (
        UniqueConstraint("empresa_origem_id", "empresa_destino_id", name="uq_prazos_rota"),
        CheckConstraint("horas > 0 AND horas <= 720", name="ck_prazos_rota_horas"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_origem_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"))
    empresa_destino_id: Mapped[int] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"))
    horas: Mapped[int] = mapped_column(Integer)
    atualizado_por: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime] = _updated_at()


class LimitesPendencia(Base):
    __tablename__ = "limites_pendencia"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_limites_pendencia_uma_linha"),
        CheckConstraint(
            "horas_atencao > 0 AND horas_atencao < horas_critico AND horas_critico <= 720",
            name="ck_limites_pendencia_horas",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    horas_atencao: Mapped[int] = mapped_column(Integer)
    horas_critico: Mapped[int] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<LimitesPendencia atencao={self.horas_atencao}h critico={self.horas_critico}h>"
