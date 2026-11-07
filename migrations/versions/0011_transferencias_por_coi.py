from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tipos(tipos: str) -> None:
    op.drop_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", type_="check"
    )
    op.create_check_constraint(
        "ck_solicitacoes_sincronizacao_tipo", "solicitacoes_sincronizacao", f"tipo IN ({tipos})"
    )


def upgrade() -> None:
    op.add_column("empresas", sa.Column("cnpj", sa.String(14), nullable=True))
    op.create_index("ix_empresas_cnpj", "empresas", ["cnpj"])

    op.alter_column("transferencias", "empresa_destino_id", nullable=True)
    op.add_column("transferencias", sa.Column("chave_nfe", sa.String(44), nullable=True))
    op.add_column("transferencias", sa.Column("numero_nota", sa.String(20), nullable=True))
    op.add_column("transferencias", sa.Column("id_erp_entrada", sa.String(50), nullable=True))
    op.add_column("transferencias", sa.Column("coi_entrada", sa.String(50), nullable=True))
    op.add_column(
        "transferencias",
        sa.Column(
            "empresa_entrada_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "transferencias",
        sa.Column(
            "problemas_coi",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_transferencias_chave_nfe",
        "transferencias",
        ["chave_nfe"],
        unique=True,
        postgresql_where=sa.text("chave_nfe IS NOT NULL"),
    )

    _tipos("'empresas', 'estoque', 'estoque_completo', 'transferencias'")

    op.execute(
        "UPDATE alertas SET status = 'RESOLVIDO', resolvido_em = now() "
        "WHERE regra = 'transferencia_sem_coi' AND status = 'ABERTO'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM solicitacoes_sincronizacao WHERE tipo = 'transferencias'")
    _tipos("'empresas', 'estoque', 'estoque_completo'")

    op.drop_index("uq_transferencias_chave_nfe", table_name="transferencias")
    op.drop_column("transferencias", "problemas_coi")
    op.drop_column("transferencias", "empresa_entrada_id")
    op.drop_column("transferencias", "coi_entrada")
    op.drop_column("transferencias", "id_erp_entrada")
    op.drop_column("transferencias", "numero_nota")
    op.drop_column("transferencias", "chave_nfe")

    op.alter_column("transferencias", "empresa_destino_id", nullable=False)

    op.drop_index("ix_empresas_cnpj", table_name="empresas")
    op.drop_column("empresas", "cnpj")
