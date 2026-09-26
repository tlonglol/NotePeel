"""Does TOAST storage of the 768-d vector column slow the exact scan?

A 768 x float4 vector is ~3 KB, above Postgres's 2 KB TOAST threshold, so with
pgvector's default EXTERNAL storage (out-of-line, uncompressed) every row
scanned by `ORDER BY embedding <=> q` is fetched from the TOAST relation.
PLAIN storage keeps the vector inline in the heap tuple.

    python -m eval.storage_test [--repeats 30]

Times the real eval corpus (the eval user's chunks) with the current storage,
switches the column to PLAIN, rewrites the table so existing tuples move, times
again, reports both, then restores the default storage so the database keeps
matching the migrations.
"""
from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import create_engine, text

from app.models import User
from app.rag.vector_type import to_pg_literal
from eval.metrics import percentile
from eval.run_eval import EVAL_EMAIL, QueryEmbeddingCache, resolve_db_url
from eval.corpus import load_qa

SQL = ("SELECT id FROM note_chunks WHERE owner_id = :u AND embedding IS NOT NULL "
       "ORDER BY embedding <=> CAST(:q AS vector), id LIMIT 20")


def bench(engine, uid, vecs, repeats):
    times = []
    with engine.connect() as c:
        for _ in range(repeats):
            for v in vecs:
                t = time.perf_counter()
                c.execute(text(SQL), {"u": uid, "q": to_pg_literal(v)}).fetchall()
                times.append((time.perf_counter() - t) * 1000)
    return {"p50": round(percentile(times, 50), 1), "p95": round(percentile(times, 95), 1), "n": len(times)}


def storage_info(engine):
    with engine.connect() as c:
        st = c.execute(text("SELECT attstorage FROM pg_attribute WHERE attrelid = 'note_chunks'::regclass AND attname = 'embedding'")).scalar()
        toast = c.execute(text("SELECT pg_size_pretty(pg_total_relation_size('note_chunks') - pg_relation_size('note_chunks'))")).scalar()
        heap = c.execute(text("SELECT pg_size_pretty(pg_relation_size('note_chunks'))")).scalar()
    return {"attstorage": st, "heap": heap, "toast_and_indexes": toast}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--queries", type=int, default=10)
    args = ap.parse_args(argv)
    engine = create_engine(resolve_db_url(), isolation_level="AUTOCOMMIT")
    with engine.connect() as c:
        uid = c.execute(text("SELECT id FROM users WHERE email = :e"), {"e": EVAL_EMAIL}).scalar()
        n = c.execute(text("SELECT count(*) FROM note_chunks WHERE owner_id = :u AND embedding IS NOT NULL"), {"u": uid}).scalar()
    cache = QueryEmbeddingCache()
    vecs = [cache.get(q.question) for q in load_qa() if q.answerable][: args.queries]

    before_info = storage_info(engine)
    before = bench(engine, uid, vecs, args.repeats)
    with engine.connect() as c:
        c.execute(text("ALTER TABLE note_chunks ALTER COLUMN embedding SET STORAGE PLAIN"))
        c.execute(text("VACUUM FULL note_chunks"))   # rewrite so existing tuples adopt the new storage
    after_info = storage_info(engine)
    after = bench(engine, uid, vecs, args.repeats)
    with engine.connect() as c:
        c.execute(text("ALTER TABLE note_chunks ALTER COLUMN embedding SET STORAGE EXTERNAL"))

    print(f"rows scanned per query: {n} (eval user), queries: {len(vecs)}, repeats: {args.repeats}")
    print("| storage | attstorage | heap size | toast+indexes | p50 ms | p95 ms | n |")
    print("|---|---|---|---|---|---|---|")
    print(f"| EXTERNAL (pgvector default) | {before_info['attstorage']} | {before_info['heap']} | {before_info['toast_and_indexes']} | {before['p50']} | {before['p95']} | {before['n']} |")
    print(f"| PLAIN | {after_info['attstorage']} | {after_info['heap']} | {after_info['toast_and_indexes']} | {after['p50']} | {after['p95']} | {after['n']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
