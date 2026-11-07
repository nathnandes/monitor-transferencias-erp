from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE perfis_acesso SET abas = abas || '[\"ESTOQUE.LOJA\"]'::jsonb, "
            "updated_at = now() WHERE abas ? 'ESTOQUE.SALDOS' AND NOT abas ? 'ESTOQUE.LOJA'"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE perfis_acesso SET abas = abas - 'ESTOQUE.LOJA' WHERE abas ? 'ESTOQUE.LOJA'")
    )
