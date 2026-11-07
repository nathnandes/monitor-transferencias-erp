from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alerta_destinos",
        sa.Column("canal", sa.String(20), server_default="telegram", nullable=False),
    )
    op.create_check_constraint(
        "ck_alerta_destinos_canal", "alerta_destinos", "canal IN ('telegram', 'whatsapp')"
    )
    op.create_check_constraint(
        "ck_alerta_destinos_numero", "alerta_destinos", "canal <> 'whatsapp' OR chat_id IS NOT NULL"
    )
    op.drop_constraint("ck_notificacoes_canal", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_canal", "notificacoes", "canal IN ('telegram', 'whatsapp')"
    )


def downgrade() -> None:

    op.execute("DELETE FROM notificacoes WHERE canal = 'whatsapp'")
    op.execute("DELETE FROM alerta_destinos WHERE canal = 'whatsapp'")
    op.drop_constraint("ck_notificacoes_canal", "notificacoes", type_="check")
    op.create_check_constraint("ck_notificacoes_canal", "notificacoes", "canal IN ('telegram')")
    op.drop_constraint("ck_alerta_destinos_numero", "alerta_destinos", type_="check")
    op.drop_constraint("ck_alerta_destinos_canal", "alerta_destinos", type_="check")
    op.drop_column("alerta_destinos", "canal")
