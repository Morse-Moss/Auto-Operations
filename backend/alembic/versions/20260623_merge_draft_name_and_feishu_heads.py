"""merge draft name and feishu analysis loop heads

Revision ID: 20260623_merge_draft_feishu
Revises: 20260622draftname, 20260622_feishu_loop
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "20260623_merge_draft_feishu"
down_revision: Union[str, Sequence[str], None] = ("20260622draftname", "20260622_feishu_loop")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
