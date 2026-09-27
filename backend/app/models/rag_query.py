from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class RagQuery(Base):
    """One row per ask-your-notes request: what was asked, what was retrieved and
    cited, whether the system abstained, what the guard flagged, and how long each
    stage took. This is the observability and cost record for the feature and the
    in-region latency source for the eval tables."""
    __tablename__ = "rag_queries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notebook_id = Column(Integer, nullable=True)
    question = Column(Text, nullable=False)

    retrieval_mode = Column(String(20), nullable=False)
    retrieved_chunk_ids = Column(JSONB, nullable=False, default=list)   # ranked, before the guard
    cited_chunk_ids = Column(JSONB, nullable=False, default=list)
    guard_flagged_chunk_ids = Column(JSONB, nullable=False, default=list)
    top_score = Column(Float, nullable=True)                              # top-1 cosine / fused score
    abstained = Column(Boolean, nullable=False, default=False)
    gate_triggered = Column(Boolean, nullable=False, default=False)      # top_score below the abstain gate

    generation_model = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)

    embed_ms = Column(Float, nullable=True)
    retrieve_ms = Column(Float, nullable=True)
    generate_ms = Column(Float, nullable=True)
    total_ms = Column(Float, nullable=True)

    streamed = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
