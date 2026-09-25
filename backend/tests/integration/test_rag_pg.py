"""Ingestion + lexical retrieval against a real Postgres (see conftest)."""
from sqlalchemy import text

from app.models.chunk import NoteChunk
from app.models.note import Note, ProcessingStatus
from app.models.notebook import Notebook
from app.rag.chunker import ChunkConfig
from app.rag.ingest import ingest_note, reindex_user, safe_ingest
from app.rag.retrieval import fts_search, ilike_note_search, note_order
from scripts.note_html import PAGE_DIVIDER, bullets, h, p
from tests.integration.conftest import requires_pg

pytestmark = requires_pg


def make_note(db, user, title, html, raw=None):
    n = Note(owner_id=user.id, title=title, structured_text=html, raw_text=raw or "",
             status=ProcessingStatus.COMPLETED)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


PHOTO = (h("Photosynthesis") + p("Converts light energy into glucose inside the chloroplast.")
         + h("Calvin Cycle") + bullets(["Occurs in the stroma", "Rubisco fixes carbon dioxide onto RuBP"]))
RESP = (h("Cellular Respiration") + p("Breaks glucose down to make ATP in the mitochondria.")
        + bullets(["Glycolysis happens in the cytoplasm", "Oxygen is the final electron acceptor"]))


class TestIngest:
    def test_chunks_written_with_context_and_tsv(self, db, user):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        r = ingest_note(db, n)
        assert r.status == "indexed" and r.chunks == 2
        rows = db.query(NoteChunk).filter(NoteChunk.note_id == n.id).order_by(NoteChunk.ordinal).all()
        assert [c.ordinal for c in rows] == [0, 1]
        assert rows[0].context == "Photosynthesis > Photosynthesis"
        assert rows[1].context == "Photosynthesis > Calvin Cycle"
        assert rows[1].owner_id == user.id
        tsv = db.execute(text("SELECT tsv::text FROM note_chunks WHERE id = :id"), {"id": rows[1].id}).scalar()
        assert "rubisco" in tsv and "calvin" in tsv   # heading is in the lexical index via context

    def test_reingest_unchanged_is_skipped(self, db, user):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n)
        ids_before = [c.id for c in db.query(NoteChunk).filter(NoteChunk.note_id == n.id).all()]
        r = ingest_note(db, n)
        assert r.status == "skipped"
        ids_after = [c.id for c in db.query(NoteChunk).filter(NoteChunk.note_id == n.id).all()]
        assert ids_before == ids_after

    def test_edit_replaces_chunks_and_reports_reuse(self, db, user):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n)
        n.structured_text = PHOTO + h("Light Reactions") + p("Water is split and oxygen is released.")
        db.commit()
        r = ingest_note(db, n)
        assert r.status == "indexed" and r.chunks == 3
        assert r.reused_embeddings == 2   # two chunks' text unchanged -> their hashes were reusable
        assert db.query(NoteChunk).filter(NoteChunk.note_id == n.id).count() == 3

    def test_title_change_updates_context(self, db, user):
        n = make_note(db, user, "Old", PHOTO)
        ingest_note(db, n)
        n.title = "New Title"
        db.commit()
        assert ingest_note(db, n).status == "indexed"
        ctx = db.query(NoteChunk.context).filter(NoteChunk.note_id == n.id).first()[0]
        assert ctx.startswith("New Title >")

    def test_style_only_edit_is_skipped(self, db, user):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n)
        n.structured_text = PHOTO.replace('style="margin:10px 0;line-height:1.75;"', 'style="margin:0"')
        db.commit()
        assert ingest_note(db, n).status == "skipped"

    def test_empty_note(self, db, user):
        n = make_note(db, user, "Blank", "", raw="")
        r = ingest_note(db, n)
        assert r.status == "empty" and r.chunks == 0
        assert n.index_hash is None

    def test_delete_note_cascades_chunks(self, db, user):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        ingest_note(db, n)
        nid = n.id
        db.delete(n)
        db.commit()
        assert db.query(NoteChunk).filter(NoteChunk.note_id == nid).count() == 0

    def test_safe_ingest_never_raises(self, db, user, monkeypatch):
        n = make_note(db, user, "Photosynthesis", PHOTO)
        import app.rag.ingest as ingest_mod
        monkeypatch.setattr(ingest_mod, "chunk_note", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        r = safe_ingest(db, n)
        assert r.status == "failed" and "boom" in r.error
        # session is usable afterwards
        assert db.query(Note).filter(Note.id == n.id).count() == 1

    def test_reindex_user_with_other_granularity(self, db, user):
        n1 = make_note(db, user, "Photosynthesis", PHOTO)
        n2 = make_note(db, user, "Respiration", RESP)
        reindex_user(db, user.id)
        assert db.query(NoteChunk).filter(NoteChunk.owner_id == user.id).count() == 3
        reindex_user(db, user.id, cfg=ChunkConfig(granularity="note"), force=True)
        assert db.query(NoteChunk).filter(NoteChunk.owner_id == user.id).count() == 2
        assert {c.note_id for c in db.query(NoteChunk).filter(NoteChunk.owner_id == user.id)} == {n1.id, n2.id}

    def test_page_breaks_recorded(self, db, user):
        n = make_note(db, user, "Two pages", p("First page text.") + PAGE_DIVIDER + p("Second page text."))
        ingest_note(db, n)
        pages = [c.page for c in db.query(NoteChunk).filter(NoteChunk.note_id == n.id).order_by(NoteChunk.ordinal)]
        assert pages == [1, 2]


class TestFtsRetrieval:
    def test_finds_the_right_chunk(self, db, user):
        n1 = make_note(db, user, "Photosynthesis", PHOTO)
        n2 = make_note(db, user, "Respiration", RESP)
        reindex_user(db, user.id)
        hits = fts_search(db, user.id, "where does the calvin cycle happen", k=5)
        assert hits and hits[0].note_id == n1.id and "stroma" in hits[0].text
        assert hits[0].rank == 1 and hits[0].source == "fts"
        hits = fts_search(db, user.id, "final electron acceptor", k=5)
        assert hits[0].note_id == n2.id

    def test_and_vs_or_semantics(self, db, user):
        make_note(db, user, "Photosynthesis", PHOTO)
        reindex_user(db, user.id)
        q = "rubisco carbon zebra"   # 'zebra' appears nowhere
        assert fts_search(db, user.id, q, mode="and") == []
        assert len(fts_search(db, user.id, q, mode="or")) == 1

    def test_owner_isolation(self, db, user):
        from app.models.user import User
        other = User(email=f"other-{user.id}@notepeel.local", username=f"other_{user.id}", hashed_password="x")
        db.add(other)
        db.commit()
        try:
            make_note(db, user, "Photosynthesis", PHOTO)
            reindex_user(db, user.id)
            assert fts_search(db, other.id, "rubisco", k=5) == []
            assert fts_search(db, user.id, "rubisco", k=5)
        finally:
            db.execute(text("DELETE FROM users WHERE id = :id"), {"id": other.id})
            db.commit()

    def test_notebook_filter(self, db, user):
        n1 = make_note(db, user, "Photosynthesis", PHOTO)
        n2 = make_note(db, user, "Respiration", RESP)
        reindex_user(db, user.id)
        nb = Notebook(name="Bio", owner_id=user.id)
        nb.notes.append(n2)
        db.add(nb)
        db.commit()
        hits = fts_search(db, user.id, "glucose", k=5, notebook_id=nb.id)
        assert {c.note_id for c in hits} == {n2.id}
        hits = fts_search(db, user.id, "glucose", k=5)
        assert {c.note_id for c in hits} == {n1.id, n2.id}

    def test_empty_and_stopword_queries(self, db, user):
        make_note(db, user, "Photosynthesis", PHOTO)
        reindex_user(db, user.id)
        assert fts_search(db, user.id, "", k=5) == []
        assert fts_search(db, user.id, "the of and", k=5) == []

    def test_note_order_and_ilike_baseline(self, db, user):
        n1 = make_note(db, user, "Photosynthesis", PHOTO, raw="photosynthesis chloroplast")
        n2 = make_note(db, user, "Respiration", RESP, raw="respiration mitochondria")
        reindex_user(db, user.id)
        hits = fts_search(db, user.id, "glucose", k=5)
        assert set(note_order(hits)) == {n1.id, n2.id}
        assert ilike_note_search(db, user.id, "chloroplast") == [n1.id]
        assert ilike_note_search(db, user.id, "where is glucose made") == []   # substring of nothing
