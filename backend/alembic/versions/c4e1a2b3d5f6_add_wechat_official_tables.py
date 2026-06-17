"""add wechat official tables

Revision ID: c4e1a2b3d5f6
Revises: 7b2d4a9c1f03
Create Date: 2026-06-16 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e1a2b3d5f6'
down_revision: Union[str, None] = '7b2d4a9c1f03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wechat_official_crawl_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('biz', sa.String(length=128), nullable=False),
        sa.Column('fake_id', sa.String(length=128), nullable=False),
        sa.Column('alias', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_crawl_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_accounts_biz'), ['biz'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_accounts_fake_id'), ['fake_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_accounts_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_accounts_user_id'), ['user_id'], unique=False)

    op.create_table(
        'wechat_official_proxy_nodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_proxy_nodes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_proxy_nodes_status'), ['status'], unique=False)

    op.create_table(
        'wechat_official_backend_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('encrypted_cookie', sa.Text(), nullable=False),
        sa.Column('encrypted_token', sa.Text(), nullable=False),
        sa.Column('user_agent', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['wechat_official_crawl_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_backend_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_backend_sessions_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_backend_sessions_status'), ['status'], unique=False)

    op.create_table(
        'wechat_official_article_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('article_url', sa.Text(), nullable=False),
        sa.Column('encrypted_cookie', sa.Text(), nullable=False),
        sa.Column('encrypted_token', sa.Text(), nullable=False),
        sa.Column('encrypted_key', sa.Text(), nullable=False),
        sa.Column('valid', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['wechat_official_crawl_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_article_credentials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_article_credentials_account_id'), ['account_id'], unique=False)

    op.create_table(
        'wechat_official_crawl_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('proxy_node_id', sa.Integer(), nullable=True),
        sa.Column('keyword', sa.String(length=256), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('requested_limit', sa.Integer(), nullable=False),
        sa.Column('fetched_count', sa.Integer(), nullable=False),
        sa.Column('saved_count', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('params_json', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['wechat_official_crawl_accounts.id']),
        sa.ForeignKeyConstraint(['proxy_node_id'], ['wechat_official_proxy_nodes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_crawl_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_jobs_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_jobs_proxy_node_id'), ['proxy_node_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_jobs_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_crawl_jobs_status'), ['status'], unique=False)

    op.create_table(
        'wechat_official_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('article_url', sa.Text(), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('digest', sa.Text(), nullable=False),
        sa.Column('author_name', sa.String(length=128), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('publish_time_remote', sa.String(length=64), nullable=True),
        sa.Column('cover_url', sa.Text(), nullable=False),
        sa.Column('content_url', sa.Text(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['wechat_official_crawl_accounts.id']),
        sa.ForeignKeyConstraint(['job_id'], ['wechat_official_crawl_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_articles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_articles_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_articles_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_articles_source'), ['source'], unique=False)

    op.create_table(
        'wechat_official_article_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('html', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('images_json', sa.JSON(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('captured_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['wechat_official_articles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_article_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_article_snapshots_article_id'), ['article_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_article_snapshots_status'), ['status'], unique=False)

    op.create_table(
        'wechat_official_article_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('read_count', sa.Integer(), nullable=False),
        sa.Column('like_count', sa.Integer(), nullable=False),
        sa.Column('wow_count', sa.Integer(), nullable=False),
        sa.Column('share_count', sa.Integer(), nullable=False),
        sa.Column('comment_count', sa.Integer(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('captured_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['wechat_official_articles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_article_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_article_metrics_article_id'), ['article_id'], unique=False)

    op.create_table(
        'wechat_official_article_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('comment_id', sa.String(length=128), nullable=False),
        sa.Column('user_name', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('like_count', sa.Integer(), nullable=False),
        sa.Column('created_at_remote', sa.String(length=64), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['wechat_official_articles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_article_comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_article_comments_article_id'), ['article_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_article_comments_comment_id'), ['comment_id'], unique=False)

    op.create_table(
        'wechat_official_ingest_errors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('article_id', sa.Integer(), nullable=True),
        sa.Column('stage', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['wechat_official_crawl_accounts.id']),
        sa.ForeignKeyConstraint(['article_id'], ['wechat_official_articles.id']),
        sa.ForeignKeyConstraint(['job_id'], ['wechat_official_crawl_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_ingest_errors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_ingest_errors_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_ingest_errors_article_id'), ['article_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_ingest_errors_job_id'), ['job_id'], unique=False)

    op.create_table(
        'wechat_official_article_comment_replies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('comment_id', sa.Integer(), nullable=False),
        sa.Column('reply_id', sa.String(length=128), nullable=False),
        sa.Column('user_name', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('like_count', sa.Integer(), nullable=False),
        sa.Column('created_at_remote', sa.String(length=64), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['wechat_official_article_comments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_article_comment_replies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_article_comment_replies_comment_id'), ['comment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_article_comment_replies_reply_id'), ['reply_id'], unique=False)

    op.create_table(
        'wechat_official_draft_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('draft_id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['wechat_official_articles.id']),
        sa.ForeignKeyConstraint(['draft_id'], ['ai_drafts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wechat_official_draft_sources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wechat_official_draft_sources_article_id'), ['article_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wechat_official_draft_sources_draft_id'), ['draft_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wechat_official_draft_sources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_draft_sources_draft_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_draft_sources_article_id'))
    op.drop_table('wechat_official_draft_sources')

    with op.batch_alter_table('wechat_official_article_comment_replies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_comment_replies_reply_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_comment_replies_comment_id'))
    op.drop_table('wechat_official_article_comment_replies')

    with op.batch_alter_table('wechat_official_ingest_errors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_ingest_errors_job_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_ingest_errors_article_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_ingest_errors_account_id'))
    op.drop_table('wechat_official_ingest_errors')

    with op.batch_alter_table('wechat_official_article_comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_comments_comment_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_comments_article_id'))
    op.drop_table('wechat_official_article_comments')

    with op.batch_alter_table('wechat_official_article_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_metrics_article_id'))
    op.drop_table('wechat_official_article_metrics')

    with op.batch_alter_table('wechat_official_article_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_snapshots_status'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_snapshots_article_id'))
    op.drop_table('wechat_official_article_snapshots')

    with op.batch_alter_table('wechat_official_articles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_articles_source'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_articles_job_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_articles_account_id'))
    op.drop_table('wechat_official_articles')

    with op.batch_alter_table('wechat_official_crawl_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_jobs_status'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_jobs_source'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_jobs_proxy_node_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_jobs_account_id'))
    op.drop_table('wechat_official_crawl_jobs')

    with op.batch_alter_table('wechat_official_article_credentials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_article_credentials_account_id'))
    op.drop_table('wechat_official_article_credentials')

    with op.batch_alter_table('wechat_official_backend_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_backend_sessions_status'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_backend_sessions_account_id'))
    op.drop_table('wechat_official_backend_sessions')

    with op.batch_alter_table('wechat_official_proxy_nodes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_proxy_nodes_status'))
    op.drop_table('wechat_official_proxy_nodes')

    with op.batch_alter_table('wechat_official_crawl_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_accounts_user_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_accounts_status'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_accounts_fake_id'))
        batch_op.drop_index(batch_op.f('ix_wechat_official_crawl_accounts_biz'))
    op.drop_table('wechat_official_crawl_accounts')
