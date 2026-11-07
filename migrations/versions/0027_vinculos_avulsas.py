from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vinculos_avulsas",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("entrada_id_planilha", sa.String(50), primary_key=True),
        sa.Column("saida_id_planilha", sa.String(50), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("empresa_id", "saida_id_planilha", name="uq_vinculos_avulsas_saida"),
    )
    op.add_column(
        "justificativas_avulsas",
        sa.Column("pelo_vinculo", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("justificativas_avulsas", "pelo_vinculo")
    op.drop_table("vinculos_avulsas")
