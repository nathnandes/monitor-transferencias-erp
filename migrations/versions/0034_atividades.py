from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "atividades",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("usuario_nome", sa.String(100), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("resumo", sa.String(300), nullable=False),
        sa.Column("detalhe", sa.Text()),
        sa.Column(
            "empresas",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ocorrida_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_atividades_tipo", "atividades", ["tipo"])
    op.create_index("ix_atividades_usuario_id", "atividades", ["usuario_id"])
    op.create_index("ix_atividades_ocorrida_em", "atividades", ["ocorrida_em"])

    op.alter_column("notificacoes", "alerta_id", nullable=True)
    op.add_column("notificacoes", sa.Column("atividade_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_notificacoes_atividade_id", "notificacoes", ["atividade_id"])
    op.create_foreign_key(
        "notificacoes_atividade_id_fkey",
        "notificacoes",
        "atividades",
        ["atividade_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_notificacoes_origem", "notificacoes", "num_nonnulls(alerta_id, atividade_id) = 1"
    )
    op.drop_constraint("ck_notificacoes_tipo", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_tipo",
        "notificacoes",
        "tipo IN ('ABERTURA', 'ESCALADA', 'RESOLUCAO', 'ATIVIDADE')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notificacoes WHERE atividade_id IS NOT NULL")
    op.drop_constraint("ck_notificacoes_tipo", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_tipo", "notificacoes", "tipo IN ('ABERTURA', 'ESCALADA', 'RESOLUCAO')"
    )
    op.drop_constraint("ck_notificacoes_origem", "notificacoes", type_="check")
    op.drop_constraint("notificacoes_atividade_id_fkey", "notificacoes", type_="foreignkey")
    op.drop_index("ix_notificacoes_atividade_id", table_name="notificacoes")
    op.drop_column("notificacoes", "atividade_id")
    op.alter_column("notificacoes", "alerta_id", nullable=False)
    op.drop_table("atividades")
