"""chat_participants join table

Revision ID: 0008_chat_participants
Revises: 0007_chats
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0008_chat_participants"
down_revision = "0007_chats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_participants",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["chats.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "user_id"),
    )
    op.create_index(
        "chat_participants_user_idx", "chat_participants", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("chat_participants_user_idx", table_name="chat_participants")
    op.drop_table("chat_participants")