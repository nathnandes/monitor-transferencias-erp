from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _usuario_e_data() -> list[sa.Column]:
    return [
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "metas_vendas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nivel", sa.String(10), nullable=False),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id", ondelete="CASCADE")),
        sa.Column("id_vendedor", sa.String(50)),
        sa.Column("periodo", sa.String(10), nullable=False),
        sa.Column("referencia", sa.Date()),
        sa.Column("valor", sa.Numeric(18, 2), nullable=False),
        *_usuario_e_data(),
        sa.CheckConstraint(
            "nivel IN ('GRUPO', 'EMPRESA', 'VENDEDOR')", name="ck_metas_vendas_nivel"
        ),
        sa.CheckConstraint("periodo IN ('DIA', 'SEMANA', 'MES')", name="ck_metas_vendas_periodo"),
        sa.CheckConstraint("valor > 0", name="ck_metas_vendas_valor"),
        sa.CheckConstraint(
            "(nivel = 'GRUPO' AND empresa_id IS NULL AND id_vendedor IS NULL)"
            " OR (nivel = 'EMPRESA' AND empresa_id IS NOT NULL AND id_vendedor IS NULL)"
            " OR (nivel = 'VENDEDOR' AND empresa_id IS NULL AND id_vendedor IS NOT NULL)",
            name="ck_metas_vendas_alvo",
        ),
        sa.CheckConstraint(
            "referencia IS NULL OR periodo = 'DIA'"
            " OR (periodo = 'SEMANA' AND extract(isodow FROM referencia) = 1)"
            " OR (periodo = 'MES' AND extract(day FROM referencia) = 1)",
            name="ck_metas_vendas_referencia",
        ),
    )
    op.create_index("ix_metas_vendas_empresa_id", "metas_vendas", ["empresa_id"])
    op.create_index(
        "uq_metas_vendas_alvo_periodo",
        "metas_vendas",
        ["nivel", "empresa_id", "id_vendedor", "periodo", "referencia"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        "parametros_metas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marcos", postgresql.ARRAY(sa.Integer()), nullable=False),
        *_usuario_e_data(),
        sa.CheckConstraint("id = 1", name="ck_parametros_metas_uma_linha"),
        sa.CheckConstraint(
            "cardinality(marcos) BETWEEN 1 AND 10 AND 0 < ALL(marcos) AND 1000 >= ALL(marcos)",
            name="ck_parametros_metas_marcos",
        ),
    )

    op.create_table(
        "metas_avisos",
        sa.Column(
            "meta_id",
            sa.Integer(),
            sa.ForeignKey("metas_vendas.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("periodo_inicio", sa.Date(), primary_key=True),
        sa.Column("marco", sa.Integer(), primary_key=True),
        sa.Column(
            "avisado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column(
        "atividades",
        sa.Column(
            "valores",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("atividades", "valores")
    op.drop_table("metas_avisos")
    op.drop_table("parametros_metas")
    op.drop_index("uq_metas_vendas_alvo_periodo", table_name="metas_vendas")
    op.drop_index("ix_metas_vendas_empresa_id", table_name="metas_vendas")
    op.drop_table("metas_vendas")
