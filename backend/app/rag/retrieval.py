"""Search over note_chunks.

Phase 1 ships lexical retrieval (Postgres full-text search) and a wrapper
around the legacy ILIKE note search so the eval harness can measure the
baseline the app shipped with. Vector and hybrid modes arrive in Phase 2 and
return the same RetrievedChunk shape so callers never care which path ran.

Every query is scoped by owner_id in SQL. There is no code path that searches
across users.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from types import SimpleNamespace
from typing import List, Literal, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

FtsQueryMode = Literal["and", "or"]


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
    rank: int          # 1-based position in the list this chunk came from
    source: str        # "fts", "vector", "hybrid", ...

    def to_dict(self) -> dict:
        return asdict(self)


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
    return [
        RetrievedChunk(
            chunk_id=r.id, note_id=r.note_id, ordinal=r.ordinal, page=r.page,
            heading=r.heading, context=r.context, text=r.text,
            score=float(r.score), rank=i + 1, source="fts",
        )
        for i, r in enumerate(rows)
    ]


def ilike_note_search(db: Session, owner_id: int, query: str) -> List[int]:
    """The search the app shipped with: substring match over title/raw_text/
    subject/topic/tags, ordered by recency, not relevance. Note ids only.
    Delegates to NoteController.search_notes so the baseline is the real thing."""
    from app.controllers.note_controller import NoteController
    user = SimpleNamespace(id=owner_id)
    notes = NoteController.search_notes(db, user, query)
    return [n.id for n in notes]


def note_order(chunks: List[RetrievedChunk]) -> List[int]:
    """Distinct note ids in the order their best chunk appears."""
    seen: List[int] = []
    for c in chunks:
        if c.note_id not in seen:
            seen.append(c.note_id)
    return seen
