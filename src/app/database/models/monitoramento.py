from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import (
    CANAIS_NOTIFICACAO,
    NIVEIS_LOG,
    SEVERIDADES_EVENTO,
    STATUS_ALERTA,
    STATUS_NOTIFICACAO,
    STATUS_RESUMO_DIARIO,
    TIPOS_NOTIFICACAO,
    _created_at,
    _in,
    _jsonb,
    _updated_at,
)

if TYPE_CHECKING:
    from app.database.models.empresas import Empresa
    from app.database.models.transferencias import Transferencia


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(_in("severidade", SEVERIDADES_EVENTO), name="ck_eventos_severidade"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="RESTRICT"), index=True
    )
    transferencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("transferencias.id", ondelete="RESTRICT"), index=True
    )

    tipo: Mapped[str] = mapped_column(String(50), index=True)

    origem: Mapped[str] = mapped_column(String(50))
    severidade: Mapped[str] = mapped_column(String(10), index=True)

    referencia_externa: Mapped[str | None] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = _jsonb()

    data_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = _created_at()

    empresa: Mapped["Empresa | None"] = relationship()
    transferencia: Mapped["Transferencia | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Evento {self.tipo} {self.severidade}>"


class Log(Base):
    __tablename__ = "logs"
    __table_args__ = (CheckConstraint(_in("nivel", NIVEIS_LOG), name="ck_logs_nivel"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    nivel: Mapped[str] = mapped_column(String(10), index=True)
    modulo: Mapped[str] = mapped_column(String(100), index=True)
    evento: Mapped[str] = mapped_column(String(100))
    mensagem: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = _jsonb()

    data: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = _created_at()

    def __repr__(self) -> str:
        return f"<Log {self.nivel} {self.modulo}.{self.evento}>"


class Alerta(Base):
    __tablename__ = "alertas"
    __table_args__ = (
        CheckConstraint(_in("severidade", SEVERIDADES_EVENTO), name="ck_alertas_severidade"),
        CheckConstraint(_in("status", STATUS_ALERTA), name="ck_alertas_status"),
        CheckConstraint(
            "(status = 'RESOLVIDO') = (resolvido_em IS NOT NULL)", name="ck_alertas_resolvido_em"
        ),
        Index(
            "uq_alertas_chave_aberto",
            "chave",
            unique=True,
            postgresql_where=text("status = 'ABERTO'"),
        ),
        Index("ix_alertas_status_aberto_em", "status", "aberto_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    regra: Mapped[str] = mapped_column(String(50), index=True)
    chave: Mapped[str] = mapped_column(String(200))
    severidade: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="ABERTO", server_default="ABERTO")
    titulo: Mapped[str] = mapped_column(String(200))
    mensagem: Mapped[str] = mapped_column(Text)
    detalhes: Mapped[dict[str, Any]] = _jsonb()

    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="SET NULL"), index=True
    )
    transferencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("transferencias.id", ondelete="SET NULL"), index=True
    )

    aberto_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    visto_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    empresa: Mapped["Empresa | None"] = relationship()
    transferencia: Mapped["Transferencia | None"] = relationship()
    notificacoes: Mapped[list["Notificacao"]] = relationship(
        back_populates="alerta", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Alerta {self.chave} {self.severidade} {self.status}>"


class Notificacao(Base):
    __tablename__ = "notificacoes"
    __table_args__ = (
        CheckConstraint(_in("canal", CANAIS_NOTIFICACAO), name="ck_notificacoes_canal"),
        CheckConstraint(_in("tipo", TIPOS_NOTIFICACAO), name="ck_notificacoes_tipo"),
        CheckConstraint(_in("status", STATUS_NOTIFICACAO), name="ck_notificacoes_status"),
        CheckConstraint("tentativas >= 0", name="ck_notificacoes_tentativas"),
        CheckConstraint(
            "num_nonnulls(alerta_id, atividade_id, mensagem_id) = 1",
            name="ck_notificacoes_origem",
        ),
        Index("ix_notificacoes_status_proxima", "status", "proxima_tentativa_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alerta_id: Mapped[int | None] = mapped_column(
        ForeignKey("alertas.id", ondelete="CASCADE"), index=True
    )
    atividade_id: Mapped[int | None] = mapped_column(
        ForeignKey("atividades.id", ondelete="CASCADE"), index=True
    )
    mensagem_id: Mapped[int | None] = mapped_column(
        ForeignKey("mensagens_avulsas.id", ondelete="CASCADE"), index=True
    )

    destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerta_destinos.id", ondelete="RESTRICT"), index=True
    )
    canal: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE", server_default="PENDENTE")
    tentativas: Mapped[int] = mapped_column(default=0, server_default="0")
    proxima_tentativa_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enviada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    alerta: Mapped[Alerta | None] = relationship(back_populates="notificacoes")
    atividade: Mapped["Atividade | None"] = relationship(back_populates="notificacoes")
    mensagem: Mapped["MensagemAvulsa | None"] = relationship(back_populates="notificacoes")
    destino: Mapped["AlertaDestino | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Notificacao {self.canal} {self.tipo} {self.status}>"


class ResumoDiario(Base):
    __tablename__ = "resumos_diarios"
    __table_args__ = (
        CheckConstraint(_in("status", STATUS_RESUMO_DIARIO), name="ck_resumos_diarios_status"),
        CheckConstraint("tentativas >= 0", name="ck_resumos_diarios_tentativas"),
    )

    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE", server_default="PENDENTE")
    tentativas: Mapped[int] = mapped_column(default=0, server_default="0")
    proxima_tentativa_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<ResumoDiario {self.dia} {self.status}>"


alerta_regra_destinos = Table(
    "alerta_regra_destinos",
    Base.metadata,
    Column("regra", ForeignKey("alerta_configuracoes.regra", ondelete="CASCADE"), primary_key=True),
    Column("destino_id", ForeignKey("alerta_destinos.id", ondelete="CASCADE"), primary_key=True),
)


class AlertaDestino(Base):
    __tablename__ = "alerta_destinos"
    __table_args__ = (
        CheckConstraint(
            _in("severidade_minima", SEVERIDADES_EVENTO), name="ck_alerta_destinos_severidade"
        ),
        CheckConstraint("length(btrim(nome)) > 0", name="ck_alerta_destinos_nome"),
        CheckConstraint(_in("canal", CANAIS_NOTIFICACAO), name="ck_alerta_destinos_canal"),
        CheckConstraint(
            "canal <> 'whatsapp' OR chat_id IS NOT NULL", name="ck_alerta_destinos_numero"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)
    canal: Mapped[str] = mapped_column(String(20), default="telegram", server_default="telegram")
    chat_id: Mapped[str | None] = mapped_column(String(50))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    severidade_minima: Mapped[str] = mapped_column(
        String(10), default="WARNING", server_default="WARNING"
    )
    empresas: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=text("'{}'")
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<AlertaDestino {self.nome}>"


class AlertaConfiguracao(Base):
    __tablename__ = "alerta_configuracoes"

    regra: Mapped[str] = mapped_column(String(50), primary_key=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    campos: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, server_default=text("'{}'")
    )

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    destinos: Mapped[list[AlertaDestino]] = relationship(
        secondary=alerta_regra_destinos, order_by=AlertaDestino.nome
    )

    def __repr__(self) -> str:
        return f"<AlertaConfiguracao {self.regra} ativo={self.ativo}>"


class ModeloMensagem(Base):
    __tablename__ = "modelos_mensagem"
    __table_args__ = (
        CheckConstraint("length(btrim(texto)) > 0", name="ck_modelos_mensagem_texto"),
    )

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    usuario_nome: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<ModeloMensagem {self.chave}>"


class Atividade(Base):
    __tablename__ = "atividades"
    __table_args__ = (Index("ix_atividades_ocorrida_em", "ocorrida_em"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50), index=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    usuario_nome: Mapped[str] = mapped_column(String(100))
    ip: Mapped[str | None] = mapped_column(String(64))
    resumo: Mapped[str] = mapped_column(String(300))
    detalhe: Mapped[str | None] = mapped_column(Text)

    valores: Mapped[dict[str, Any]] = _jsonb()
    empresas: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=text("'{}'")
    )
    ocorrida_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    notificacoes: Mapped[list[Notificacao]] = relationship(
        back_populates="atividade", order_by=Notificacao.id
    )

    def __repr__(self) -> str:
        return f"<Atividade {self.tipo} {self.usuario_nome}>"


class MensagemAvulsa(Base):
    __tablename__ = "mensagens_avulsas"
    __table_args__ = (
        CheckConstraint("length(btrim(texto)) > 0", name="ck_mensagens_avulsas_texto"),
        CheckConstraint(
            "horario IS NULL OR cardinality(dias_semana) > 0",
            name="ck_mensagens_avulsas_dias_semana",
        ),
        Index("ix_mensagens_avulsas_agendada_para", "agendada_para"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    agendada_para: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    horario: Mapped[time | None] = mapped_column(Time)
    dias_semana: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=text("'{}'")
    )

    destinos: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=text("'{}'")
    )
    criada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    criada_por_nome: Mapped[str] = mapped_column(String(100))
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    notificacoes: Mapped[list[Notificacao]] = relationship(
        back_populates="mensagem", order_by=Notificacao.id
    )

    def __repr__(self) -> str:
        return f"<MensagemAvulsa {self.id} {self.agendada_para:%Y-%m-%d %H:%M}>"


class ModeloMensagemAvulsa(Base):
    __tablename__ = "modelos_mensagem_avulsa"
    __table_args__ = (
        CheckConstraint("length(btrim(nome)) > 0", name="ck_modelos_mensagem_avulsa_nome"),
        CheckConstraint("length(btrim(texto)) > 0", name="ck_modelos_mensagem_avulsa_texto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    texto: Mapped[str] = mapped_column(Text)
    atualizado_por: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<ModeloMensagemAvulsa {self.nome}>"
