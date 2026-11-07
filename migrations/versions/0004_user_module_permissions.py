from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_module_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=30), nullable=False),
        sa.Column("can_view", sa.Boolean(), server_default="false", nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "module", name="uq_user_module_permissions_user_module"),
        sa.CheckConstraint(
            "module IN ('DASHBOARD', 'TRANSFERENCIAS', 'ESTOQUE', 'VENDAS', "
            "'FINANCEIRO', 'ALERTAS', 'ADMINISTRACAO')",
            name="ck_user_module_permissions_module",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_module_permissions")
