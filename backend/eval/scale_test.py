"""Exact scan vs HNSW at scale, to justify (or overturn) "no ANN index".

    python -m eval.scale_test --sizes 200,2000,10000 --queries 20

For each size N: a throwaway user gets N chunk rows with random unit vectors
generated server-side (no network payload; the subquery is correlated on the
outer row so Postgres evaluates it per row instead of once), then
  1. exact filtered scan timing:  ORDER BY embedding <=> q  WHERE owner_id = u
  2. HNSW build time, then the same query with enable_seqscan off so the planner
     must use the index (SET LOCAL: transaction-scoped, pooler-safe)
  3. HNSW recall@10 against the exact result over the same random queries
Rows and index are dropped afterwards. Numbers are wall time from this machine
to the database, so compare rows to each other, not to absolute budgets.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from typing import List

from sqlalchemy import create_engine, text

from app.rag.vector_type import to_pg_literal
from eval.metrics import percentile
from eval.run_eval import resolve_db_url

DIMS = 768


def rand_unit(rng: random.Random) -> List[float]:
    v = [rng.gauss(0, 1) for _ in range(DIMS)]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def timed(engine_tx, sql: str, params: dict, repeats: int, setup_sql: str = "") -> tuple[float, float]:
    """Each repeat runs in its own real transaction so SET LOCAL applies."""
    times = []
    for _ in range(repeats):
        with engine_tx.begin() as c:
            if setup_sql:
                for stmt in setup_sql.split(";"):
                    c.execute(text(stmt))
            t = time.perf_counter()
            c.execute(text(sql), params).fetchall()
            times.append((time.perf_counter() - t) * 1000)
    return percentile(times, 50), percentile(times, 95)


def fetch_ids(engine_tx, sql: str, params: dict, setup_sql: str = "") -> set:
    with engine_tx.begin() as c:
        for stmt in (setup_sql.split(";") if setup_sql else []):
            c.execute(text(stmt))
        return {r[0] for r in c.execute(text(sql), params)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="200,2000,10000")
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--ef-search", type=int, default=40)
    args = ap.parse_args(argv)

    url = resolve_db_url()
    engine = create_engine(url, isolation_level="AUTOCOMMIT")   # setup, inserts, index build
    engine_tx = create_engine(url)                               # timed queries, real transactions
    rng = random.Random(7)
    rows_out = []
    with engine.connect() as conn:
        uid = conn.execute(text(
            "INSERT INTO users (email, username, hashed_password, is_active) "
            "VALUES ('scale-test@notepeel.local', 'scale_test', 'x', false) RETURNING id")).scalar()
        nid = conn.execute(text(
            "INSERT INTO notes (owner_id, title, status) VALUES (:u, 'scale', 'COMPLETED') RETURNING id"),
            {"u": uid}).scalar()
        try:
            inserted = 0
            for n in [int(x) for x in args.sizes.split(",")]:
                if n > inserted:
                    t = time.perf_counter()
                    conn.execute(text("""
                        INSERT INTO note_chunks (note_id, owner_id, ordinal, page, heading, context, text,
                                                 token_estimate, content_hash, embedding, embedding_model)
                        SELECT :nid, :uid, s.i, 1, NULL, 'scale', 'row ' || s.i, 3, md5(s.i::text),
                               (SELECT array_agg(random() - 0.5) FROM generate_series(1, :dims) g
                                WHERE g.g > 0 OR s.i IS NULL)::vector,
                               'random'
                        FROM generate_series(:lo, :hi) AS s(i)
                    """), {"nid": nid, "uid": uid, "dims": DIMS, "lo": inserted, "hi": n - 1})
                    # normalize server-side so cosine and inner product agree with real data
                    conn.execute(text("UPDATE note_chunks SET embedding = l2_normalize(embedding) "
                                      "WHERE owner_id = :u AND embedding_model = 'random'"), {"u": uid})
                    inserted = n
                    print(f"inserted up to {n} rows in {time.perf_counter() - t:.1f}s", file=sys.stderr)

                queries = [rand_unit(rng) for _ in range(args.queries)]
                sql = ("SELECT id FROM note_chunks WHERE owner_id = :u AND embedding IS NOT NULL "
                       "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 10")
                exact_p50s, exact_p95s = [], []
                exact_sets = []
                for q in queries:
                    p50, p95 = timed(engine_tx, sql, {"u": uid, "q": to_pg_literal(q)}, 3)
                    exact_p50s.append(p50)
                    exact_p95s.append(p95)
                    exact_sets.append(fetch_ids(engine_tx, sql, {"u": uid, "q": to_pg_literal(q)}))
                exact_p50 = percentile(exact_p50s, 50)

                t = time.perf_counter()
                conn.execute(text("CREATE INDEX ix_scale_hnsw ON note_chunks USING hnsw (embedding vector_cosine_ops)"))
                build_s = time.perf_counter() - t
                setup = f"SET LOCAL enable_seqscan = off;SET LOCAL hnsw.ef_search = {args.ef_search}"
                hnsw_p50s, recalls = [], []
                for q, exact in zip(queries, exact_sets):
                    p50, _ = timed(engine_tx, sql, {"u": uid, "q": to_pg_literal(q)}, 3, setup_sql=setup)
                    hnsw_p50s.append(p50)
                    got = fetch_ids(engine_tx, sql, {"u": uid, "q": to_pg_literal(q)}, setup_sql=setup)
                    recalls.append(len(got & exact) / max(1, len(exact)))
                conn.execute(text("DROP INDEX ix_scale_hnsw"))

                row = {"rows": n, "exact_p50_ms": round(exact_p50, 1),
                       "exact_p95_ms": round(percentile(exact_p95s, 50), 1),
                       "hnsw_p50_ms": round(percentile(hnsw_p50s, 50), 1), "hnsw_build_s": round(build_s, 1),
                       "hnsw_recall10": round(sum(recalls) / len(recalls), 3), "queries": len(queries)}
                rows_out.append(row)
                print(row, file=sys.stderr)
        finally:
            conn.execute(text("DELETE FROM notes WHERE owner_id = :u"), {"u": uid})
            conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})

    print("| chunks (one owner) | exact scan p50 ms | exact p95 ms | HNSW p50 ms | HNSW build s "
          "| HNSW recall@10 vs exact | queries |")
    print("|---|---|---|---|---|---|---|")
    for r in rows_out:
        print(f"| {r['rows']} | {r['exact_p50_ms']} | {r['exact_p95_ms']} | {r['hnsw_p50_ms']} "
              f"| {r['hnsw_build_s']} | {r['hnsw_recall10']} | {r['queries']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
