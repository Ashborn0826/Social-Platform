"""chats table

Revision ID: 0007_chats
Revises: 0006_timeline_entries
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0007_chats"
down_revision = "0006_timeline_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("chats")