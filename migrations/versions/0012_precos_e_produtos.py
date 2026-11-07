from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIPOS_ANTES = "'empresas', 'estoque', 'estoque_completo', 'transferencias'"


def _tipos(tipos: str) -> None:
    op.drop_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", type_="check"
    )
    op.create_check_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", f"tipo IN ({tipos})"
    )


def _controle() -> list[sa.Column]:
    return [
        sa.Column("data_alteracao_erp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inativo_erp", sa.Boolean(), nullable=True),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ultima_sincronizacao_id",
            sa.Integer(),
            sa.ForeignKey("sincronizacoes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("id_produto", sa.String(50), nullable=False),
        sa.Column("id_subproduto", sa.String(50), nullable=False),
        sa.Column("descricao", sa.String(200), nullable=True),
        sa.Column("descricao_resumida", sa.String(100), nullable=True),
        sa.Column("referencia", sa.String(50), nullable=True),
        sa.Column("codigo_barras", sa.String(20), nullable=True),
        sa.Column("embalagem_saida", sa.String(10), nullable=True),
        sa.Column("marca", sa.String(100), nullable=True),
        sa.Column("divisao", sa.String(100), nullable=True),
        sa.Column("secao", sa.String(100), nullable=True),
        sa.Column("grupo", sa.String(100), nullable=True),
        sa.Column("subgrupo", sa.String(100), nullable=True),
        sa.Column("bloqueado_venda", sa.Boolean(), nullable=True),
        *_controle(),
        sa.UniqueConstraint("id_produto", "id_subproduto", name="uq_produtos_produto"),
    )
    op.create_index("ix_produtos_ultima_sincronizacao_id", "produtos", ["ultima_sincronizacao_id"])

    valor = sa.Numeric(15, 6)
    op.create_table(
        "precos_produto_empresa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("id_produto", sa.String(50), nullable=False),
        sa.Column("id_subproduto", sa.String(50), nullable=False),
        sa.Column("preco_varejo", valor, nullable=True),
        sa.Column("preco_promocao_varejo", valor, nullable=True),
        sa.Column("inicio_promocao_varejo", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fim_promocao_varejo", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preco_atacado", valor, nullable=True),
        sa.Column("preco_promocao_atacado", valor, nullable=True),
        sa.Column("inicio_promocao_atacado", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fim_promocao_atacado", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custo_reposicao", valor, nullable=True),
        sa.Column("custo_gerencial", valor, nullable=True),
        sa.Column("custo_nota_fiscal", valor, nullable=True),
        *_controle(),
        sa.UniqueConstraint(
            "empresa_id", "id_produto", "id_subproduto", name="uq_precos_produto_empresa_chave"
        ),
    )
    op.create_index(
        "ix_precos_produto_empresa_produto",
        "precos_produto_empresa",
        ["id_produto", "id_subproduto"],
    )
    op.create_index(
        "ix_precos_produto_empresa_ultima_sincronizacao_id",
        "precos_produto_empresa",
        ["ultima_sincronizacao_id"],
    )

    _tipos(f"{_TIPOS_ANTES}, 'precos', 'precos_completo'")


def downgrade() -> None:
    op.execute("DELETE FROM solicitacoes_sincronizacao WHERE tipo IN ('precos', 'precos_completo')")
    _tipos(_TIPOS_ANTES)
    op.drop_table("precos_produto_empresa")
    op.drop_table("produtos")
