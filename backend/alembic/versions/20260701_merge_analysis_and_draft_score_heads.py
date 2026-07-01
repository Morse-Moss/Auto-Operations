"""merge analysis score and draft score heads

Revision ID: 20260701_merge_analysis_draft_score_heads
Revises: 20260625_analysis_score_rating, 20260630_draft_ai_score_results
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "20260701_merge_analysis_draft_score_heads"
down_revision: Union[str, Sequence[str], None] = (
    "20260625_analysis_score_rating",
    "20260630_draft_ai_score_results",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
