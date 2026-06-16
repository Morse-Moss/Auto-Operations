"""add analysis reports table

Revision ID: 9f4c2b7e1a0d
Revises: 7b2d4a9c1f03
Create Date: 2026-06-16 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9f4c2b7e1a0d'
down_revision: Union[str, None] = '7b2d4a9c1f03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analysis_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('report_type', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('input_config', sa.JSON(), nullable=True),
        sa.Column('data_health', sa.JSON(), nullable=True),
        sa.Column('evidence_pool', sa.JSON(), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('html_file_path', sa.Text(), nullable=False),
        sa.Column('source_task_id', sa.Integer(), nullable=True),
        sa.Column('rerun_from_report_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('analysis_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_analysis_reports_platform'), ['platform'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_reports_report_type'), ['report_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_reports_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_reports_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('analysis_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_analysis_reports_user_id'))
        batch_op.drop_index(batch_op.f('ix_analysis_reports_status'))
        batch_op.drop_index(batch_op.f('ix_analysis_reports_report_type'))
        batch_op.drop_index(batch_op.f('ix_analysis_reports_platform'))
    op.drop_table('analysis_reports')
