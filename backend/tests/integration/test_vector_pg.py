"""Embedding ingestion, vector search, and hybrid fusion against a real Postgres.

The embedding API is replaced by a deterministic bag-of-words hash embedder so
these tests run offline and assert exact behaviour (which chunks got embedded,
what was reused) rather than model quality.
"""
import hashlib
import re

import pytest

from app.models.chunk import NoteChunk
from app.models.note import Note, ProcessingStatus
from app.rag.embeddings import EmbeddingError
from app.rag.ingest import ingest_note, reindex_user
from app.rag.retrieval import fts_search, hybrid_search, vector_search
from scripts.note_html import bullets, h, p
from tests.integration.conftest import requires_pg

pytestmark = requires_pg
DIMS = 768


def fake_embed(text: str):
    """Hashed bag of words -> unit vector. Shared words => higher cosine."""
    v = [0.0] * DIMS
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIMS] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture
def embedder(monkeypatch):
    calls = {"docs": [], "queries": []}

    def embed_documents(texts):
        calls["docs"].append(list(texts))
        return [fake_embed(t) for t in texts]

    def embed_query(q):
        calls["queries"].append(q)
        return fake_embed(q)

    import app.rag.ingest as ingest_mod
    import app.rag.retrieval as retr_mod
    monkeypatch.setattr(ingest_mod, "embed_documents", embed_documents)
    monkeypatch.setattr(retr_mod, "embed_query", embed_query)
    monkeypatch.setattr(ingest_mod, "model_tag", lambda: "fake@768")
    return calls


def make_note(db, user, title, html):
    n = Note(owner_id=user.id, title=title, structured_text=html, raw_text="", status=ProcessingStatus.COMPLETED)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


PHOTO = (h("Photosynthesis") + p("Converts light energy into glucose inside the chloroplast.")
         + h("Calvin Cycle") + bullets(["Occurs in the stroma", "Rubisco fixes carbon dioxide onto RuBP"]))
RESP = (h("Cellular Respiration") + p("Breaks glucose down to make ATP in the mitochondria.")
        + bullets(["Glycolysis happens in the cytoplasm", "Oxygen is the final electron acceptor"]))
AIRBAG = h("Momentum") + p("Airbags work because the same change in momentum over a longer time means a smaller force.")


class TestEmbeddingIngest:
    def test_embeds_every_chunk_with_context(self, db, user, embedder):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        r = ingest_note(db, n, embed=True)
        assert r.status == "indexed" and r.chunks == 2 and r.embedded == 2 and r.reused_embeddings == 0
        assert len(embedder["docs"]) == 1 and len(embedder["docs"][0]) == 2
        assert embedder["docs"][0][1].startswith("Photosynthesis > Calvin Cycle\n")
        rows = db.query(NoteChunk).filter(NoteChunk.note_id == n.id).order_by(NoteChunk.ordinal).all()
        assert all(len(c.embedding) == DIMS for c in rows)
        assert all(c.embedding_model == "fake@768" for c in rows)

    def test_edit_reembeds_only_changed_chunk(self, db, user, embedder):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n, embed=True)
        n.structured_text = PHOTO + h("Light Reactions") + p("Water is split and oxygen is released.")
        db.commit()
        r = ingest_note(db, n, embed=True)
        assert r.status == "indexed" and r.chunks == 3
        assert r.reused_embeddings == 2 and r.embedded == 1
        assert len(embedder["docs"]) == 2 and len(embedder["docs"][1]) == 1   # second call embedded one text

    def test_unchanged_note_skipped_no_api_calls(self, db, user, embedder):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n, embed=True)
        assert ingest_note(db, n, embed=True).status == "skipped"
        assert len(embedder["docs"]) == 1

    def test_lexical_only_then_backfill_embeds(self, db, user, embedder):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        assert ingest_note(db, n, embed=False).embedded == 0
        assert db.query(NoteChunk).filter(NoteChunk.note_id == n.id, NoteChunk.embedding.is_(None)).count() == 2
        r = ingest_note(db, n, embed=True)          # hash unchanged, but embeddings missing -> not skipped
        assert r.status == "indexed" and r.embedded == 2

    def test_embedding_failure_keeps_chunks_and_retries_later(self, db, user, embedder, monkeypatch):
        import app.rag.ingest as ingest_mod
        n = make_note(db, user, "Photosynthesis", PHOTO)

        def boom(texts):
            raise EmbeddingError("quota")
        monkeypatch.setattr(ingest_mod, "embed_documents", boom)
        r = ingest_note(db, n, embed=True)
        assert r.status == "partial" and r.chunks == 2 and r.embedded == 0 and "quota" in r.error
        assert n.index_hash is None
        assert fts_search(db, user.id, "rubisco")            # lexical search still works
        monkeypatch.setattr(ingest_mod, "embed_documents", lambda texts: [fake_embed(t) for t in texts])
        assert ingest_note(db, n, embed=True).status == "indexed"


class TestVectorAndHybrid:
    def test_vector_search_ranks_by_similarity_and_isolates_owner(self, db, user, embedder):
        n1 = make_note(db, user, "Photosynthesis", PHOTO)
        n2 = make_note(db, user, "Respiration", RESP)
        reindex_user(db, user.id, embed=True)
        hits = vector_search(db, user.id, fake_embed("rubisco carbon dioxide stroma"), k=3)
        assert hits[0].note_id == n1.id and hits[0].source == "vector" and 0 < hits[0].score <= 1.0
        assert hits[0].rank == 1
        assert vector_search(db, user.id + 100000, fake_embed("rubisco"), k=3) == []
        assert {c.note_id for c in vector_search(db, user.id, fake_embed("oxygen electron acceptor"), k=1)} == {n2.id}

    def test_null_embeddings_are_skipped(self, db, user, embedder):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n, embed=False)
        assert vector_search(db, user.id, fake_embed("rubisco"), k=5) == []

    def test_hybrid_fuses_and_reports_timings(self, db, user, embedder):
        n1 = make_note(db, user, "Photosynthesis", PHOTO)
        make_note(db, user, "Respiration", RESP)
        make_note(db, user, "Momentum", AIRBAG)
        reindex_user(db, user.id, embed=True)
        timings = {}
        hits = hybrid_search(db, user.id, "rubisco fixes carbon dioxide", k=5, timings=timings)
        assert hits[0].note_id == n1.id and hits[0].source == "hybrid"
        assert set(hits[0].parts) == {"fts", "vector"}          # found by both
        assert [c.rank for c in hits] == list(range(1, len(hits) + 1))
        assert {"embed_ms", "fts_ms", "vector_ms", "fuse_ms", "total_ms"} <= set(timings)
        assert embedder["queries"] == ["rubisco fixes carbon dioxide"]

    def test_hybrid_overlap_and_sequential_agree(self, db, user, embedder):
        make_note(db, user, "Photosynthesis", PHOTO)
        make_note(db, user, "Momentum", AIRBAG)
        reindex_user(db, user.id, embed=True)
        a = hybrid_search(db, user.id, "airbag force momentum", k=5, overlap=True)
        b = hybrid_search(db, user.id, "airbag force momentum", k=5, overlap=False)
        c = hybrid_search(db, user.id, "airbag force momentum", k=5, query_vec=fake_embed("airbag force momentum"))
        assert [x.chunk_id for x in a] == [x.chunk_id for x in b] == [x.chunk_id for x in c]

    def test_hybrid_notebook_filter_applies_to_both_sources(self, db, user, embedder):
        from app.models.notebook import Notebook
        n1 = make_note(db, user, "Photosynthesis", PHOTO)
        n2 = make_note(db, user, "Respiration", RESP)
        reindex_user(db, user.id, embed=True)
        nb = Notebook(name="Bio", owner_id=user.id)
        nb.notes.append(n2)
        db.add(nb)
        db.commit()
        hits = hybrid_search(db, user.id, "glucose", k=5, notebook_id=nb.id)
        assert hits and {c.note_id for c in hits} == {n2.id}
        assert n1.id not in {c.note_id for c in hits}
