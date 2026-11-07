from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "limites_pendencia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("horas_atencao", sa.Integer(), nullable=False),
        sa.Column("horas_critico", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_limites_pendencia_uma_linha"),
        sa.CheckConstraint(
            "horas_atencao > 0 AND horas_atencao < horas_critico AND horas_critico <= 720",
            name="ck_limites_pendencia_horas",
        ),
    )


def downgrade() -> None:
    op.drop_table("limites_pendencia")
