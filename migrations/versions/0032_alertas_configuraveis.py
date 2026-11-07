from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: str | None = "0031"
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
        "alerta_destinos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("chat_id", sa.String(length=50), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "severidade_minima", sa.String(length=10), server_default="WARNING", nullable=False
        ),
        sa.Column(
            "empresas",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
        sa.CheckConstraint(
            "severidade_minima IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')",
            name="ck_alerta_destinos_severidade",
        ),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_alerta_destinos_nome"),
    )
    op.create_table(
        "alerta_configuracoes",
        sa.Column("regra", sa.String(length=50), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "campos",
            postgresql.ARRAY(sa.String(length=50)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("regra"),
    )
    op.create_table(
        "alerta_regra_destinos",
        sa.Column("regra", sa.String(length=50), nullable=False),
        sa.Column("destino_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("regra", "destino_id"),
        sa.ForeignKeyConstraint(["regra"], ["alerta_configuracoes.regra"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["destino_id"], ["alerta_destinos.id"], ondelete="CASCADE"),
    )
    op.add_column("notificacoes", sa.Column("destino_id", sa.Integer(), nullable=True))
    op.create_index("ix_notificacoes_destino_id", "notificacoes", ["destino_id"], unique=False)
    op.create_foreign_key(
        "notificacoes_destino_id_fkey",
        "notificacoes",
        "alerta_destinos",
        ["destino_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "INSERT INTO alerta_destinos (nome, chat_id, severidade_minima) "
        "VALUES ('Padrão (TELEGRAM_CHAT_ID do .env)', NULL, 'WARNING')"
    )


def downgrade() -> None:
    op.drop_constraint("notificacoes_destino_id_fkey", "notificacoes", type_="foreignkey")
    op.drop_index("ix_notificacoes_destino_id", table_name="notificacoes")
    op.drop_column("notificacoes", "destino_id")
    op.drop_table("alerta_regra_destinos")
    op.drop_table("alerta_configuracoes")
    op.drop_table("alerta_destinos")
