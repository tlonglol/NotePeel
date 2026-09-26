"""Turn a note into note_chunks rows. Idempotent and safe to call from the
upload path.

* `ingest_note` recomputes chunks only when the note's index_hash changes
  (title, extracted text, or chunker config). Unchanged notes are skipped.
* Rows for a note are replaced wholesale inside one transaction: bulk DELETE,
  flush, INSERT. Replacing rather than diffing keeps ordinals dense and the
  (note_id, ordinal) unique constraint honest.
* Embeddings are reused by content_hash: an edit to one paragraph re-embeds
  only that paragraph's chunk. Everything else is copied from the old rows.
* If the embedding API fails, chunks are still written (lexical search keeps
  working), the note is left un-hashed so the next ingest retries, and the
  result says "partial".
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

from app.config import get_settings
from app.models.chunk import NoteChunk
from app.models.note import Note
from app.rag.chunker import ChunkConfig, DEFAULT_CONFIG, build_context, chunk_note, note_content_hash
from app.rag.embeddings import EmbeddingError, embed_documents, embedding_available, model_tag

log = logging.getLogger("notepeel.rag.ingest")

Status = Literal["indexed", "partial", "skipped", "empty", "failed"]


@dataclass
class IngestResult:
    note_id: int
    status: Status
    chunks: int = 0
    embedded: int = 0             # chunks that needed a fresh embedding call
    reused_embeddings: int = 0    # chunks whose embedding was copied by content_hash
    elapsed_ms: float = 0.0
    embedding_ms: float = 0.0
    error: Optional[str] = None


def embedding_input(context: str, text: str) -> str:
    """What gets embedded: the breadcrumb then the chunk. Mirrors the tsvector."""
    return f"{context}\n{text}" if context else text


def _should_embed(embed: Optional[bool]) -> bool:
    if embed is not None:
        return embed
    return get_settings().rag_embed_on_ingest and embedding_available()


def ingest_note(
    db: Session,
    note: Note,
    cfg: ChunkConfig = DEFAULT_CONFIG,
    force: bool = False,
    commit: bool = True,
    embed: Optional[bool] = None,
) -> IngestResult:
    t0 = time.perf_counter()
    want_embed = _should_embed(embed)
    tag = model_tag()
    new_hash = note_content_hash(note.title, note.structured_text, note.raw_text, cfg)

    existing: List[NoteChunk] = list(note.chunks)
    if not force and note.index_hash == new_hash and existing:
        missing = want_embed and any(c.embedding is None or c.embedding_model != tag for c in existing)
        if not missing:
            return IngestResult(note.id, "skipped", chunks=len(existing),
                                elapsed_ms=(time.perf_counter() - t0) * 1000)

    chunks = chunk_note(note.structured_text, note.raw_text, cfg)

    reusable: Dict[str, NoteChunk] = {
        c.content_hash: c for c in existing
        if c.embedding is not None and c.embedding_model == tag
    }

    rows: List[NoteChunk] = []
    for c in chunks:
        ctx = build_context(note.title, c.heading)
        row = NoteChunk(
            note_id=note.id, owner_id=note.owner_id, ordinal=c.ordinal, page=c.page,
            heading=c.heading, context=ctx, text=c.text, token_estimate=c.token_estimate,
            content_hash=c.content_hash,
        )
        prev = reusable.get(c.content_hash)
        if prev is not None:
            row.embedding = list(prev.embedding)
            row.embedding_model = prev.embedding_model
        rows.append(row)
    reused = sum(1 for r in rows if r.embedding is not None)

    embedded = 0
    embedding_ms = 0.0
    embed_error: Optional[str] = None
    todo = [r for r in rows if r.embedding is None] if want_embed else []
    if todo:
        t1 = time.perf_counter()
        try:
            vectors = embed_documents([embedding_input(r.context, r.text) for r in todo])
            for r, v in zip(todo, vectors):
                r.embedding = v
                r.embedding_model = tag
            embedded = len(todo)
        except EmbeddingError as exc:
            embed_error = str(exc)
            log.warning("rag.ingest embeddings failed note=%s err=%s", note.id, exc)
        embedding_ms = (time.perf_counter() - t1) * 1000

    db.query(NoteChunk).filter(NoteChunk.note_id == note.id).delete(synchronize_session=False)
    db.flush()
    for r in rows:
        db.add(r)

    if not chunks:
        status: Status = "empty"
        note.index_hash = None
    elif embed_error:
        status = "partial"
        note.index_hash = None          # retry embeddings on the next ingest
    else:
        status = "indexed"
        note.index_hash = new_hash
    note.indexed_at = datetime.utcnow()
    db.flush()
    db.expire(note, ["chunks"])
    if commit:
        db.commit()

    return IngestResult(note.id, status, chunks=len(chunks), embedded=embedded,
                        reused_embeddings=reused, elapsed_ms=(time.perf_counter() - t0) * 1000,
                        embedding_ms=embedding_ms, error=embed_error)


def safe_ingest(db: Session, note: Note, cfg: ChunkConfig = DEFAULT_CONFIG) -> Optional[IngestResult]:
    """Upload-path wrapper. Never raises; rolls back its own partial work."""
    try:
        result = ingest_note(db, note, cfg=cfg)
        log.info("rag.ingest note=%s status=%s chunks=%s embedded=%s reused=%s ms=%.1f embed_ms=%.1f",
                 note.id, result.status, result.chunks, result.embedded, result.reused_embeddings,
                 result.elapsed_ms, result.embedding_ms)
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
    embed: Optional[bool] = None,
) -> List[IngestResult]:
    """Backfill / re-chunk every note a user owns. Used by scripts and the eval harness."""
    results: List[IngestResult] = []
    notes = db.query(Note).filter(Note.owner_id == owner_id).order_by(Note.id).all()
    for n in notes:
        results.append(ingest_note(db, n, cfg=cfg, force=force, commit=False, embed=embed))
    db.commit()
    return results
