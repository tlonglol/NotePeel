"""Ask-your-notes orchestration: retrieve -> guard -> generate -> log.

`ask` returns a complete answer; `ask_stream` yields server-sent events
("sources" as soon as retrieval finishes, then "token" deltas, then "done").
Both write one rag_queries row. Logging never raises into the request.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterator, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.note import Note
from app.models.rag_query import RagQuery
from app.rag.embeddings import embed_query
from app.rag.generate import (
    ABSTAIN_TEXT, GenerationError, Source, citations_from_text, generate_with_fallback,
    stream_answer_with_fallback,
)
from app.rag.guard import filter_chunks
from app.rag.retrieval import RetrievedChunk, fts_search, hybrid_search, vector_search

log = logging.getLogger("notepeel.rag.ask")
STREAM_ABSTAIN_SENTINEL = "NOT_IN_NOTES"


@dataclass
class Citation:
    n: int
    chunk_id: int
    note_id: int
    note_title: str
    page: int
    heading: Optional[str]
    snippet: str


@dataclass
class AskResult:
    question: str
    answer: str
    abstained: bool
    gate_triggered: bool
    citations: List[Citation]            # sources the answer cites
    sources: List[Citation]              # every source shown to the model
    retrieval_mode: str
    top_score: Optional[float]
    guard_flagged_chunk_ids: List[int]
    model: Optional[str]
    timings_ms: Dict[str, float] = field(default_factory=dict)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    query_id: Optional[int] = None
    error: Optional[str] = None          # set when generation failed; abstained is then True

    def to_dict(self) -> dict:
        return asdict(self)


# ── retrieval ───────────────────────────────────────────────────────────────

def retrieve(db: Session, user_id: int, question: str, notebook_id: Optional[int],
             mode: Optional[str], timings: Dict[str, float]) -> tuple[List[RetrievedChunk], Optional[float], str]:
    """Returns (ranked chunks, top-1 cosine score or None, mode used). The cosine
    score is what the abstain gate reads; in hybrid mode it comes from the vector
    component, in fts mode there is none."""
    s = get_settings()
    mode = mode or s.rag_retrieval_mode
    k = s.rag_candidates
    if mode == "vector":
        t = time.perf_counter()
        qvec = embed_query(question)
        timings["embed_ms"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        chunks = vector_search(db, user_id, qvec, k=k, notebook_id=notebook_id)
        timings["retrieve_ms"] = (time.perf_counter() - t) * 1000
        if not chunks and _has_unembedded_chunks(db, user_id, notebook_id):
            # The user's notes are indexed lexically but their embeddings are missing
            # (embedding API failure during ingest; see DECISIONS D22). Answering from
            # lexical search beats telling them their notes contain nothing.
            log.warning("rag.retrieve vector empty but chunks exist; falling back to fts user=%s", user_id)
            t = time.perf_counter()
            chunks = fts_search(db, user_id, question, k=k, notebook_id=notebook_id)
            timings["retrieve_ms"] += (time.perf_counter() - t) * 1000
            return chunks, None, "vector_fts_fallback"
        return chunks, (chunks[0].score if chunks else None), mode
    if mode == "hybrid":
        lists: Dict[str, List[RetrievedChunk]] = {}
        stage: Dict[str, float] = {}
        chunks = hybrid_search(db, user_id, question, k=k, candidates=k, rrf_k=s.rag_rrf_k,
                               notebook_id=notebook_id, fts_weight=s.rag_hybrid_fts_weight,
                               timings=stage, lists_out=lists)
        timings["embed_ms"] = stage.get("embed_ms", 0.0)
        timings["retrieve_ms"] = stage.get("fts_ms", 0.0) + stage.get("vector_ms", 0.0) + stage.get("fuse_ms", 0.0)
        vec = lists.get("vector") or []
        return chunks, (vec[0].score if vec else None), mode
    if mode == "fts":
        t = time.perf_counter()
        chunks = fts_search(db, user_id, question, k=k, notebook_id=notebook_id)
        timings["retrieve_ms"] = (time.perf_counter() - t) * 1000
        return chunks, None, mode
    raise ValueError(f"unknown retrieval mode {mode!r}")


def _has_unembedded_chunks(db: Session, user_id: int, notebook_id: Optional[int]) -> bool:
    """True when the user owns chunks that vector search cannot see (NULL embedding)."""
    from app.models.chunk import NoteChunk
    q = db.query(NoteChunk.id).filter(NoteChunk.owner_id == user_id, NoteChunk.embedding.is_(None))
    if notebook_id is not None:
        from app.models.notebook import note_notebooks
        q = q.filter(NoteChunk.note_id.in_(
            db.query(note_notebooks.c.note_id).filter(note_notebooks.c.notebook_id == notebook_id)))
    return db.query(q.exists()).scalar()


def _titles(db: Session, note_ids: List[int]) -> Dict[int, str]:
    if not note_ids:
        return {}
    rows = db.query(Note.id, Note.title).filter(Note.id.in_(set(note_ids))).all()
    return {i: (t or "Untitled") for i, t in rows}


def build_sources(db: Session, chunks: List[RetrievedChunk]) -> tuple[List[Source], List[Citation]]:
    titles = _titles(db, [c.note_id for c in chunks])
    sources, cites = [], []
    for i, c in enumerate(chunks, 1):
        title = titles.get(c.note_id, "Untitled")
        sources.append(Source(n=i, chunk_id=c.chunk_id, note_id=c.note_id, title=title, text=c.text))
        cites.append(Citation(n=i, chunk_id=c.chunk_id, note_id=c.note_id, note_title=title,
                              page=c.page, heading=c.heading, snippet=c.text[:300]))
    return sources, cites


def prepare(db: Session, user_id: int, question: str, notebook_id: Optional[int], mode: Optional[str]):
    """Shared first half of ask / ask_stream."""
    s = get_settings()
    timings: Dict[str, float] = {}
    ranked, top_score, mode_used = retrieve(db, user_id, question, notebook_id, mode, timings)
    kept, flagged = filter_chunks(ranked, keep=s.rag_context_chunks)
    if flagged:
        log.warning("rag.guard flagged chunks=%s user=%s", flagged, user_id)
    sources, cites = build_sources(db, kept)
    gate = top_score is not None and top_score < s.rag_abstain_threshold
    return ranked, kept, flagged, sources, cites, top_score, mode_used, gate, timings


def _log(db: Session, user_id: int, question: str, notebook_id: Optional[int], result: AskResult,
         ranked: List[RetrievedChunk], streamed: bool, error: Optional[str] = None) -> Optional[int]:
    try:
        row = RagQuery(
            user_id=user_id, notebook_id=notebook_id, question=question,
            retrieval_mode=result.retrieval_mode,
            retrieved_chunk_ids=[c.chunk_id for c in ranked],
            cited_chunk_ids=[c.chunk_id for c in result.citations],
            guard_flagged_chunk_ids=list(result.guard_flagged_chunk_ids),
            top_score=result.top_score, abstained=result.abstained, gate_triggered=result.gate_triggered,
            generation_model=result.model, prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens, estimated_cost_usd=result.estimated_cost_usd,
            embed_ms=result.timings_ms.get("embed_ms"), retrieve_ms=result.timings_ms.get("retrieve_ms"),
            generate_ms=result.timings_ms.get("generate_ms"), total_ms=result.timings_ms.get("total_ms"),
            streamed=streamed, error=error,
        )
        db.add(row)
        db.commit()
        return row.id
    except Exception as exc:  # noqa: BLE001  logging must never break an answer
        db.rollback()
        log.warning("rag.query_log failed: %s", exc)
        return None


# ── non-streaming ───────────────────────────────────────────────────────────

def ask(db: Session, user_id: int, question: str, notebook_id: Optional[int] = None,
        mode: Optional[str] = None, model: Optional[str] = None, write_log: bool = True) -> AskResult:
    t_all = time.perf_counter()
    question = (question or "").strip()
    ranked, kept, flagged, sources, cites, top_score, mode_used, gate, timings = prepare(
        db, user_id, question, notebook_id, mode)

    result = AskResult(
        question=question, answer=ABSTAIN_TEXT, abstained=True, gate_triggered=gate,
        citations=[], sources=cites, retrieval_mode=mode_used, top_score=top_score,
        guard_flagged_chunk_ids=flagged, model=None, timings_ms=timings,
    )
    error = None
    if sources:
        try:
            gen = generate_with_fallback(question, sources, weak_evidence=gate, model=model)
            by_n = {c.n: c for c in cites}
            result.answer = gen.answer
            result.abstained = gen.abstain
            result.citations = [by_n[n] for n in gen.cited if n in by_n]
            result.model = gen.model
            result.prompt_tokens = gen.prompt_tokens
            result.completion_tokens = gen.completion_tokens
            result.estimated_cost_usd = gen.estimated_cost_usd
            timings["generate_ms"] = gen.generate_ms
            if gen.fallback_from:
                log.warning("rag.ask served by fallback %s (primary %s failed: %s) user=%s",
                            gen.model, gen.fallback_from, gen.primary_error, user_id)
        except GenerationError as exc:
            error = str(exc)
            log.warning("rag.generate failed: %s", exc)
            result.answer = "Sorry, the answer could not be generated right now."
            result.abstained = True
            result.error = error[:500]
    timings["total_ms"] = (time.perf_counter() - t_all) * 1000
    if write_log:
        result.query_id = _log(db, user_id, question, notebook_id, result, ranked, streamed=False, error=error)
    return result


# ── streaming ───────────────────────────────────────────────────────────────

def ask_stream(db: Session, user_id: int, question: str, notebook_id: Optional[int] = None,
               mode: Optional[str] = None, model: Optional[str] = None,
               write_log: bool = True) -> Iterator[dict]:
    """Yields {"event": name, "data": dict}. Events: sources, token*, done (or error)."""
    t_all = time.perf_counter()
    question = (question or "").strip()
    ranked, kept, flagged, sources, cites, top_score, mode_used, gate, timings = prepare(
        db, user_id, question, notebook_id, mode)
    yield {"event": "sources", "data": {
        "sources": [asdict(c) for c in cites], "retrieval_mode": mode_used, "top_score": top_score,
        "gate_triggered": gate, "guard_flagged_chunk_ids": flagged,
        "timings_ms": {k: round(v, 1) for k, v in timings.items()},
    }}

    result = AskResult(
        question=question, answer="", abstained=True, gate_triggered=gate, citations=[], sources=cites,
        retrieval_mode=mode_used, top_score=top_score, guard_flagged_chunk_ids=flagged,
        model=model or get_settings().rag_generation_model, timings_ms=timings,
    )
    error = None
    text = ""
    used_model: List[str] = []
    if sources:
        t = time.perf_counter()
        try:
            for delta in stream_answer_with_fallback(question, sources, weak_evidence=gate, model=model,
                                                     used_model=used_model):
                text += delta
                yield {"event": "token", "data": {"text": delta}}
        except GenerationError as exc:
            error = str(exc)
            log.warning("rag.stream failed: %s", exc)
        timings["generate_ms"] = (time.perf_counter() - t) * 1000
        if used_model:
            result.model = used_model[-1]
            if used_model[-1] != (model or get_settings().rag_generation_model):
                log.warning("rag.ask_stream served by fallback %s user=%s", used_model[-1], user_id)

    stripped = text.strip()
    if error:
        result.answer = "Sorry, the answer could not be generated right now."
    elif not sources or not stripped or stripped.startswith(STREAM_ABSTAIN_SENTINEL):
        result.answer = ABSTAIN_TEXT
        result.abstained = True
    else:
        nums = citations_from_text(stripped, len(sources))
        by_n = {c.n: c for c in cites}
        result.answer = stripped
        result.citations = [by_n[n] for n in nums if n in by_n]
        result.abstained = not nums   # ungrounded text is not a grounded answer
    timings["total_ms"] = (time.perf_counter() - t_all) * 1000
    if write_log:
        result.query_id = _log(db, user_id, question, notebook_id, result, ranked, streamed=True, error=error)
    yield {"event": "error" if error else "done", "data": {
        "answer": result.answer, "abstained": result.abstained,
        "citations": [asdict(c) for c in result.citations],
        "timings_ms": {k: round(v, 1) for k, v in timings.items()},
        "query_id": result.query_id, "model": result.model,
    }}


def sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
