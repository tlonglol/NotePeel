"""Read the ask-your-notes query log: latency, abstain rate, cost, guard activity.

    DATABASE_URL="<url>" python -m scripts.rag_stats [--days 7] [--user-id N]

This is the in-region view. The eval harness measures latency from wherever it
runs (a dev machine, so every number includes a round trip to Neon); these
numbers come from inside the request that served a real user, which is the only
place the deployed stack's real p50/p95/p99 can be seen.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

from sqlalchemy import func

from app.database import SessionLocal
import app.models  # noqa: F401
from app.models.rag_query import RagQuery
from eval.metrics import percentile


def pct(values, p):
    v = percentile(values, p)
    return f"{v:.0f}" if v is not None else "-"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=0, help="only the last N days (0 = all)")
    ap.add_argument("--user-id", type=int, default=None)
    ap.add_argument("--limit-recent", type=int, default=5, help="show this many recent questions")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        q = db.query(RagQuery)
        if args.days:
            q = q.filter(RagQuery.created_at >= datetime.utcnow() - timedelta(days=args.days))
        if args.user_id:
            q = q.filter(RagQuery.user_id == args.user_id)
        rows = q.order_by(RagQuery.created_at).all()
        if not rows:
            print("no queries logged for that window")
            return 0

        total = len(rows)
        errors = [r for r in rows if r.error]
        abstained = [r for r in rows if r.abstained]
        gated = [r for r in rows if r.gate_triggered]
        guarded = [r for r in rows if r.guard_flagged_chunk_ids]
        streamed = [r for r in rows if r.streamed]

        print(f"queries: {total}  ({rows[0].created_at:%Y-%m-%d} to {rows[-1].created_at:%Y-%m-%d})")
        print(f"  abstained:        {len(abstained)} ({len(abstained) / total:.0%})")
        print(f"  weak-evidence gate triggered: {len(gated)} ({len(gated) / total:.0%})")
        print(f"  guard flagged a chunk: {len(guarded)}")
        print(f"  generation errors: {len(errors)}")
        print(f"  streamed: {len(streamed)} of {total}")
        print(f"  distinct users: {db.query(func.count(func.distinct(RagQuery.user_id))).scalar()}")

        print("\n| stage | p50 ms | p95 ms | p99 ms | n |")
        print("|---|---|---|---|---|")
        for label, attr in (("embed", "embed_ms"), ("retrieve", "retrieve_ms"),
                            ("generate", "generate_ms"), ("total", "total_ms")):
            vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
            print(f"| {label} | {pct(vals, 50)} | {pct(vals, 95)} | {pct(vals, 99)} | {len(vals)} |")

        cost = sum(r.estimated_cost_usd or 0 for r in rows)
        pt = sum(r.prompt_tokens or 0 for r in rows)
        ct = sum(r.completion_tokens or 0 for r in rows)
        print(f"\ncost: ${cost:.6f} total, ${cost / total:.6f} per query ({pt} prompt / {ct} completion tokens)")
        by_user = {}
        for r in rows:
            e = by_user.setdefault(r.user_id, {"n": 0, "usd": 0.0})
            e["n"] += 1
            e["usd"] += r.estimated_cost_usd or 0
        print("\n| user | queries | cost usd |")
        print("|---|---|---|")
        for uid, e in sorted(by_user.items(), key=lambda kv: -kv[1]["n"]):
            print(f"| {uid} | {e['n']} | {e['usd']:.6f} |")

        if args.limit_recent:
            print(f"\nmost recent {args.limit_recent}:")
            for r in rows[-args.limit_recent:]:
                flag = " ABSTAINED" if r.abstained else ""
                flag += " GATED" if r.gate_triggered else ""
                flag += f" GUARD{r.guard_flagged_chunk_ids}" if r.guard_flagged_chunk_ids else ""
                flag += " ERROR" if r.error else ""
                score = f"{r.top_score:.3f}" if r.top_score is not None else "-"
                print(f"  [{r.created_at:%m-%d %H:%M}] u{r.user_id} {r.retrieval_mode} top1={score} "
                      f"cited={len(r.cited_chunk_ids)} {r.total_ms:.0f}ms{flag}")
                print(f"     {r.question[:110]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
