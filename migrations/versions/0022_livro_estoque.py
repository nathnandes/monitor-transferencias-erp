from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORIAS = (
    "venda",
    "devolucao_venda",
    "compra",
    "devolucao_compra",
    "transferencia_entrada",
    "transferencia_saida",
    "entrada_avulsa",
    "saida_avulsa",
    "balanco",
    "perda",
    "uso_consumo",
    "producao",
    "bonificacao",
    "remessa",
    "outros",
    "nao_classificado",
)
_ANTES = ("entrada_avulsa", "saida_avulsa", "balanco")


def _check(valores: tuple[str, ...]) -> str:
    lista = ", ".join(repr(v) for v in valores)
    return (
        "ALTER TABLE movimentos_estoque DROP CONSTRAINT IF EXISTS ck_movimentos_estoque_tipo;"
        " ALTER TABLE movimentos_estoque ADD CONSTRAINT ck_movimentos_estoque_tipo"
        f" CHECK (tipo IN ({lista}))"
    )


UPGRADE = (
    "ALTER TABLE movimentos_estoque ALTER COLUMN tipo TYPE VARCHAR(30)",
    _check(_CATEGORIAS),
    "ALTER TABLE movimentos_estoque ADD COLUMN IF NOT EXISTS operacao VARCHAR(100)",
    "CREATE INDEX IF NOT EXISTS ix_movimentos_estoque_empresa_produto_dia"
    " ON movimentos_estoque (empresa_id, id_produto, id_subproduto, dia)",
    "ALTER TABLE movimentos_estoque_dias"
    " ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1",
)


def upgrade() -> None:
    for sql in UPGRADE:
        op.execute(sql)


def downgrade() -> None:
    op.execute("ALTER TABLE movimentos_estoque_dias DROP COLUMN IF EXISTS versao")
    op.execute("DROP INDEX IF EXISTS ix_movimentos_estoque_empresa_produto_dia")
    op.execute("ALTER TABLE movimentos_estoque DROP COLUMN IF EXISTS operacao")
    op.execute(f"DELETE FROM movimentos_estoque WHERE tipo NOT IN {_ANTES!r}")
    op.execute(_check(_ANTES))
    op.execute("ALTER TABLE movimentos_estoque ALTER COLUMN tipo TYPE VARCHAR(20)")
