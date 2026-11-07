from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notas_movimento", sa.Column("cnpj_emitente", sa.String(14)))
    op.add_column("notas_movimento", sa.Column("nome_emitente", sa.String(200)))
    op.add_column(
        "notas_movimento",
        sa.Column("emitente_lido", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("notas_movimento", "emitente_lido")
    op.drop_column("notas_movimento", "nome_emitente")
    op.drop_column("notas_movimento", "cnpj_emitente")
