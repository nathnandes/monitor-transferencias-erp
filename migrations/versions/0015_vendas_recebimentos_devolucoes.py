from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendas_dias", sa.Column("versao", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_table(
        "vendas_recebimentos",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("dia", sa.Date(), primary_key=True),
        sa.Column("id_forma", sa.Integer(), primary_key=True),
        sa.Column("forma", sa.String(60), nullable=False),
        sa.Column("valor", sa.Numeric(18, 2), nullable=False),
        sa.Column("parcelas", sa.Integer(), nullable=False),
    )
    op.create_table(
        "devolucoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("id_erp", sa.String(50), nullable=False),
        sa.Column("numero_nota", sa.String(20), nullable=True),
        sa.Column("coi", sa.Integer(), nullable=False),
        sa.Column("data_devolucao", sa.Date(), nullable=False),
        sa.Column("valor_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("quantidade_itens", sa.Integer(), nullable=False),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("empresa_id", "id_erp", name="uq_devolucoes_empresa_id_erp"),
    )
    op.create_index("ix_devolucoes_data_empresa", "devolucoes", ["data_devolucao", "empresa_id"])


def downgrade() -> None:
    op.drop_table("devolucoes")
    op.drop_table("vendas_recebimentos")
    op.drop_column("vendas_dias", "versao")
