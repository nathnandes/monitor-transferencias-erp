from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import (
    STATUS_SINCRONIZACAO,
    STATUS_SOLICITACAO_SINCRONIZACAO,
    TIPOS_SINCRONIZACAO_MANUAL,
    _created_at,
    _in,
    _updated_at,
)

if TYPE_CHECKING:
    from app.database.models.empresas import Empresa


class Sincronizacao(Base):
    __tablename__ = "sincronizacoes"
    __table_args__ = (
        CheckConstraint(_in("status", STATUS_SINCRONIZACAO), name="ck_sincronizacoes_status"),
        CheckConstraint(
            "registros_consultados >= 0 AND registros_criados >= 0"
            " AND registros_atualizados >= 0 AND registros_ignorados >= 0",
            name="ck_sincronizacoes_contadores",
        ),
        CheckConstraint(
            "empresas_processadas >= 0 AND paginas_processadas >= 0",
            name="ck_sincronizacoes_contadores_execucao",
        ),
        CheckConstraint("fim IS NULL OR fim >= inicio", name="ck_sincronizacoes_periodo"),
        Index("ix_sincronizacoes_tipo_inicio", "tipo", "inicio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="RESTRICT"), index=True
    )

    tipo: Mapped[str] = mapped_column(String(50))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default="em_andamento", server_default="em_andamento", index=True
    )

    registros_consultados: Mapped[int] = mapped_column(default=0, server_default="0")
    registros_criados: Mapped[int] = mapped_column(default=0, server_default="0")
    registros_atualizados: Mapped[int] = mapped_column(default=0, server_default="0")
    registros_ignorados: Mapped[int] = mapped_column(default=0, server_default="0")
    empresas_processadas: Mapped[int] = mapped_column(default=0, server_default="0")
    paginas_processadas: Mapped[int] = mapped_column(default=0, server_default="0")

    mensagem_erro: Mapped[str | None] = mapped_column(Text)

    sincronizacao_pai_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="CASCADE"), index=True
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    empresa: Mapped["Empresa | None"] = relationship()

    @property
    def registros_gravados(self) -> int:
        return self.registros_criados + self.registros_atualizados

    def __repr__(self) -> str:
        return f"<Sincronizacao {self.tipo} {self.status}>"


class SolicitacaoSincronizacao(Base):
    __tablename__ = "solicitacoes_sincronizacao"
    __table_args__ = (
        CheckConstraint(
            _in("tipo", TIPOS_SINCRONIZACAO_MANUAL), name="ck_solicitacoes_sincronizacao_tipo"
        ),
        CheckConstraint(
            _in("status", STATUS_SOLICITACAO_SINCRONIZACAO),
            name="ck_solicitacoes_sincronizacao_status",
        ),
        Index(
            "uq_solicitacoes_sincronizacao_tipo_pendente",
            "tipo",
            unique=True,
            postgresql_where=text("status = 'PENDENTE'"),
        ),
        Index("ix_solicitacoes_sincronizacao_status_solicitado", "status", "solicitado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE", server_default="PENDENTE")

    solicitado_por: Mapped[str | None] = mapped_column(String(50))
    solicitado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<SolicitacaoSincronizacao {self.tipo} {self.status}>"


class IntegracaoErro(Base):
    __tablename__ = "integracao_erros"

    id: Mapped[int] = mapped_column(primary_key=True)
    sincronizacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("sincronizacoes.id", ondelete="CASCADE"), index=True
    )
    id_erp_empresa: Mapped[str | None] = mapped_column(String(50))
    endpoint: Mapped[str | None] = mapped_column(String(200))
    status_http: Mapped[int | None] = mapped_column(Integer)

    tipo_erro: Mapped[str] = mapped_column(String(100))
    mensagem: Mapped[str] = mapped_column(Text)
    tentativa: Mapped[int] = mapped_column(default=1, server_default="1")
    ocorrido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<IntegracaoErro {self.tipo_erro} {self.status_http}>"
