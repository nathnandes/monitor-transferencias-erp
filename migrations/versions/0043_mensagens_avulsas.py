from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mensagens_avulsas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("agendada_para", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "criada_por_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("criada_por_nome", sa.String(100), nullable=False),
        sa.Column("cancelada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(texto)) > 0", name="ck_mensagens_avulsas_texto"),
    )
    op.create_index("ix_mensagens_avulsas_agendada_para", "mensagens_avulsas", ["agendada_para"])
    op.create_index("ix_mensagens_avulsas_criada_por_id", "mensagens_avulsas", ["criada_por_id"])

    op.add_column("notificacoes", sa.Column("mensagem_id", sa.Integer(), nullable=True))
    op.create_index("ix_notificacoes_mensagem_id", "notificacoes", ["mensagem_id"])
    op.create_foreign_key(
        "notificacoes_mensagem_id_fkey",
        "notificacoes",
        "mensagens_avulsas",
        ["mensagem_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("ck_notificacoes_origem", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_origem",
        "notificacoes",
        "num_nonnulls(alerta_id, atividade_id, mensagem_id) = 1",
    )
    op.drop_constraint("ck_notificacoes_tipo", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_tipo",
        "notificacoes",
        "tipo IN ('ABERTURA', 'ESCALADA', 'RESOLUCAO', 'ATIVIDADE', 'MENSAGEM')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notificacoes WHERE mensagem_id IS NOT NULL")
    op.drop_constraint("ck_notificacoes_tipo", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_tipo",
        "notificacoes",
        "tipo IN ('ABERTURA', 'ESCALADA', 'RESOLUCAO', 'ATIVIDADE')",
    )
    op.drop_constraint("ck_notificacoes_origem", "notificacoes", type_="check")
    op.create_check_constraint(
        "ck_notificacoes_origem", "notificacoes", "num_nonnulls(alerta_id, atividade_id) = 1"
    )
    op.drop_constraint("notificacoes_mensagem_id_fkey", "notificacoes", type_="foreignkey")
    op.drop_index("ix_notificacoes_mensagem_id", table_name="notificacoes")
    op.drop_column("notificacoes", "mensagem_id")
    op.drop_index("ix_mensagens_avulsas_criada_por_id", table_name="mensagens_avulsas")
    op.drop_index("ix_mensagens_avulsas_agendada_para", table_name="mensagens_avulsas")
    op.drop_table("mensagens_avulsas")
