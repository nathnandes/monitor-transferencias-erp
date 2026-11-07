from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ABAS_NOVAS = (
    "VENDAS.GERAL",
    "VENDAS.EMPRESA_1",
    "VENDAS.EMPRESA_2",
    "VENDAS.EMPRESA_3",
    "VENDAS.EMPRESA_6",
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE perfis_acesso SET abas = abas || CAST(:novas AS jsonb), updated_at = now() "
            "WHERE modulos ? 'VENDAS' AND NOT abas ?| CAST(:codigos AS text[])"
        ),
        {"novas": "[" + ",".join(f'"{a}"' for a in ABAS_NOVAS) + "]", "codigos": list(ABAS_NOVAS)},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE perfis_acesso SET abas = abas - CAST(:codigos AS text[]) "
            "WHERE abas ?| CAST(:codigos AS text[])"
        ),
        {"codigos": list(ABAS_NOVAS)},
    )
