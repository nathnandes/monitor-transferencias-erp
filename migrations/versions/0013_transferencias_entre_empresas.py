from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transferencias",
        sa.Column("entre_empresas", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_index("ix_transferencias_entre_empresas", "transferencias", ["entre_empresas"])

    op.execute(
        """
        WITH novo AS (
            SELECT id,
                   CASE
                       WHEN coalesce(btrim(coi), '') = '' THEN '["nota de saida sem COI"]'::jsonb
                       WHEN id_erp_entrada IS NOT NULL AND coalesce(btrim(coi_entrada), '') = ''
                           THEN '["nota de entrada sem COI"]'::jsonb
                       ELSE '[]'::jsonb
                   END AS problemas
            FROM transferencias
        )
        UPDATE transferencias t
        SET entre_empresas = jsonb_array_length(t.problemas_coi) = 0
                             OR jsonb_array_length(novo.problemas) > 0,
            problemas_coi = novo.problemas
        FROM novo
        WHERE novo.id = t.id
        """
    )


def downgrade() -> None:

    op.drop_index("ix_transferencias_entre_empresas", table_name="transferencias")
    op.drop_column("transferencias", "entre_empresas")
