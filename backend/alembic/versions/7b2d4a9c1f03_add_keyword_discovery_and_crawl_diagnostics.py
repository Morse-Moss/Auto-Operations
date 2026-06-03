"""add keyword discovery and crawl diagnostics

Revision ID: 7b2d4a9c1f03
Revises: 60cd5c95fde1
Create Date: 2026-06-03 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7b2d4a9c1f03'
down_revision: Union[str, None] = '60cd5c95fde1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'keyword_discovery_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('seed_keywords', sa.JSON(), nullable=True),
        sa.Column('limit_per_seed', sa.Integer(), nullable=False),
        sa.Column('source_mode', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('keyword_discovery_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_keyword_discovery_runs_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_keyword_discovery_runs_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_keyword_discovery_runs_user_id'), ['user_id'], unique=False)

    op.create_table(
        'keyword_discovery_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_keyword', sa.String(length=128), nullable=False),
        sa.Column('keyword', sa.String(length=128), nullable=False),
        sa.Column('hot_value_text', sa.String(length=64), nullable=True),
        sa.Column('hot_value_number', sa.Integer(), nullable=True),
        sa.Column('note_count', sa.Integer(), nullable=True),
        sa.Column('interaction_text', sa.String(length=64), nullable=True),
        sa.Column('interaction_number', sa.Integer(), nullable=True),
        sa.Column('categories', sa.JSON(), nullable=True),
        sa.Column('rank_index', sa.Integer(), nullable=False),
        sa.Column('selected', sa.Boolean(), nullable=False),
        sa.Column('imported_group_id', sa.Integer(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['imported_group_id'], ['keyword_groups.id']),
        sa.ForeignKeyConstraint(['run_id'], ['keyword_discovery_runs.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('keyword_discovery_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_keyword_discovery_items_keyword'), ['keyword'], unique=False)
        batch_op.create_index(batch_op.f('ix_keyword_discovery_items_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_keyword_discovery_items_run_id'), ['run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_keyword_discovery_items_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_keyword_discovery_items_user_id'), ['user_id'], unique=False)

    op.create_table(
        'crawl_diagnostics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('platform_account_id', sa.Integer(), nullable=True),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('note_id', sa.String(length=128), nullable=True),
        sa.Column('note_url', sa.Text(), nullable=True),
        sa.Column('stage', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('recoverable', sa.Boolean(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['platform_account_id'], ['platform_accounts.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('crawl_diagnostics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_note_id'), ['note_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_platform_account_id'), ['platform_account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_stage'), ['stage'], unique=False)
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_crawl_diagnostics_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('crawl_diagnostics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_user_id'))
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_task_id'))
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_stage'))
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_platform_account_id'))
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_platform'))
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_note_id'))
        batch_op.drop_index(batch_op.f('ix_crawl_diagnostics_kind'))
    op.drop_table('crawl_diagnostics')

    with op.batch_alter_table('keyword_discovery_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_items_user_id'))
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_items_source'))
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_items_run_id'))
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_items_platform'))
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_items_keyword'))
    op.drop_table('keyword_discovery_items')

    with op.batch_alter_table('keyword_discovery_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_runs_user_id'))
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_runs_source'))
        batch_op.drop_index(batch_op.f('ix_keyword_discovery_runs_platform'))
    op.drop_table('keyword_discovery_runs')
