from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "empresas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_erp", sa.String(length=50), nullable=True),
        sa.Column("codigo", sa.String(length=20), nullable=False),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("ambiente", sa.String(length=20), server_default="producao", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_empresas_codigo"), "empresas", ["codigo"], unique=True)
    op.create_index(op.f("ix_empresas_id_erp"), "empresas", ["id_erp"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_empresas_id_erp"), table_name="empresas")
    op.drop_index(op.f("ix_empresas_codigo"), table_name="empresas")
    op.drop_table("empresas")
