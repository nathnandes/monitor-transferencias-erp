from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "modelos_mensagem_avulsa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("atualizado_por", sa.String(100), nullable=False),
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
        sa.UniqueConstraint("nome"),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_modelos_mensagem_avulsa_nome"),
        sa.CheckConstraint("length(btrim(texto)) > 0", name="ck_modelos_mensagem_avulsa_texto"),
    )


def downgrade() -> None:
    op.drop_table("modelos_mensagem_avulsa")
