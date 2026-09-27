"""Top-1 retrieval score for answerable vs unanswerable questions.

    python -m eval.abstain_report [--thresholds 0.60,0.65,0.70]

Uses the eval user's current index and the cached query embeddings. Reports the
score distributions and, for each threshold, how many unanswerable questions
would slip through and how many answerable ones would be wrongly refused. This
is the evidence behind the abstain gate in the ask endpoint (DECISIONS.md D23).
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import User
from app.rag.retrieval import fts_search, vector_search
from eval.corpus import load_qa
from eval.metrics import percentile
from eval.run_eval import EVAL_EMAIL, QueryEmbeddingCache, resolve_db_url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", default="0.60,0.62,0.64,0.65,0.66,0.68,0.70")
    args = ap.parse_args(argv)
    db = sessionmaker(bind=create_engine(resolve_db_url()))()
    user = db.query(User).filter(User.email == EVAL_EMAIL).first()
    cache = QueryEmbeddingCache()
    rows = []
    for q in load_qa():
        hits = vector_search(db, user.id, cache.get(q.question), k=2)
        top1 = hits[0].score if hits else 0.0
        gap = (hits[0].score - hits[1].score) if len(hits) > 1 else 0.0
        rows.append((q.type, q.id, top1, gap, len(fts_search(db, user.id, q.question, k=5))))
    print(f"query embedding cache misses: {cache.misses}\n")
    print("| type | n | top-1 cosine min / p25 / p50 / max | top1-top2 gap p50 | FTS returned hits |")
    print("|---|---|---|---|---|")
    for t in ("single", "multi", "injection", "unanswerable"):
        sc = [r[2] for r in rows if r[0] == t]
        if not sc:
            continue
        gap = [r[3] for r in rows if r[0] == t]
        fts_hits = sum(1 for r in rows if r[0] == t and r[4] > 0)
        print(f"| {t} | {len(sc)} | {min(sc):.3f} / {percentile(sc, 25):.3f} / {percentile(sc, 50):.3f} / "
              f"{max(sc):.3f} | {percentile(gap, 50):.3f} | {fts_hits}/{len(sc)} |")
    ans = [r[2] for r in rows if r[0] in ("single", "multi")]
    un = [r[2] for r in rows if r[0] == "unanswerable"]
    print("\n| threshold | unanswerable passing (false answers) | answerable refused |")
    print("|---|---|---|")
    for thr in [float(x) for x in args.thresholds.split(",")]:
        print(f"| {thr:.2f} | {sum(1 for s in un if s >= thr)}/{len(un)} | {sum(1 for s in ans if s < thr)}/{len(ans)} |")
    print("\nunanswerable detail (id, top-1 cosine):", ", ".join(f"{r[1]}={r[2]:.3f}" for r in rows if r[0] == "unanswerable"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
