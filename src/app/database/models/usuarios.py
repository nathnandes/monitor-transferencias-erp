from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.comum import (
    MODULOS_SISTEMA,
    ORIGENS_AUDITORIA,
    PAPEIS_USUARIO,
    TIPOS_EVENTO_AUDITORIA,
    USERNAME_REGEX_SQL,
    _created_at,
    _in,
    _jsonb,
    _updated_at,
)


class PerfilAcesso(Base):
    __tablename__ = "perfis_acesso"
    __table_args__ = (
        UniqueConstraint("nome", name="uq_perfis_acesso_nome"),
        CheckConstraint("length(btrim(nome)) > 0", name="ck_perfis_acesso_nome_preenchido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60))
    descricao: Mapped[str | None] = mapped_column(String(200))
    modulos: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    abas: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))

    tela_inicial: Mapped[str | None] = mapped_column(String(40))

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<PerfilAcesso {self.nome}>"


class Usuario(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint(f"username ~ '{USERNAME_REGEX_SQL}'", name="ck_users_username_formato"),
        CheckConstraint(
            "length(btrim(nome_exibicao)) > 0", name="ck_users_nome_exibicao_preenchido"
        ),
        CheckConstraint(_in("role", PAPEIS_USUARIO), name="ck_users_role"),
        CheckConstraint(
            "left(password_hash, 10) = '$argon2id$'", name="ck_users_password_hash_argon2id"
        ),
        CheckConstraint(
            "NOT (sessao_continua AND role = 'ADMIN')", name="ck_users_sessao_continua_so_operador"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(String(50))
    nome_exibicao: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    sessao_continua: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    perfil_id: Mapped[int | None] = mapped_column(
        ForeignKey("perfis_acesso.id", ondelete="RESTRICT"), index=True
    )
    perfil: Mapped[PerfilAcesso | None] = relationship(lazy="joined")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<Usuario {self.username} {self.role}>"


class PermissaoModulo(Base):
    __tablename__ = "user_module_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "module", name="uq_user_module_permissions_user_module"),
        CheckConstraint(_in("module", MODULOS_SISTEMA), name="ck_user_module_permissions_module"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    module: Mapped[str] = mapped_column(String(30))
    can_view: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    def __repr__(self) -> str:
        return f"<PermissaoModulo user_id={self.user_id} {self.module} view={self.can_view}>"


class EventoAuditoriaUsuario(Base):
    __tablename__ = "user_audit_events"
    __table_args__ = (
        CheckConstraint(
            _in("event_type", TIPOS_EVENTO_AUDITORIA), name="ck_user_audit_events_event_type"
        ),
        CheckConstraint(_in("origem", ORIGENS_AUDITORIA), name="ck_user_audit_events_origem"),
        Index("ix_user_audit_events_target_created", "target_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    origem: Mapped[str] = mapped_column(String(10))

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(50))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_username: Mapped[str] = mapped_column(String(50))

    detalhes: Mapped[dict[str, Any]] = _jsonb()
    created_at: Mapped[datetime] = _created_at()

    def __repr__(self) -> str:
        return f"<EventoAuditoriaUsuario {self.event_type} alvo={self.target_username}>"
