from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notas_movimento", sa.Column("cnpj_destinatario", sa.String(14)))
    op.add_column("notas_movimento", sa.Column("nome_destinatario", sa.String(200)))
    op.add_column("notas_movimento", sa.Column("cancelada", sa.Boolean()))
    op.add_column(
        "notas_movimento",
        sa.Column("destinatario_lido", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "ix_notas_movimento_cnpj_destinatario",
        "notas_movimento",
        ["cnpj_destinatario"],
        postgresql_where=sa.text("cnpj_destinatario IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notas_movimento_cnpj_destinatario", table_name="notas_movimento")
    op.drop_column("notas_movimento", "destinatario_lido")
    op.drop_column("notas_movimento", "cancelada")
    op.drop_column("notas_movimento", "nome_destinatario")
    op.drop_column("notas_movimento", "cnpj_destinatario")
