from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notas_movimento",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id_planilha", sa.String(50), primary_key=True),
        sa.Column("saida", sa.Boolean(), nullable=False),
        sa.Column("encontrado", sa.Boolean(), nullable=False),
        sa.Column("numero", sa.String(20)),
        sa.Column("momento", sa.DateTime(timezone=True)),
        sa.Column("usuario", sa.String(100)),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notas_movimento")
