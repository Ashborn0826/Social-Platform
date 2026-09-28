"""timeline_entries table

Revision ID: 0006_timeline_entries
Revises: 0005_follows
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0006_timeline_entries"
down_revision = "0005_follows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeline_entries",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "post_id"),
    )
    op.create_index(
        "timeline_user_idx", "timeline_entries", ["user_id", "inserted_at"]
    )


def downgrade() -> None:
    op.drop_index("timeline_user_idx", table_name="timeline_entries")
    op.drop_table("timeline_entries")