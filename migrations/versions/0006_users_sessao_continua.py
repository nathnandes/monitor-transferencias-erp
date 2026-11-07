from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("sessao_continua", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_sessao_continua_so_operador",
        "users",
        "NOT (sessao_continua AND role = 'ADMIN')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_sessao_continua_so_operador", "users", type_="check")
    op.drop_column("users", "sessao_continua")
