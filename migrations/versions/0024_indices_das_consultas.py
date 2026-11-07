from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDICES = (
    ("ix_movimentos_estoque_coi_dia_empresa", "movimentos_estoque", "coi, dia, empresa_id"),
    ("ix_movimentos_estoque_subproduto", "movimentos_estoque", "id_subproduto"),
    ("ix_vendas_id_vendedor", "vendas", "id_vendedor"),
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '30s'")
    op.execute(
        "UPDATE movimentos_estoque SET id_subproduto = id_produto WHERE id_subproduto IS NULL"
    )
    op.alter_column("movimentos_estoque", "id_subproduto", nullable=False)
    op.execute("UPDATE transferencias SET status = upper(status) WHERE status <> upper(status)")
    op.execute(
        "ALTER TABLE transferencias DROP CONSTRAINT IF EXISTS ck_transferencias_status_maiusculo"
    )
    op.create_check_constraint(
        "ck_transferencias_status_maiusculo", "transferencias", "status = upper(status)"
    )
    with op.get_context().autocommit_block():
        for nome, tabela, colunas in _INDICES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {nome} ON {tabela} ({colunas})")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for nome, _, _ in _INDICES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {nome}")
    op.drop_constraint("ck_transferencias_status_maiusculo", "transferencias", type_="check")
    op.alter_column("movimentos_estoque", "id_subproduto", nullable=True)
