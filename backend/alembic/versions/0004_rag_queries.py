"""rag_queries: per-request log for ask-your-notes (retrieval, Phase 3).

Revision ID: 0004_rag_queries
Revises: 0003_chunk_embeddings
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004_rag_queries'
down_revision: Union[str, None] = '0003_chunk_embeddings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rag_queries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notebook_id', sa.Integer(), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('retrieval_mode', sa.String(length=20), nullable=False),
        sa.Column('retrieved_chunk_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('cited_chunk_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('guard_flagged_chunk_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('top_score', sa.Float(), nullable=True),
        sa.Column('abstained', sa.Boolean(), nullable=False),
        sa.Column('gate_triggered', sa.Boolean(), nullable=False),
        sa.Column('generation_model', sa.String(length=100), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
        sa.Column('embed_ms', sa.Float(), nullable=True),
        sa.Column('retrieve_ms', sa.Float(), nullable=True),
        sa.Column('generate_ms', sa.Float(), nullable=True),
        sa.Column('total_ms', sa.Float(), nullable=True),
        sa.Column('streamed', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_rag_queries_user_id'), 'rag_queries', ['user_id'], unique=False)
    op.create_index(op.f('ix_rag_queries_created_at'), 'rag_queries', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_rag_queries_created_at'), table_name='rag_queries')
    op.drop_index(op.f('ix_rag_queries_user_id'), table_name='rag_queries')
    op.drop_table('rag_queries')
