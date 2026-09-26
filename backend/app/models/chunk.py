from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    UniqueConstraint, Index, Computed,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import relationship

from app.config import get_settings
from app.database import Base
from app.rag.vector_type import Vector


class NoteChunk(Base):
    """One retrieval unit of a note.

    Produced by app.rag.chunker from the note's structured_text (the text the
    user actually sees and edits), falling back to raw_text. `context` carries
    the note title and section heading so lexical and vector search both see
    where a chunk came from. `tsv` is a Postgres generated column, so the
    lexical index can never drift from the text.
    """
    __tablename__ = "note_chunks"

    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    ordinal = Column(Integer, nullable=False)                 # 0-based position within the note
    page = Column(Integer, nullable=False, default=1, server_default="1")  # <hr>-delimited segment
    heading = Column(String(300), nullable=True)              # nearest section heading, if any
    context = Column(String(600), nullable=False, default="", server_default="")  # "title > heading"
    text = Column(Text, nullable=False)
    token_estimate = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)         # sha256(heading + text); embedding reuse key

    tsv = Column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(context, '') || ' ' || text)", persisted=True),
    )

    # Dense embedding of `context + text`. NULL until embedded; vector search
    # skips NULLs, so lexical search keeps working if the embedding API is down.
    embedding = Column(Vector(get_settings().rag_embedding_dims), nullable=True)
    embedding_model = Column(String(100), nullable=True)   # e.g. "gemini-embedding-001@768"

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("note_id", "ordinal", name="uq_note_chunks_note_ordinal"),
        Index("ix_note_chunks_owner_note", "owner_id", "note_id"),
        Index("ix_note_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    note = relationship("Note", back_populates="chunks")
