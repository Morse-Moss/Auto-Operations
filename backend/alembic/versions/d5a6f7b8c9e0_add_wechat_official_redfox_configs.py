"""add wechat official redfox configs

Revision ID: d5a6f7b8c9e0
Revises: c4e1a2b3d5f6
Create Date: 2026-06-17 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5a6f7b8c9e0'
down_revision: Union[str, None] = 'c4e1a2b3d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wechat_official_redfox_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('encrypted_api_key', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_redfox_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_redfox_configs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_redfox_configs_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wechat_official_redfox_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_redfox_configs_user_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_redfox_configs_status'))
    op.drop_table('wechat_official_redfox_configs')
