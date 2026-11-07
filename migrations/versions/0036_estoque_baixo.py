from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parametros_estoque_baixo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("dias_cobertura", sa.Integer(), nullable=False),
        sa.Column(
            "dias_por_empresa",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("janela_dias", sa.Integer(), server_default="30", nullable=False),
        sa.Column("horarios", postgresql.ARRAY(sa.String(5)), nullable=False),
        sa.Column("ultima_execucao", sa.DateTime(timezone=True)),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_parametros_estoque_baixo_uma_linha"),
        sa.CheckConstraint(
            "dias_cobertura BETWEEN 1 AND 365", name="ck_parametros_estoque_baixo_dias"
        ),
        sa.CheckConstraint(
            "janela_dias BETWEEN 7 AND 180", name="ck_parametros_estoque_baixo_janela"
        ),
        sa.CheckConstraint(
            "cardinality(horarios) BETWEEN 1 AND 6", name="ck_parametros_estoque_baixo_horarios"
        ),
    )
    op.create_table(
        "estoque_baixo_avisados",
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id_produto", sa.String(50), primary_key=True),
        sa.Column("id_subproduto", sa.String(50), primary_key=True),
        sa.Column("avisado_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("estoque_baixo_avisados")
    op.drop_table("parametros_estoque_baixo")
