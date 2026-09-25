"""note_chunks table + note index state (retrieval, Phase 1).

Revision ID: 0002_note_chunks
Revises: 0001_baseline
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002_note_chunks'
down_revision: Union[str, None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notes', sa.Column('index_hash', sa.String(length=64), nullable=True))
    op.add_column('notes', sa.Column('indexed_at', sa.DateTime(), nullable=True))
    op.create_table(
        'note_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('note_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('page', sa.Integer(), server_default='1', nullable=False),
        sa.Column('heading', sa.String(length=300), nullable=True),
        sa.Column('context', sa.String(length=600), server_default='', nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('token_estimate', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'tsv', postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(context, '') || ' ' || text)", persisted=True),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('note_id', 'ordinal', name='uq_note_chunks_note_ordinal'),
    )
    op.create_index('ix_note_chunks_owner_note', 'note_chunks', ['owner_id', 'note_id'], unique=False)
    op.create_index('ix_note_chunks_tsv', 'note_chunks', ['tsv'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('ix_note_chunks_tsv', table_name='note_chunks', postgresql_using='gin')
    op.drop_index('ix_note_chunks_owner_note', table_name='note_chunks')
    op.drop_table('note_chunks')
    op.drop_column('notes', 'indexed_at')
    op.drop_column('notes', 'index_hash')
