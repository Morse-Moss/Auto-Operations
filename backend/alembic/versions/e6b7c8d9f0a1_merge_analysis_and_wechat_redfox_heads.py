"""merge analysis and wechat redfox heads

Revision ID: e6b7c8d9f0a1
Revises: 9f4c2b7e1a0d, d5a6f7b8c9e0
Create Date: 2026-06-17 15:30:00.000000
"""

from typing import Sequence, Union


revision: str = "e6b7c8d9f0a1"
down_revision: Union[str, Sequence[str], None] = ("9f4c2b7e1a0d", "d5a6f7b8c9e0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
