"""pgvector extension + embedding columns on note_chunks (retrieval, Phase 2).

Revision ID: 0003_chunk_embeddings
Revises: 0002_note_chunks

No ANN index on purpose: per-user corpora are hundreds of chunks and an exact
scan filtered by owner_id is both faster and exact at that size. DECISIONS.md
records the measured crossover. Dimension is fixed at 768 (Matryoshka
truncation of gemini-embedding-001); changing it means a new column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.rag.vector_type import Vector

revision: str = '0003_chunk_embeddings'
down_revision: Union[str, None] = '0002_note_chunks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMS = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column('note_chunks', sa.Column('embedding', Vector(EMBEDDING_DIMS), nullable=True))
    op.add_column('note_chunks', sa.Column('embedding_model', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('note_chunks', 'embedding_model')
    op.drop_column('note_chunks', 'embedding')
    # The extension is left installed; dropping it would fail if anything else used it.
