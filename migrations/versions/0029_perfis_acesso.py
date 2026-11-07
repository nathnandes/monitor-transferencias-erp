from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "perfis_acesso",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(60), nullable=False),
        sa.Column("descricao", sa.String(200)),
        sa.Column("modulos", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("abas", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("tela_inicial", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("nome", name="uq_perfis_acesso_nome"),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_perfis_acesso_nome_preenchido"),
    )
    op.add_column(
        "users",
        sa.Column(
            "perfil_id",
            sa.Integer(),
            sa.ForeignKey("perfis_acesso.id", ondelete="RESTRICT"),
        ),
    )
    op.create_index("ix_users_perfil_id", "users", ["perfil_id"])


def downgrade() -> None:
    op.drop_index("ix_users_perfil_id", table_name="users")
    op.drop_column("users", "perfil_id")
    op.drop_table("perfis_acesso")
