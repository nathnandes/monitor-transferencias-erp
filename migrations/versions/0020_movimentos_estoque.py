from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIPOS_ANTES = (
    "'empresas', 'estoque', 'estoque_completo', 'transferencias', 'precos', "
    "'precos_completo', 'vendas'"
)


def _tipos(tipos: str) -> None:
    op.drop_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", type_="check"
    )
    op.create_check_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", f"tipo IN ({tipos})"
    )


def upgrade() -> None:
    op.create_table(
        "movimentos_estoque",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("coi", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("id_planilha", sa.String(50), nullable=False),
        sa.Column("sequencia", sa.String(20), nullable=True),
        sa.Column("id_produto", sa.String(50), nullable=False),
        sa.Column("id_subproduto", sa.String(50), nullable=True),
        sa.Column("descricao_produto", sa.String(300), nullable=True),
        sa.Column("quantidade", sa.Numeric(18, 4), nullable=True),
        sa.Column("valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('entrada_avulsa', 'saida_avulsa', 'balanco')",
            name="ck_movimentos_estoque_tipo",
        ),
    )
    op.create_index(
        "ix_movimentos_estoque_dia_empresa", "movimentos_estoque", ["dia", "empresa_id"]
    )
    op.create_index(
        "ix_movimentos_estoque_produto", "movimentos_estoque", ["id_produto", "id_subproduto"]
    )

    op.create_table(
        "movimentos_estoque_dias",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("dia", sa.Date(), primary_key=True),
        sa.Column("movimentos", sa.Integer(), nullable=False),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sincronizacao_id",
            sa.Integer(),
            sa.ForeignKey("sincronizacoes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    _tipos(f"{_TIPOS_ANTES}, 'movimentos_estoque'")


def downgrade() -> None:
    op.execute("DELETE FROM solicitacoes_sincronizacao WHERE tipo = 'movimentos_estoque'")
    _tipos(_TIPOS_ANTES)
    op.drop_table("movimentos_estoque_dias")
    op.drop_table("movimentos_estoque")
