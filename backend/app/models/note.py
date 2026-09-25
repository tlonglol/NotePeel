from sqlalchemy import Column, Integer, String, Text, LargeBinary, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)

    # REMOVED: original_image = Column(LargeBinary, nullable=False)

    # S3 blob storage
    image_key = Column(String(500), nullable=True)    # S3 object key
    image_url = Column(Text, nullable=True)           # presigned URL (refreshed on access); TEXT because IAM-role (STS) signed URLs exceed varchar(1000)

    image_filename = Column(String(255), nullable=True)
    image_mimetype = Column(String(100), nullable=True)

    # Extracted text
    raw_text = Column(Text, nullable=True)
    structured_text = Column(Text, nullable=True)
    
    # AI-generated content (cached)
    ai_summary = Column(Text, nullable=True)
    
    # Organization
    subject = Column(String(100), nullable=True)
    topic = Column(String(100), nullable=True)
    tags = Column(String(500), nullable=True)

    # Processing status
    status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    error_message = Column(Text, nullable=True)

    # Sharing
    share_token = Column(String(36), unique=True, index=True, nullable=True)

    # Retrieval index state (see app.rag.ingest). index_hash is a hash of the
    # source text + chunker config; unchanged hash => re-ingestion is skipped.
    index_hash = Column(String(64), nullable=True)
    indexed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Foreign key
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    owner = relationship("User", back_populates="notes")
    
    # Relationship to notebooks (many-to-many)
    notebooks = relationship("Notebook", secondary="note_notebooks", back_populates="notes")

    # Retrieval chunks. passive_deletes lets the DB-level ON DELETE CASCADE do the work.
    chunks = relationship(
        "NoteChunk", back_populates="note", cascade="all, delete-orphan",
        passive_deletes=True, order_by="NoteChunk.ordinal",
    )
