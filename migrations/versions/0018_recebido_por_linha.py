from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.execute(
        """
        WITH grupos AS (
            SELECT transferencia_id, id_produto_erp, min(quantidade_processada) AS total
              FROM transferencias_itens
             WHERE quantidade_processada IS NOT NULL
             GROUP BY transferencia_id, id_produto_erp
            HAVING count(*) > 1
               AND count(*) = count(quantidade_processada)
               AND min(quantidade_processada) = max(quantidade_processada)
               -- Ja repartido (cada linha recebeu o que enviou e todas por acaso
               -- iguais) tambem tem min = max: so o formato antigo soma diferente.
               AND sum(quantidade_processada) <> sum(COALESCE(quantidade_solicitada, 0))
        ),
        linhas AS (
            SELECT i.id,
                   g.total,
                   GREATEST(COALESCE(i.quantidade_solicitada, 0), 0) AS enviada,
                   COALESCE(sum(GREATEST(COALESCE(i.quantidade_solicitada, 0), 0)) OVER (
                       PARTITION BY i.transferencia_id, i.id_produto_erp ORDER BY i.id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                   ), 0) AS antes,
                   row_number() OVER (
                       PARTITION BY i.transferencia_id, i.id_produto_erp ORDER BY i.id DESC
                   ) = 1 AS ultima
              FROM transferencias_itens i
              JOIN grupos g USING (transferencia_id, id_produto_erp)
        ),
        partes AS (
            SELECT id,
                   ultima,
                   enviada,
                   CASE WHEN total < 0 THEN total ELSE GREATEST(total - antes, 0) END AS resto
              FROM linhas
        )
        UPDATE transferencias_itens t
           SET quantidade_processada = CASE
                   WHEN p.ultima THEN p.resto
                   ELSE GREATEST(LEAST(p.enviada, p.resto), 0)
               END
          FROM partes p
         WHERE t.id = p.id
        """
    )


def downgrade() -> None:

    pass
