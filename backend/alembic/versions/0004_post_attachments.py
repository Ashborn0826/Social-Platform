"""post_attachments join table

Revision ID: 0004_post_attachments
Revises: 0003_attachments
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0004_post_attachments"
down_revision = "0003_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_attachments",
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("attachment_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"], ["attachments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("post_id", "attachment_id"),
    )


def downgrade() -> None:
    op.drop_table("post_attachments")