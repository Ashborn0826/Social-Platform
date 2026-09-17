"""attachments table

Revision ID: 0003_attachments
Revises: 0002_initial_posts
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0003_attachments"
down_revision = "0002_initial_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("thumbnail_key", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("attachments_owner_idx", "attachments", ["owner_id"])


def downgrade() -> None:
    op.drop_index("attachments_owner_idx", table_name="attachments")
    op.drop_table("attachments")