from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transferencias", sa.Column("coi", sa.String(length=50), nullable=True))
    op.create_index("ix_transferencias_coi", "transferencias", ["coi"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_transferencias_coi", table_name="transferencias")
    op.drop_column("transferencias", "coi")
