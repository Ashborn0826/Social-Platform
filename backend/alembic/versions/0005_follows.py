"""follows table

Revision ID: 0005_follows
Revises: 0004_post_attachments
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0005_follows"
down_revision = "0004_post_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follows",
        sa.Column("follower_id", sa.BigInteger(), nullable=False),
        sa.Column("followee_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["follower_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["followee_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("follower_id", "followee_id"),
    )
    op.create_index("follows_followee_idx", "follows", ["followee_id"])


def downgrade() -> None:
    op.drop_index("follows_followee_idx", table_name="follows")
    op.drop_table("follows")