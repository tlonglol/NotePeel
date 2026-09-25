"""Turn a note into note_chunks rows. Idempotent and safe to call from the
upload path.

* `ingest_note` recomputes chunks only when the note's index_hash changes
  (title, extracted text, or chunker config). Unchanged notes are skipped.
* Rows for a note are replaced wholesale inside one transaction: bulk DELETE,
  flush, INSERT. Replacing rather than diffing keeps ordinals dense and the
  (note_id, ordinal) unique constraint honest. Per-chunk content_hash lets
  Phase 2 carry embeddings over for chunks whose text did not change.
* `safe_ingest` is the upload-path wrapper: it never raises. Indexing failing
  must not fail an upload, the same rule auto-categorize follows.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Literal, Optional

from sqlalchemy.orm import Session

from app.models.chunk import NoteChunk
from app.models.note import Note
from app.rag.chunker import ChunkConfig, DEFAULT_CONFIG, build_context, chunk_note, note_content_hash

log = logging.getLogger("notepeel.rag.ingest")


@dataclass
class IngestResult:
    note_id: int
    status: Literal["indexed", "skipped", "empty", "failed"]
    chunks: int = 0
    reused_embeddings: int = 0
    elapsed_ms: float = 0.0
    error: Optional[str] = None


def ingest_note(
    db: Session,
    note: Note,
    cfg: ChunkConfig = DEFAULT_CONFIG,
    force: bool = False,
    commit: bool = True,
) -> IngestResult:
    t0 = time.perf_counter()
    new_hash = note_content_hash(note.title, note.structured_text, note.raw_text, cfg)

    existing: List[NoteChunk] = list(note.chunks)
    if not force and note.index_hash == new_hash and existing:
        return IngestResult(note.id, "skipped", chunks=len(existing),
                            elapsed_ms=(time.perf_counter() - t0) * 1000)

    chunks = chunk_note(note.structured_text, note.raw_text, cfg)

    # Embedding reuse map (Phase 2 fills `embedding`; today it just proves the
    # plumbing). Keyed by content_hash so an edit to one paragraph re-embeds
    # only that paragraph's chunk.
    reusable: Dict[str, NoteChunk] = {c.content_hash: c for c in existing}
    reused = sum(1 for c in chunks if c.content_hash in reusable)

    db.query(NoteChunk).filter(NoteChunk.note_id == note.id).delete(synchronize_session=False)
    db.flush()

    for c in chunks:
        db.add(NoteChunk(
            note_id=note.id,
            owner_id=note.owner_id,
            ordinal=c.ordinal,
            page=c.page,
            heading=c.heading,
            context=build_context(note.title, c.heading),
            text=c.text,
            token_estimate=c.token_estimate,
            content_hash=c.content_hash,
        ))

    note.index_hash = new_hash if chunks else None
    note.indexed_at = datetime.utcnow()
    db.flush()
    db.expire(note, ["chunks"])
    if commit:
        db.commit()

    status: Literal["indexed", "empty"] = "indexed" if chunks else "empty"
    return IngestResult(note.id, status, chunks=len(chunks), reused_embeddings=reused,
                        elapsed_ms=(time.perf_counter() - t0) * 1000)


def safe_ingest(db: Session, note: Note, cfg: ChunkConfig = DEFAULT_CONFIG) -> Optional[IngestResult]:
    """Upload-path wrapper. Never raises; rolls back its own partial work."""
    try:
        result = ingest_note(db, note, cfg=cfg)
        log.info("rag.ingest note=%s status=%s chunks=%s ms=%.1f",
                 note.id, result.status, result.chunks, result.elapsed_ms)
        return result
    except Exception as exc:  # noqa: BLE001  deliberate: indexing must never break an upload
        db.rollback()
        log.warning("rag.ingest failed note=%s err=%s", getattr(note, "id", None), exc)
        return IngestResult(getattr(note, "id", -1), "failed", error=str(exc))


def reindex_user(
    db: Session,
    owner_id: int,
    cfg: ChunkConfig = DEFAULT_CONFIG,
    force: bool = False,
) -> List[IngestResult]:
    """Backfill / re-chunk every note a user owns. Used by scripts and the eval harness."""
    results: List[IngestResult] = []
    notes = db.query(Note).filter(Note.owner_id == owner_id).order_by(Note.id).all()
    for n in notes:
        results.append(ingest_note(db, n, cfg=cfg, force=force, commit=False))
    db.commit()
    return results
