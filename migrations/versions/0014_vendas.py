from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIPOS_ANTES = (
    "'empresas', 'estoque', 'estoque_completo', 'transferencias', 'precos', 'precos_completo'"
)


def _tipos(tipos: str) -> None:
    op.drop_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", type_="check"
    )
    op.create_check_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", f"tipo IN ({tipos})"
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "vendas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("id_erp", sa.String(50), nullable=False),
        sa.Column("numero_nota", sa.String(20), nullable=True),
        sa.Column("serie", sa.String(10), nullable=True),
        sa.Column("modelo", sa.String(10), nullable=True),
        sa.Column("coi", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(20), nullable=False),
        sa.Column("data_venda", sa.Date(), nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelada", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("valor_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("valor_desconto", sa.Numeric(18, 2), nullable=False),
        sa.Column("quantidade_itens", sa.Integer(), nullable=False),
        sa.Column("id_vendedor", sa.String(50), nullable=True),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("empresa_id", "id_erp", name="uq_vendas_empresa_id_erp"),
        sa.CheckConstraint("quantidade_itens >= 0", name="ck_vendas_quantidade_itens"),
    )
    op.create_index("ix_vendas_data_venda_empresa", "vendas", ["data_venda", "empresa_id"])
    op.create_index("ix_vendas_canal", "vendas", ["canal"])

    op.create_table(
        "vendas_itens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "venda_id", sa.Integer(), sa.ForeignKey("vendas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("sequencia", sa.String(20), nullable=True),
        sa.Column("id_produto", sa.String(50), nullable=False),
        sa.Column("id_subproduto", sa.String(50), nullable=True),
        sa.Column("descricao_produto", sa.String(300), nullable=True),
        sa.Column("cfop", sa.String(10), nullable=True),
        sa.Column("quantidade", sa.Numeric(18, 4), nullable=True),
        sa.Column("valor_liquido", sa.Numeric(18, 4), nullable=True),
        sa.Column("valor_desconto", sa.Numeric(18, 4), nullable=True),
    )
    op.create_index("ix_vendas_itens_venda_id", "vendas_itens", ["venda_id"])
    op.create_index("ix_vendas_itens_produto", "vendas_itens", ["id_produto", "id_subproduto"])

    op.create_table(
        "vendas_dias",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("dia", sa.Date(), primary_key=True),
        sa.Column("notas", sa.Integer(), nullable=False),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sincronizacao_id",
            sa.Integer(),
            sa.ForeignKey("sincronizacoes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    _tipos(f"{_TIPOS_ANTES}, 'vendas'")


def downgrade() -> None:
    op.execute("DELETE FROM solicitacoes_sincronizacao WHERE tipo = 'vendas'")
    _tipos(_TIPOS_ANTES)
    op.drop_table("vendas_dias")
    op.drop_table("vendas_itens")
    op.drop_table("vendas")
