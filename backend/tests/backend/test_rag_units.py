"""Unit tests for the vector type, normalization, RRF fusion, and retry policy. No database, no API."""
from app.rag.embeddings import l2_normalize as _norm
from app.rag.embeddings import _is_retryable as _retry
from app.rag.embeddings import suggested_delay
from app.rag.ingest import embedding_input
from app.rag.retrieval import RetrievedChunk, rrf_fuse
from app.rag.vector_type import Vector, from_pg_literal, to_pg_literal


def rc(cid, rank, source, note=1):
    return RetrievedChunk(chunk_id=cid, note_id=note, ordinal=0, page=1, heading=None, context="",
                          text=f"chunk {cid}", score=1.0 / rank, rank=rank, source=source)


class TestVectorType:
    def test_literal_roundtrip(self):
        v = [0.5, -1.25, 3.0]
        assert from_pg_literal(to_pg_literal(v)) == v
        assert to_pg_literal([1, 2]) == "[1.0,2.0]"
        assert from_pg_literal("[]") == []

    def test_sqlalchemy_processors(self):
        t = Vector(3)
        assert t.get_col_spec() == "vector(3)"
        assert t.bind_processor(None)([1, 2, 3]) == "[1.0,2.0,3.0]"
        assert t.bind_processor(None)(None) is None
        assert t.result_processor(None, None)("[1,2,3]") == [1.0, 2.0, 3.0]
        assert t.result_processor(None, None)(None) is None


class TestEmbeddingHelpers:
    def test_l2_normalize(self):
        v = _norm([3.0, 4.0])
        assert abs(v[0] - 0.6) < 1e-9 and abs(v[1] - 0.8) < 1e-9
        assert _norm([0.0, 0.0]) == [0.0, 0.0]

    def test_retryable_classification(self):
        class E(Exception):
            code = 429
        assert _retry(E("rate"))
        assert _retry(Exception("503 UNAVAILABLE"))
        assert not _retry(Exception("400 invalid argument"))

    def test_suggested_delay_parsed_from_429_body(self):
        assert suggested_delay(Exception("... Please retry in 35.24289074s. ...")) == 35.24289074
        assert suggested_delay(Exception("{'@type': 'RetryInfo', 'retryDelay': '14s'}")) == 14.0
        assert suggested_delay(Exception("500 boom")) is None

    def test_embedding_input_includes_context(self):
        assert embedding_input("Note > Sec", "body") == "Note > Sec\nbody"
        assert embedding_input("", "body") == "body"


class TestRRF:
    def test_item_in_both_lists_wins(self):
        fts = [rc(1, 1, "fts"), rc(2, 2, "fts"), rc(3, 3, "fts")]
        vec = [rc(2, 1, "vector"), rc(4, 2, "vector")]
        fused = rrf_fuse([fts, vec], k=60)
        assert fused[0].chunk_id == 2
        assert fused[0].parts == {"fts": 2, "vector": 1}
        assert fused[0].source == "hybrid"
        assert [c.rank for c in fused] == [1, 2, 3, 4]

    def test_scores_follow_formula(self):
        fused = rrf_fuse([[rc(1, 1, "fts")], [rc(1, 3, "vector")]], k=60)
        assert abs(fused[0].score - (1 / 61 + 1 / 63)) < 1e-12

    def test_weights_and_limit(self):
        fts = [rc(1, 1, "fts")]
        vec = [rc(2, 1, "vector")]
        fused = rrf_fuse([fts, vec], k=60, weights=[1.0, 2.0], limit=1)
        assert len(fused) == 1 and fused[0].chunk_id == 2

    def test_tie_broken_by_best_rank_then_id(self):
        fts = [rc(5, 1, "fts"), rc(6, 2, "fts")]
        vec = [rc(6, 1, "vector"), rc(5, 2, "vector")]
        fused = rrf_fuse([fts, vec], k=60)
        assert [c.chunk_id for c in fused] == [5, 6]   # equal scores, both best rank 1, lower id first

    def test_empty_inputs(self):
        assert rrf_fuse([[], []]) == []
        assert [c.chunk_id for c in rrf_fuse([[], [rc(9, 1, "vector")]])] == [9]

    def test_larger_k_flattens_top_ranks(self):
        a = [rc(1, 1, "fts"), rc(2, 10, "fts")]
        s_small = rrf_fuse([a], k=1)
        s_large = rrf_fuse([a], k=1000)
        ratio_small = s_small[0].score / s_small[1].score
        ratio_large = s_large[0].score / s_large[1].score
        assert ratio_small > ratio_large
