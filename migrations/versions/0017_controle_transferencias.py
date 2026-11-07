from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transferencias", sa.Column("valor_total", sa.Numeric(18, 2), nullable=True))
    op.add_column("transferencias", sa.Column("usuario_emissao", sa.String(100), nullable=True))
    op.add_column(
        "transferencias_itens", sa.Column("valor_total", sa.Numeric(18, 2), nullable=True)
    )
    op.add_column("transferencias_itens", sa.Column("cfop_saida", sa.String(10), nullable=True))
    op.add_column("transferencias_itens", sa.Column("cfop_entrada", sa.String(10), nullable=True))

    op.execute(
        """
        UPDATE transferencias
           SET valor_total = (raw_data -> 'saida' ->> 'valor_contabil')::numeric
         WHERE raw_data -> 'saida' ->> 'valor_contabil' ~ '^-?[0-9]+(\\.[0-9]+)?$'
        """
    )

    op.create_table(
        "prazos_rota",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "empresa_origem_id",
            sa.Integer,
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "empresa_destino_id",
            sa.Integer,
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("horas", sa.Integer, nullable=False),
        sa.Column("atualizado_por", sa.String(50), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("empresa_origem_id", "empresa_destino_id", name="uq_prazos_rota"),
        sa.CheckConstraint("horas > 0 AND horas <= 720", name="ck_prazos_rota_horas"),
    )

    op.create_table(
        "transferencias_tratativas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "transferencia_id",
            sa.Integer,
            sa.ForeignKey("transferencias.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "usuario_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column("situacao", sa.String(20), nullable=False),
        sa.Column("observacao", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "situacao IN ('EM_ANALISE', 'RESOLVIDA')", name="ck_tratativas_situacao"
        ),
    )


def downgrade() -> None:
    op.drop_table("transferencias_tratativas")
    op.drop_table("prazos_rota")
    op.drop_column("transferencias_itens", "cfop_entrada")
    op.drop_column("transferencias_itens", "cfop_saida")
    op.drop_column("transferencias_itens", "valor_total")
    op.drop_column("transferencias", "usuario_emissao")
    op.drop_column("transferencias", "valor_total")
