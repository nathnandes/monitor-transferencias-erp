from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resumos_diarios",
        sa.Column("dia", sa.Date, primary_key=True),
        sa.Column("texto", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDENTE"),
        sa.Column("tentativas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("proxima_tentativa_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'ENVIADO', 'FALHA')", name="ck_resumos_diarios_status"
        ),
        sa.CheckConstraint("tentativas >= 0", name="ck_resumos_diarios_tentativas"),
    )


def downgrade() -> None:
    op.drop_table("resumos_diarios")
