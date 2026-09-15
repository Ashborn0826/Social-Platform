"""initial posts table

Revision ID: 0002_initial_posts
Revises: 0001_initial_users
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0002_initial_posts"
down_revision = "0001_initial_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "posts_author_created_idx", "posts", ["author_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("posts_author_created_idx", table_name="posts")
    op.drop_table("posts")