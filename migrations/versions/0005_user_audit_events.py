from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("origem", sa.String(length=10), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=50), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_username", sa.String(length=50), nullable=False),
        sa.Column(
            "detalhes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "event_type IN ('USUARIO_CRIADO', 'USUARIO_EDITADO', 'USUARIO_ATIVADO', "
            "'USUARIO_DESATIVADO', 'SENHA_REDEFINIDA', 'ROLE_ALTERADA', "
            "'PERMISSOES_ALTERADAS')",
            name="ck_user_audit_events_event_type",
        ),
        sa.CheckConstraint("origem IN ('API', 'CLI')", name="ck_user_audit_events_origem"),
    )
    op.create_index(
        "ix_user_audit_events_event_type", "user_audit_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_user_audit_events_actor_user_id", "user_audit_events", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_user_audit_events_target_created",
        "user_audit_events",
        ["target_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("user_audit_events")
