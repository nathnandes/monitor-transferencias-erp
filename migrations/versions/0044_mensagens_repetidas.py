from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mensagens_avulsas", sa.Column("horario", sa.Time(), nullable=True))
    op.add_column(
        "mensagens_avulsas",
        sa.Column(
            "dias_semana", ARRAY(sa.Integer()), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column(
        "mensagens_avulsas",
        sa.Column("destinos", ARRAY(sa.Integer()), server_default=sa.text("'{}'"), nullable=False),
    )

    op.execute(
        """
        UPDATE mensagens_avulsas m
           SET destinos = sub.ids
          FROM (SELECT mensagem_id, array_agg(DISTINCT destino_id) AS ids
                  FROM notificacoes
                 WHERE mensagem_id IS NOT NULL AND destino_id IS NOT NULL
                 GROUP BY mensagem_id) sub
         WHERE sub.mensagem_id = m.id
        """
    )
    op.create_check_constraint(
        "ck_mensagens_avulsas_dias_semana",
        "mensagens_avulsas",
        "horario IS NULL OR cardinality(dias_semana) > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_mensagens_avulsas_dias_semana", "mensagens_avulsas", type_="check")
    op.drop_column("mensagens_avulsas", "destinos")
    op.drop_column("mensagens_avulsas", "dias_semana")
    op.drop_column("mensagens_avulsas", "horario")
