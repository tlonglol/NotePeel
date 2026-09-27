"""Search over note_chunks: lexical (Postgres FTS), dense (pgvector), and
hybrid (reciprocal rank fusion of both). The legacy ILIKE note search is kept
as the eval baseline.

Every query is scoped by owner_id in SQL. There is no code path that searches
across users. All modes return the same RetrievedChunk shape.

Hybrid overlaps the query-embedding API call with the FTS query: the vector
query cannot start until the embedding arrives, but FTS can run meanwhile.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace
from typing import Dict, List, Literal, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rag.embeddings import embed_query
from app.rag.vector_type import to_pg_literal

FtsQueryMode = Literal["and", "or"]
RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk_id: int
    note_id: int
    ordinal: int
    page: int
    heading: Optional[str]
    context: str
    text: str
    score: float
    rank: int                 # 1-based position in the list this chunk came from
    source: str               # "fts" | "vector" | "hybrid"
    parts: Dict[str, int] = field(default_factory=dict)   # hybrid: rank in each source list

    def to_dict(self) -> dict:
        return asdict(self)


# ── lexical ─────────────────────────────────────────────────────────────────

# AND: websearch_to_tsquery -> every term must match (precise, brittle for
#      natural-language questions full of incidental words).
# OR:  plainto_tsquery's '&' rewritten to '|' via its text form, then cast with
#      ::tsquery. The cast does not re-stem, so lexemes are not double-stemmed.
#      ts_rank_cd still rewards chunks that match more of the terms.
_FTS_SQL = """
WITH q AS (
    SELECT CASE
        WHEN :mode = 'and' THEN websearch_to_tsquery('english', :query)
        ELSE replace(plainto_tsquery('english', :query)::text, ' & ', ' | ')::tsquery
    END AS tsq
)
SELECT c.id, c.note_id, c.ordinal, c.page, c.heading, c.context, c.text,
       ts_rank_cd(c.tsv, q.tsq, 32) AS score
FROM note_chunks c, q
WHERE c.owner_id = :owner_id
  AND c.tsv @@ q.tsq
  AND (CAST(:notebook_id AS INTEGER) IS NULL
       OR c.note_id IN (SELECT note_id FROM note_notebooks WHERE notebook_id = :notebook_id))
ORDER BY score DESC, c.note_id, c.ordinal
LIMIT :k
"""


def _rows_to_chunks(rows, source: str) -> List[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=r.id, note_id=r.note_id, ordinal=r.ordinal, page=r.page,
            heading=r.heading, context=r.context, text=r.text,
            score=float(r.score), rank=i + 1, source=source,
        )
        for i, r in enumerate(rows)
    ]


def fts_search(
    db: Session,
    owner_id: int,
    query: str,
    k: int = 10,
    mode: FtsQueryMode = "or",
    notebook_id: Optional[int] = None,
) -> List[RetrievedChunk]:
    query = (query or "").strip()
    if not query:
        return []
    rows = db.execute(
        text(_FTS_SQL),
        {"query": query, "mode": mode, "owner_id": owner_id, "notebook_id": notebook_id, "k": k},
    ).fetchall()
    return _rows_to_chunks(rows, "fts")


# ── dense ───────────────────────────────────────────────────────────────────

# Exact scan by design: no ANN index. Per-user corpora are hundreds of chunks;
# the owner_id filter plus a sequential cosine scan is exact and, at this size,
# faster than an HNSW probe with post-filtering. See DECISIONS.md for the
# measured crossover. Score is cosine similarity (vectors are unit length).
_VECTOR_SQL = """
SELECT c.id, c.note_id, c.ordinal, c.page, c.heading, c.context, c.text,
       1 - (c.embedding <=> CAST(:q AS vector)) AS score
FROM note_chunks c
WHERE c.owner_id = :owner_id
  AND c.embedding IS NOT NULL
  AND (CAST(:notebook_id AS INTEGER) IS NULL
       OR c.note_id IN (SELECT note_id FROM note_notebooks WHERE notebook_id = :notebook_id))
ORDER BY c.embedding <=> CAST(:q AS vector), c.id
LIMIT :k
"""


def vector_search(
    db: Session,
    owner_id: int,
    query_vec: Sequence[float],
    k: int = 10,
    notebook_id: Optional[int] = None,
) -> List[RetrievedChunk]:
    rows = db.execute(
        text(_VECTOR_SQL),
        {"q": to_pg_literal(query_vec), "owner_id": owner_id, "notebook_id": notebook_id, "k": k},
    ).fetchall()
    return _rows_to_chunks(rows, "vector")


# ── fusion ──────────────────────────────────────────────────────────────────

def rrf_fuse(
    lists: Sequence[Sequence[RetrievedChunk]],
    k: int = RRF_K,
    weights: Optional[Sequence[float]] = None,
    limit: int = 10,
) -> List[RetrievedChunk]:
    """Reciprocal rank fusion: score(d) = sum_i w_i / (k + rank_i(d)).

    Rank-based, so it needs no score normalization between a ts_rank_cd value
    and a cosine similarity, which is why it is the standard choice for fusing
    lexical and dense lists. k=60 is the value from the original paper; larger
    k flattens the contribution of top ranks.
    """
    weights = list(weights) if weights else [1.0] * len(lists)
    scores: Dict[int, float] = {}
    best: Dict[int, RetrievedChunk] = {}
    parts: Dict[int, Dict[str, int]] = {}
    for w, lst in zip(weights, lists):
        for item in lst:
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + w / (k + item.rank)
            parts.setdefault(item.chunk_id, {})[item.source] = item.rank
            if item.chunk_id not in best or item.rank < best[item.chunk_id].rank:
                best[item.chunk_id] = item
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], min(parts[kv[0]].values()), kv[0]))
    fused: List[RetrievedChunk] = []
    for i, (cid, s) in enumerate(ordered[:limit]):
        src = best[cid]
        fused.append(RetrievedChunk(
            chunk_id=cid, note_id=src.note_id, ordinal=src.ordinal, page=src.page,
            heading=src.heading, context=src.context, text=src.text,
            score=s, rank=i + 1, source="hybrid", parts=dict(parts[cid]),
        ))
    return fused


# ── hybrid ──────────────────────────────────────────────────────────────────

def hybrid_search(
    db: Session,
    owner_id: int,
    query: str,
    k: int = 10,
    candidates: int = 20,
    rrf_k: int = RRF_K,
    fts_mode: FtsQueryMode = "or",
    notebook_id: Optional[int] = None,
    overlap: bool = False,
    query_vec: Optional[Sequence[float]] = None,
    timings: Optional[Dict[str, float]] = None,
    fts_weight: float = 1.0,
    lists_out: Optional[Dict[str, List[RetrievedChunk]]] = None,
) -> List[RetrievedChunk]:
    """FTS top-`candidates` and vector top-`candidates`, fused by RRF, top-k.

    `fts_weight` scales the lexical list's RRF contribution (vector is 1.0).
    `overlap=True` runs the embedding API call in a worker thread while the FTS
    query runs on the caller's session (the embedding call touches no database
    state, so the session stays single-threaded). Measured as noise against
    the embedding call's own variance (DECISIONS.md), so it defaults off.
    `query_vec` lets callers supply a precomputed embedding (the eval harness
    caches them). `timings`, if given, receives per-stage milliseconds.
    """
    query = (query or "").strip()
    t_all = time.perf_counter()
    embed_ms = fts_ms = vector_ms = 0.0

    def timed_embed():
        t = time.perf_counter()
        v = embed_query(query)
        return v, (time.perf_counter() - t) * 1000

    if query_vec is not None:
        t = time.perf_counter()
        fts = fts_search(db, owner_id, query, k=candidates, mode=fts_mode, notebook_id=notebook_id)
        fts_ms = (time.perf_counter() - t) * 1000
        qvec = list(query_vec)
    elif overlap:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(timed_embed)
            t = time.perf_counter()
            fts = fts_search(db, owner_id, query, k=candidates, mode=fts_mode, notebook_id=notebook_id)
            fts_ms = (time.perf_counter() - t) * 1000
            qvec, embed_ms = fut.result()
    else:
        qvec, embed_ms = timed_embed()
        t = time.perf_counter()
        fts = fts_search(db, owner_id, query, k=candidates, mode=fts_mode, notebook_id=notebook_id)
        fts_ms = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    vec = vector_search(db, owner_id, qvec, k=candidates, notebook_id=notebook_id)
    vector_ms = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    fused = rrf_fuse([fts, vec], k=rrf_k, weights=[fts_weight, 1.0], limit=k)
    fuse_ms = (time.perf_counter() - t) * 1000
    if lists_out is not None:
        lists_out["fts"] = fts
        lists_out["vector"] = vec

    if timings is not None:
        timings.update(embed_ms=embed_ms, fts_ms=fts_ms, vector_ms=vector_ms, fuse_ms=fuse_ms,
                       total_ms=(time.perf_counter() - t_all) * 1000)
    return fused


# ── baseline + helpers ──────────────────────────────────────────────────────

def ilike_note_search(db: Session, owner_id: int, query: str) -> List[int]:
    """The search the app shipped with: substring match over title/raw_text/
    subject/topic/tags, ordered by recency, not relevance. Note ids only.
    Delegates to NoteController.search_notes so the baseline is the real thing."""
    from app.controllers.note_controller import NoteController
    user = SimpleNamespace(id=owner_id)
    notes = NoteController.search_notes(db, user, query)
    return [n.id for n in notes]


def note_order(chunks: Sequence[RetrievedChunk]) -> List[int]:
    """Distinct note ids in the order their best chunk appears."""
    seen: List[int] = []
    for c in chunks:
        if c.note_id not in seen:
            seen.append(c.note_id)
    return seen
