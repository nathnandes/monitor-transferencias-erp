from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "alertas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("regra", sa.String(length=50), nullable=False),
        sa.Column("chave", sa.String(length=200), nullable=False),
        sa.Column("severidade", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="ABERTO", nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column(
            "detalhes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("empresa_id", sa.Integer(), nullable=True),
        sa.Column("transferencia_id", sa.Integer(), nullable=True),
        sa.Column("aberto_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transferencia_id"], ["transferencias.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "severidade IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')", name="ck_alertas_severidade"
        ),
        sa.CheckConstraint("status IN ('ABERTO', 'RESOLVIDO')", name="ck_alertas_status"),
        sa.CheckConstraint(
            "(status = 'RESOLVIDO') = (resolvido_em IS NOT NULL)", name="ck_alertas_resolvido_em"
        ),
    )
    op.create_index("ix_alertas_regra", "alertas", ["regra"], unique=False)
    op.create_index("ix_alertas_empresa_id", "alertas", ["empresa_id"], unique=False)
    op.create_index("ix_alertas_transferencia_id", "alertas", ["transferencia_id"], unique=False)
    op.create_index("ix_alertas_status_aberto_em", "alertas", ["status", "aberto_em"], unique=False)
    op.create_index(
        "uq_alertas_chave_aberto",
        "alertas",
        ["chave"],
        unique=True,
        postgresql_where=sa.text("status = 'ABERTO'"),
    )

    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alerta_id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(length=20), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDENTE", nullable=False),
        sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proxima_tentativa_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["alerta_id"], ["alertas.id"], ondelete="CASCADE"),
        sa.CheckConstraint("canal IN ('telegram')", name="ck_notificacoes_canal"),
        sa.CheckConstraint(
            "tipo IN ('ABERTURA', 'ESCALADA', 'RESOLUCAO')", name="ck_notificacoes_tipo"
        ),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'ENVIADA', 'FALHA', 'DESCARTADA')",
            name="ck_notificacoes_status",
        ),
        sa.CheckConstraint("tentativas >= 0", name="ck_notificacoes_tentativas"),
    )
    op.create_index("ix_notificacoes_alerta_id", "notificacoes", ["alerta_id"], unique=False)
    op.create_index(
        "ix_notificacoes_status_proxima",
        "notificacoes",
        ["status", "proxima_tentativa_em"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("notificacoes")
    op.drop_table("alertas")
