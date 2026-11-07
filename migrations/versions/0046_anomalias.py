from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomalias_execucoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("versao_modelo", sa.String(100), nullable=False),
        sa.Column("notas_treino", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("notas_avaliadas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("notas_sinalizadas", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("limiar", sa.Double(), nullable=True),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('sucesso', 'sem_historico', 'erro')",
            name="ck_anomalias_execucoes_status",
        ),
    )
    op.create_index("ix_anomalias_execucoes_concluida_em", "anomalias_execucoes", ["concluida_em"])
    op.create_table(
        "anomalias_transferencias",
        sa.Column(
            "transferencia_id",
            sa.Integer(),
            sa.ForeignKey("transferencias.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "execucao_id",
            sa.Integer(),
            sa.ForeignKey("anomalias_execucoes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("score", sa.Double(), nullable=False),
        sa.Column("limiar", sa.Double(), nullable=False),
        sa.Column("sinalizada", sa.Boolean(), nullable=False),
        sa.Column("com_entrada", sa.Boolean(), nullable=False),
        sa.Column("motivos", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("avaliada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_anomalias_transferencias_execucao_id", "anomalias_transferencias", ["execucao_id"]
    )
    op.create_index(
        "ix_anomalias_transferencias_sinalizadas",
        "anomalias_transferencias",
        ["score"],
        postgresql_where=sa.text("sinalizada"),
    )


def downgrade() -> None:
    op.drop_table("anomalias_transferencias")
    op.drop_table("anomalias_execucoes")
