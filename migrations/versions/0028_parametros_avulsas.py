from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parametros_avulsas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("justificar_desde", sa.Date()),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_parametros_avulsas_uma_linha"),
    )


def downgrade() -> None:
    op.drop_table("parametros_avulsas")
