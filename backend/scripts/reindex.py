"""Backfill / re-chunk / re-embed notes for retrieval.

    DATABASE_URL=... python -m scripts.reindex --all
    DATABASE_URL=... python -m scripts.reindex --email demo@notepeel.xyz --force
    DATABASE_URL=... python -m scripts.reindex --user-id 7 --no-embed

Idempotent: unchanged notes are skipped (hash match), unchanged chunks keep
their embeddings (content_hash match). --force re-chunks everything but still
reuses embeddings for chunks whose text did not change.
"""
from __future__ import annotations

import argparse
import sys
import time

from app.database import SessionLocal
import app.models  # noqa: F401
from app.models.user import User
from app.rag.ingest import reindex_user


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--user-id", type=int)
    g.add_argument("--email")
    ap.add_argument("--force", action="store_true", help="re-chunk even if the note hash is unchanged")
    ap.add_argument("--no-embed", action="store_true", help="lexical index only")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        q = db.query(User)
        if args.user_id:
            q = q.filter(User.id == args.user_id)
        elif args.email:
            q = q.filter(User.email == args.email)
        users = q.order_by(User.id).all()
        if not users:
            sys.exit("no matching users")

        totals = {"notes": 0, "chunks": 0, "embedded": 0, "reused": 0, "partial": 0, "failed": 0}
        t0 = time.perf_counter()
        for u in users:
            res = reindex_user(db, u.id, force=args.force, embed=False if args.no_embed else None)
            statuses = {}
            for r in res:
                statuses[r.status] = statuses.get(r.status, 0) + 1
            totals["notes"] += len(res)
            totals["chunks"] += sum(r.chunks for r in res)
            totals["embedded"] += sum(r.embedded for r in res)
            totals["reused"] += sum(r.reused_embeddings for r in res)
            totals["partial"] += statuses.get("partial", 0)
            totals["failed"] += statuses.get("failed", 0)
            print(f"user {u.id} {u.email}: {len(res)} notes {statuses}")
        print(f"done in {time.perf_counter() - t0:.1f}s: {totals}")
        return 1 if totals["partial"] or totals["failed"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
