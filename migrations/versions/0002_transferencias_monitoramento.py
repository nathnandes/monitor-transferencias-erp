from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps(com_updated_at: bool = True) -> list[sa.Column]:
    colunas = [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )
    ]
    if com_updated_at:
        colunas.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
        )
    return colunas


def _jsonb(nome: str) -> sa.Column:
    return sa.Column(
        nome,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:

    op.drop_index("ix_empresas_id_erp", table_name="empresas")
    op.create_unique_constraint("uq_empresas_id_erp_ambiente", "empresas", ["id_erp", "ambiente"])

    op.create_table(
        "transferencias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("id_erp", sa.String(length=50), nullable=False),
        sa.Column("empresa_origem_id", sa.Integer(), nullable=False),
        sa.Column("empresa_destino_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("data_criacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_processamento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantidade_itens", sa.Integer(), nullable=True),
        sa.Column("hash_payload", sa.String(length=64), nullable=True),
        _jsonb("raw_data"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["empresa_origem_id"], ["empresas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["empresa_destino_id"], ["empresas.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("empresa_origem_id", "id_erp", name="uq_transferencias_origem_id_erp"),
        sa.CheckConstraint(
            "quantidade_itens IS NULL OR quantidade_itens >= 0",
            name="ck_transferencias_quantidade_itens",
        ),
    )
    op.create_index("ix_transferencias_id_erp", "transferencias", ["id_erp"])
    op.create_index(
        "ix_transferencias_empresa_destino_id", "transferencias", ["empresa_destino_id"]
    )
    op.create_index(
        "ix_transferencias_status_data_criacao",
        "transferencias",
        ["status", "data_criacao"],
    )
    op.create_index("ix_transferencias_data_criacao", "transferencias", ["data_criacao"])
    op.create_index(
        "ix_transferencias_data_processamento", "transferencias", ["data_processamento"]
    )

    op.create_table(
        "transferencias_itens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transferencia_id", sa.Integer(), nullable=False),
        sa.Column("id_produto_erp", sa.String(length=50), nullable=False),
        sa.Column("codigo_produto", sa.String(length=50), nullable=True),
        sa.Column("descricao_produto", sa.String(length=300), nullable=True),
        sa.Column("quantidade_solicitada", sa.Numeric(18, 4), nullable=True),
        sa.Column("quantidade_processada", sa.Numeric(18, 4), nullable=True),
        _jsonb("raw_data"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["transferencia_id"], ["transferencias.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_transferencias_itens_transferencia_id",
        "transferencias_itens",
        ["transferencia_id"],
    )
    op.create_index(
        "ix_transferencias_itens_id_produto_erp",
        "transferencias_itens",
        ["id_produto_erp"],
    )

    op.create_table(
        "sincronizacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column(
            "inicio",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="em_andamento", nullable=False),
        sa.Column("registros_consultados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("registros_criados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("registros_atualizados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("registros_ignorados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mensagem_erro", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('em_andamento', 'sucesso', 'parcial', 'erro')",
            name="ck_sincronizacoes_status",
        ),
        sa.CheckConstraint(
            "registros_consultados >= 0 AND registros_criados >= 0"
            " AND registros_atualizados >= 0 AND registros_ignorados >= 0",
            name="ck_sincronizacoes_contadores",
        ),
        sa.CheckConstraint("fim IS NULL OR fim >= inicio", name="ck_sincronizacoes_periodo"),
    )
    op.create_index("ix_sincronizacoes_empresa_id", "sincronizacoes", ["empresa_id"])
    op.create_index("ix_sincronizacoes_status", "sincronizacoes", ["status"])
    op.create_index("ix_sincronizacoes_tipo_inicio", "sincronizacoes", ["tipo", "inicio"])

    op.create_table(
        "eventos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=True),
        sa.Column("transferencia_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column("origem", sa.String(length=50), nullable=False),
        sa.Column("severidade", sa.String(length=10), nullable=False),
        sa.Column("referencia_externa", sa.String(length=100), nullable=True),
        _jsonb("payload"),
        sa.Column(
            "data_evento",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_timestamps(com_updated_at=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transferencia_id"], ["transferencias.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "severidade IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')",
            name="ck_eventos_severidade",
        ),
    )
    op.create_index("ix_eventos_empresa_id", "eventos", ["empresa_id"])
    op.create_index("ix_eventos_transferencia_id", "eventos", ["transferencia_id"])
    op.create_index("ix_eventos_tipo", "eventos", ["tipo"])
    op.create_index("ix_eventos_severidade", "eventos", ["severidade"])
    op.create_index("ix_eventos_referencia_externa", "eventos", ["referencia_externa"])
    op.create_index("ix_eventos_data_evento", "eventos", ["data_evento"])

    op.create_table(
        "logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nivel", sa.String(length=10), nullable=False),
        sa.Column("modulo", sa.String(length=100), nullable=False),
        sa.Column("evento", sa.String(length=100), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        _jsonb("payload"),
        sa.Column(
            "data",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_timestamps(com_updated_at=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "nivel IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')",
            name="ck_logs_nivel",
        ),
    )
    op.create_index("ix_logs_nivel", "logs", ["nivel"])
    op.create_index("ix_logs_modulo", "logs", ["modulo"])
    op.create_index("ix_logs_data", "logs", ["data"])


def downgrade() -> None:

    op.drop_table("logs")
    op.drop_table("eventos")
    op.drop_table("sincronizacoes")
    op.drop_table("transferencias_itens")
    op.drop_table("transferencias")

    op.drop_constraint("uq_empresas_id_erp_ambiente", "empresas", type_="unique")
    op.create_index("ix_empresas_id_erp", "empresas", ["id_erp"], unique=False)
