from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
        for nome in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.add_column("empresas", sa.Column("bairro", sa.String(length=100), nullable=True))

    op.add_column(
        "sincronizacoes",
        sa.Column("empresas_processadas", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "sincronizacoes",
        sa.Column("paginas_processadas", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("sincronizacoes", sa.Column("sincronizacao_pai_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "sincronizacoes_sincronizacao_pai_id_fkey",
        "sincronizacoes",
        "sincronizacoes",
        ["sincronizacao_pai_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_sincronizacoes_sincronizacao_pai_id", "sincronizacoes", ["sincronizacao_pai_id"]
    )
    op.create_check_constraint(
        "ck_sincronizacoes_contadores_execucao",
        "sincronizacoes",
        "empresas_processadas >= 0 AND paginas_processadas >= 0",
    )

    op.create_table(
        "solicitacoes_sincronizacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDENTE", nullable=False),
        sa.Column("solicitado_por", sa.String(length=50), nullable=True),
        sa.Column(
            "solicitado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sincronizacao_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "tipo IN ('empresas', 'estoque')", name="ck_solicitacoes_sincronizacao_tipo"
        ),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'EM_EXECUCAO', 'CONCLUIDA')",
            name="ck_solicitacoes_sincronizacao_status",
        ),
        sa.ForeignKeyConstraint(["sincronizacao_id"], ["sincronizacoes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_solicitacoes_sincronizacao_tipo_pendente",
        "solicitacoes_sincronizacao",
        ["tipo"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDENTE'"),
    )
    op.create_index(
        "ix_solicitacoes_sincronizacao_status_solicitado",
        "solicitacoes_sincronizacao",
        ["status", "solicitado_em"],
    )

    op.create_table(
        "integracao_erros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sincronizacao_id", sa.Integer(), nullable=True),
        sa.Column("id_erp_empresa", sa.String(length=50), nullable=True),
        sa.Column("endpoint", sa.String(length=200), nullable=True),
        sa.Column("status_http", sa.Integer(), nullable=True),
        sa.Column("tipo_erro", sa.String(length=100), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("tentativa", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "ocorrido_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sincronizacao_id"], ["sincronizacoes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integracao_erros_sincronizacao_id", "integracao_erros", ["sincronizacao_id"]
    )
    op.create_index("ix_integracao_erros_ocorrido_em", "integracao_erros", ["ocorrido_em"])

    op.create_table(
        "estoque_empresa_local_lote",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("id_produto", sa.String(length=50), nullable=False),
        sa.Column("id_subproduto", sa.String(length=50), nullable=False),
        sa.Column("id_local_estoque", sa.String(length=50), nullable=False),
        sa.Column("descricao_local_estoque", sa.String(length=200), nullable=True),
        sa.Column("utiliza_lote", sa.Boolean(), nullable=True),
        sa.Column("descricao_lote", sa.String(length=200), server_default="", nullable=False),
        sa.Column("permite_estoque_negativo", sa.Boolean(), nullable=True),
        sa.Column("saldo_atual", sa.Numeric(15, 3), nullable=True),
        sa.Column("saldo_reservado", sa.Numeric(15, 3), nullable=True),
        sa.Column("saldo_disponivel", sa.Numeric(15, 3), nullable=True),
        sa.Column("data_alteracao_erp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("removido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultima_sincronizacao_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ultima_sincronizacao_id"], ["sincronizacoes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id",
            "id_produto",
            "id_subproduto",
            "id_local_estoque",
            "descricao_lote",
            name="uq_estoque_empresa_local_lote_chave",
        ),
    )
    op.create_index(
        "ix_estoque_empresa_local_lote_produto",
        "estoque_empresa_local_lote",
        ["id_produto", "id_subproduto"],
    )
    op.create_index(
        "ix_estoque_empresa_local_lote_ultima_sincronizacao_id",
        "estoque_empresa_local_lote",
        ["ultima_sincronizacao_id"],
    )

    op.create_table(
        "estoque_consolidado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_produto", sa.String(length=50), nullable=False),
        sa.Column("id_subproduto", sa.String(length=50), nullable=False),
        sa.Column("saldo_atual_total", sa.Numeric(15, 3), nullable=True),
        sa.Column("saldo_reservado_total", sa.Numeric(15, 3), nullable=True),
        sa.Column("saldo_disponivel_total", sa.Numeric(15, 3), nullable=True),
        sa.Column("empresas_com_estoque", sa.Integer(), server_default="0", nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id_produto", "id_subproduto", name="uq_estoque_consolidado_produto"),
    )


def downgrade() -> None:
    op.drop_table("estoque_consolidado")
    op.drop_index(
        "ix_estoque_empresa_local_lote_ultima_sincronizacao_id",
        table_name="estoque_empresa_local_lote",
    )
    op.drop_index("ix_estoque_empresa_local_lote_produto", table_name="estoque_empresa_local_lote")
    op.drop_table("estoque_empresa_local_lote")
    op.drop_index("ix_integracao_erros_ocorrido_em", table_name="integracao_erros")
    op.drop_index("ix_integracao_erros_sincronizacao_id", table_name="integracao_erros")
    op.drop_table("integracao_erros")
    op.drop_index(
        "ix_solicitacoes_sincronizacao_status_solicitado",
        table_name="solicitacoes_sincronizacao",
    )
    op.drop_index(
        "uq_solicitacoes_sincronizacao_tipo_pendente", table_name="solicitacoes_sincronizacao"
    )
    op.drop_table("solicitacoes_sincronizacao")
    op.drop_constraint("ck_sincronizacoes_contadores_execucao", "sincronizacoes", type_="check")
    op.drop_index("ix_sincronizacoes_sincronizacao_pai_id", table_name="sincronizacoes")
    op.drop_constraint(
        "sincronizacoes_sincronizacao_pai_id_fkey", "sincronizacoes", type_="foreignkey"
    )
    op.drop_column("sincronizacoes", "sincronizacao_pai_id")
    op.drop_column("sincronizacoes", "paginas_processadas")
    op.drop_column("sincronizacoes", "empresas_processadas")
    op.drop_column("empresas", "bairro")
