"""add wechat official content library tombstones

Revision ID: 20260618woclt
Revises: e6b7c8d9f0a1
Create Date: 2026-06-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260618woclt"
down_revision: Union[str, Sequence[str], None] = "e6b7c8d9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wechat_official_content_library_tombstones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("article_url", sa.String(length=512), nullable=False),
        sa.Column("article_title", sa.String(length=512), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "article_url", name="uq_wechat_official_content_library_tombstones_user_url"),
    )
    op.create_index(op.f("ix_wechat_official_content_library_tombstones_user_id"), "wechat_official_content_library_tombstones", ["user_id"], unique=False)
    op.create_index(op.f("ix_wechat_official_content_library_tombstones_article_url"), "wechat_official_content_library_tombstones", ["article_url"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_wechat_official_content_library_tombstones_article_url"), table_name="wechat_official_content_library_tombstones")
    op.drop_index(op.f("ix_wechat_official_content_library_tombstones_user_id"), table_name="wechat_official_content_library_tombstones")
    op.drop_table("wechat_official_content_library_tombstones")
