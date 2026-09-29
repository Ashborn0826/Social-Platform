"""messages table

Revision ID: 0009_messages
Revises: 0008_chat_participants
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0009_messages"
down_revision = "0008_chat_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("messages_chat_idx", "messages", ["chat_id", "created_at"])


def downgrade() -> None:
    op.drop_index("messages_chat_idx", table_name="messages")
    op.drop_table("messages")