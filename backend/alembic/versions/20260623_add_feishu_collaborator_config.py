"""add feishu collaborator config

Revision ID: 20260623_feishu_collab
Revises: 20260623_merge_draft_feishu
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260623_feishu_collab"
down_revision: Union[str, Sequence[str], None] = "20260623_merge_draft_feishu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("feishu_integration_configs", sa.Column("collaborator_member_type", sa.String(length=32), nullable=False, server_default=""))
    op.add_column("feishu_integration_configs", sa.Column("collaborator_member_id", sa.String(length=256), nullable=False, server_default=""))
    op.add_column("feishu_integration_configs", sa.Column("collaborator_perm", sa.String(length=32), nullable=False, server_default="edit"))


def downgrade() -> None:
    op.drop_column("feishu_integration_configs", "collaborator_perm")
    op.drop_column("feishu_integration_configs", "collaborator_member_id")
    op.drop_column("feishu_integration_configs", "collaborator_member_type")
