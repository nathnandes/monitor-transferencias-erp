from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "estoque_empresa_local_lote", sa.Column("inativo_erp", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "estoque_empresa_local_lote",
        sa.Column("ausencias_leitura_completa", sa.Integer(), server_default="0", nullable=False),
    )
    op.drop_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", type_="check"
    )
    op.create_check_constraint(
        "ck_solicitacoes_sincronizacao_tipo",
        "solicitacoes_sincronizacao",
        "tipo IN ('empresas', 'estoque', 'estoque_completo')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM solicitacoes_sincronizacao WHERE tipo = 'estoque_completo'")
    op.drop_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", type_="check"
    )
    op.create_check_constraint(
        "ck_solicitacoes_sincronizacao_tipo",
        "solicitacoes_sincronizacao",
        "tipo IN ('empresas', 'estoque')",
    )
    op.drop_column("estoque_empresa_local_lote", "ausencias_leitura_completa")
    op.drop_column("estoque_empresa_local_lote", "inativo_erp")
