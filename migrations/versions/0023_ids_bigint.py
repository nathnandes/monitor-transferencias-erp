from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABELAS = (
    "estoque_consolidado",
    "movimentos_estoque",
    "vendas",
    "vendas_itens",
    "devolucoes",
    "transferencias_itens",
)


def _mudar(tipo: str) -> None:
    for tabela in _TABELAS:
        op.execute(f"ALTER TABLE {tabela} ALTER COLUMN id TYPE {tipo}")
        op.execute(
            f"DO $$ BEGIN EXECUTE format('ALTER SEQUENCE %s AS {tipo}',"
            f" pg_get_serial_sequence('{tabela}', 'id')); END $$"
        )
    op.execute(f"ALTER TABLE vendas_itens ALTER COLUMN venda_id TYPE {tipo}")


def upgrade() -> None:
    _mudar("bigint")


def downgrade() -> None:

    _mudar("integer")
