from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendas_titulos",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id_planilha", sa.String(50), primary_key=True),
        sa.Column("id_titulo", sa.String(20), primary_key=True),
        sa.Column("parcela", sa.String(10), primary_key=True),
        sa.Column("id_forma", sa.Integer(), nullable=False),
        sa.Column("forma", sa.String(60), nullable=False),
        sa.Column("dia_lancamento", sa.Date(), nullable=False),
        sa.Column("vencimento", sa.Date()),
        sa.Column("dia_pagamento", sa.Date()),
        sa.Column("valor", sa.Numeric(18, 2), nullable=False),
        sa.Column("valor_pago", sa.Numeric(18, 2), nullable=False),
        sa.Column("valor_pendente", sa.Numeric(18, 2), nullable=False),
        sa.Column("juros", sa.Numeric(18, 2), nullable=False),
        sa.Column("desconto", sa.Numeric(18, 2), nullable=False),
    )
    op.create_index(
        "ix_vendas_titulos_lancamento", "vendas_titulos", ["empresa_id", "dia_lancamento"]
    )
    op.create_index(
        "ix_vendas_titulos_pagamento", "vendas_titulos", ["empresa_id", "dia_pagamento"]
    )
    op.drop_table("vendas_recebimentos")


def downgrade() -> None:
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
    op.execute(
        "INSERT INTO vendas_recebimentos (empresa_id, dia, id_forma, forma, valor, parcelas) "
        "SELECT empresa_id, dia_lancamento, id_forma, min(forma), sum(valor), count(*) "
        "FROM vendas_titulos GROUP BY empresa_id, dia_lancamento, id_forma"
    )
    op.drop_index("ix_vendas_titulos_pagamento", table_name="vendas_titulos")
    op.drop_index("ix_vendas_titulos_lancamento", table_name="vendas_titulos")
    op.drop_table("vendas_titulos")
