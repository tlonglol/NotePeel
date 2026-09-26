"""Retrieval evaluation harness.

    EVAL_DATABASE_URL=postgresql://... python -m eval.run_eval \
        --modes ilike,fts_and,fts_or --chunking window,section,note,window:60:100 --repeats 5

What it does
  1. Validates the corpus + QA set (evidence spans must exist inside a chunk
     under every granularity, or the run refuses to start).
  2. Upserts the corpus under a dedicated eval user (matched by title, so
     re-runs reuse rows and, from Phase 2, embeddings).
  3. For each granularity: re-chunks the eval user's notes, then for each mode
     runs every answerable question, scoring:
        chunk-level  recall@1, recall@5, MRR@10   (evidence-span coverage)
        note-level   recall@5, MRR@10             (expected note ids)
     and times the retrieval call `repeats` times per question for p50/p95/p99.
  4. Writes eval/results/<timestamp>.json with per-question detail and prints
     markdown tables. Every number carries its n.

Latency is wall time of the retrieval function measured from wherever this
runs, so it includes the network hop to the database. Lambda-side numbers come
from the query log (Phase 3).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.controllers.auth_controller import AuthController
from app.models import Note, NoteChunk, ProcessingStatus, User
from app.rag.chunker import ChunkConfig, estimate_tokens
from app.rag.ingest import reindex_user
from app.rag.embeddings import embed_query, model_tag
from app.rag.retrieval import RetrievedChunk, fts_search, hybrid_search, ilike_note_search, note_order, vector_search
from eval.corpus import CorpusNote, QAItem, load_notes, load_qa, norm, validate
from eval.metrics import bootstrap_ci, coverage_at_k, mean, percentile, reciprocal_rank

EVAL_EMAIL = "eval@notepeel.local"
EVAL_USERNAME = "eval_corpus"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
K_MAX = 10

MODES: Dict[str, str] = {
    "ilike": "legacy substring search over whole notes, ordered by recency (what the app shipped with)",
    "fts_and": "Postgres FTS over chunks, websearch_to_tsquery (all terms required)",
    "fts_or": "Postgres FTS over chunks, OR of stemmed terms, ts_rank_cd",
    "vector": "pgvector exact cosine scan over chunk embeddings (Gemini, 768-d)",
    "hybrid": "RRF of fts_or and vector (top-20 each, k=60); embedding call overlapped with FTS",
    "hybrid_seq": "same as hybrid but embedding call and FTS run sequentially (latency ablation)",
}
CACHE_DIR = Path(__file__).resolve().parent / ".cache"


class QueryEmbeddingCache:
    """Question -> embedding, on disk, keyed by model tag. Used for the accuracy
    pass so re-runs are free and deterministic. The latency pass bypasses it."""

    def __init__(self) -> None:
        CACHE_DIR.mkdir(exist_ok=True)
        self.path = CACHE_DIR / f"qemb_{model_tag().replace('@', '_')}.json"
        self.data: Dict[str, List[float]] = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.misses = 0

    def get(self, question: str) -> List[float]:
        if question not in self.data:
            self.data[question] = embed_query(question)
            self.misses += 1
            self.path.write_text(json.dumps(self.data))
        return self.data[question]


# ── setup ───────────────────────────────────────────────────────────────────

def resolve_db_url() -> str:
    for key in ("EVAL_DATABASE_URL", "TEST_DATABASE_URL"):
        if os.environ.get(key):
            return os.environ[key]
    env_test = Path(__file__).resolve().parent.parent / ".env.test"
    if env_test.exists():
        for line in env_test.read_text().splitlines():
            if line.startswith("TEST_DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    sys.exit("set EVAL_DATABASE_URL (or TEST_DATABASE_URL / backend/.env.test)")


def db_kind(url: str) -> str:
    if "pooler" in url:
        return "neon-pooler"
    if "neon.tech" in url:
        return "neon-direct"
    if "localhost" in url or "127.0.0.1" in url:
        return "local"
    return "other"


def ensure_user(db: Session) -> User:
    user = db.query(User).filter(User.email == EVAL_EMAIL).first()
    if not user:
        user = User(email=EVAL_EMAIL, username=EVAL_USERNAME,
                    hashed_password=AuthController.hash_password("eval-not-a-login"), is_active=False)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def upsert_corpus(db: Session, user: User, notes: List[CorpusNote]) -> Dict[str, int]:
    """Create/update eval notes by title. created_at is spaced deterministically
    so the recency-ordered ILIKE baseline is reproducible."""
    existing = {n.title: n for n in db.query(Note).filter(Note.owner_id == user.id).all()}
    wanted = {n.title for n in notes}
    for title, n in existing.items():
        if title not in wanted:
            db.delete(n)
    base = datetime(2026, 1, 1)
    slug_to_id: Dict[str, int] = {}
    for i, cn in enumerate(notes):
        n = existing.get(cn.title)
        if n is None:
            n = Note(owner_id=user.id, title=cn.title, status=ProcessingStatus.COMPLETED,
                     image_filename=f"{cn.slug}.jpg")
            db.add(n)
        n.raw_text = cn.raw_text
        n.structured_text = cn.structured_text
        n.subject, n.topic, n.tags = cn.subject, cn.topic, cn.tags
        n.created_at = base + timedelta(minutes=i)
        n.processed_at = n.created_at
        db.flush()
        slug_to_id[cn.slug] = n.id
    db.commit()
    return slug_to_id


def parse_chunk_spec(spec: str) -> ChunkConfig:
    """'window' | 'section' | 'note' | 'window:60:100' (granularity:target_tokens:max_tokens)."""
    parts = spec.split(":")
    gran = parts[0]
    if gran not in ("window", "section", "note"):
        raise SystemExit(f"bad chunk spec {spec!r}")
    if len(parts) == 1:
        return ChunkConfig(granularity=gran)  # type: ignore[arg-type]
    target, mx = int(parts[1]), int(parts[2])
    return ChunkConfig(granularity=gran, target_tokens=target, max_tokens=mx,  # type: ignore[arg-type]
                       min_tail_tokens=min(40, max(8, target // 4)))


def chunk_stats(db: Session, user_id: int) -> dict:
    rows = db.query(NoteChunk.note_id, NoteChunk.token_estimate).filter(NoteChunk.owner_id == user_id).all()
    toks = [t for _, t in rows]
    per_note: Dict[int, int] = {}
    for nid, _ in rows:
        per_note[nid] = per_note.get(nid, 0) + 1
    return {
        "chunks": len(rows),
        "notes": len(per_note),
        "tokens_mean": round(mean(toks) or 0, 1),
        "tokens_p50": percentile(toks, 50),
        "tokens_p95": percentile(toks, 95),
        "tokens_max": max(toks) if toks else None,
        "chunks_per_note_mean": round(len(rows) / len(per_note), 2) if per_note else None,
    }


# ── one mode ────────────────────────────────────────────────────────────────

def make_retriever(mode: str, db: Session, user_id: int, cache: QueryEmbeddingCache,
                   stages: List[dict], rrf_k: int, candidates: int,
                   fts_weight: float = 1.0) -> Callable[[str, bool], tuple]:
    """Return fn(question, live) -> (chunks or None, ranked_note_ids).
    live=False may use the query-embedding cache; live=True always calls the API
    and appends per-stage timings to `stages`."""
    if mode == "ilike":
        return lambda q, live: (None, ilike_note_search(db, user_id, q))
    if mode in ("fts_and", "fts_or"):
        fmode = "and" if mode == "fts_and" else "or"

        def f(q, live):
            ch = fts_search(db, user_id, q, k=K_MAX, mode=fmode)
            return ch, note_order(ch)
        return f
    if mode == "vector":
        def f(q, live):
            if live:
                t = time.perf_counter()
                v = embed_query(q)
                embed_ms = (time.perf_counter() - t) * 1000
                t = time.perf_counter()
                ch = vector_search(db, user_id, v, k=K_MAX)
                stages.append({"embed_ms": embed_ms, "vector_ms": (time.perf_counter() - t) * 1000})
            else:
                ch = vector_search(db, user_id, cache.get(q), k=K_MAX)
            return ch, note_order(ch)
        return f
    if mode in ("hybrid", "hybrid_seq"):
        overlap = mode == "hybrid"

        def f(q, live):
            timings: Dict[str, float] = {}
            ch = hybrid_search(db, user_id, q, k=K_MAX, candidates=candidates, rrf_k=rrf_k,
                               overlap=overlap, query_vec=None if live else cache.get(q), timings=timings,
                               fts_weight=fts_weight)
            if live:
                stages.append(timings)
            return ch, note_order(ch)
        return f
    raise ValueError(f"unknown mode {mode}")


LIVE_MODES = ("vector", "hybrid", "hybrid_seq")


def run_mode(db: Session, user_id: int, mode: str, qa: List[QAItem],
             slug_to_id: Dict[str, int], repeats: int, cache: QueryEmbeddingCache,
             rrf_k: int = 60, candidates: int = 20, live_repeats: int = 2, live_rpm: int = 90,
             fts_weight: float = 1.0) -> dict:
    stages: List[dict] = []
    retrieve = make_retriever(mode, db, user_id, cache, stages, rrf_k, candidates, fts_weight)
    answerable = [q for q in qa if q.answerable]
    live = mode in LIVE_MODES
    if live:
        repeats = live_repeats
    # Live modes call the embedding API per query. The free tier allows 100
    # requests/min, and a throttled call would record the throttle wait as
    # latency, so live calls are paced below the limit (the pause is outside
    # the timed region).
    pace_s = 60.0 / live_rpm if live else 0.0

    def chunk_covers(c: RetrievedChunk, ev) -> bool:
        return c.note_id == slug_to_id[ev.note] and norm(ev.span) in norm(c.text)

    def note_covers(nid: int, slug: str) -> bool:
        return nid == slug_to_id[slug]

    per_q: List[dict] = []
    latencies: List[float] = []
    for q in answerable:
        chunks, ranked_notes = retrieve(q.question, False)
        rec = {"id": q.id, "type": q.type, "tags": q.tags}
        if chunks is not None:
            rec["chunk_r1"] = coverage_at_k(chunks, q.evidence, 1, chunk_covers)
            rec["chunk_r5"] = coverage_at_k(chunks, q.evidence, 5, chunk_covers)
            rec["chunk_mrr10"] = reciprocal_rank(chunks, q.evidence, 10, chunk_covers)
            rec["top5_chunks"] = [(c.chunk_id, c.note_id, round(c.score, 4)) for c in chunks[:5]]
            rec["ctx_tokens_top5"] = sum(estimate_tokens(c.text) for c in chunks[:5])
        rec["note_r5"] = coverage_at_k(ranked_notes, q.notes, 5, note_covers)
        rec["note_mrr10"] = reciprocal_rank(ranked_notes, q.notes, 10, note_covers)
        rec["top5_notes"] = ranked_notes[:5]
        rec["expected_notes"] = [slug_to_id[s] for s in q.notes]
        per_q.append(rec)

        for _ in range(repeats):
            if pace_s:
                time.sleep(pace_s)
            t0 = time.perf_counter()
            retrieve(q.question, True)
            latencies.append((time.perf_counter() - t0) * 1000)

    def agg(key: str, subset: Optional[List[dict]] = None) -> Optional[dict]:
        rows = subset if subset is not None else per_q
        vals = [r[key] for r in rows if key in r and r[key] is not None]
        if not vals:
            return None
        ci = bootstrap_ci(vals)
        return {"mean": round(mean(vals), 4), "n": len(vals),
                "ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None}

    headline_rows = [r for r in per_q if r["type"] in ("single", "multi")]
    summary = {k: agg(k, headline_rows)
               for k in ("chunk_r1", "chunk_r5", "chunk_mrr10", "note_r5", "note_mrr10", "ctx_tokens_top5")}
    by_type = {
        t: {k: agg(k, [r for r in per_q if r["type"] == t]) for k in ("chunk_r5", "note_r5", "chunk_mrr10")}
        for t in sorted({r["type"] for r in per_q})
    }
    return {
        "mode": mode,
        "description": MODES[mode],
        "summary": summary,
        "by_type": by_type,
        "latency_ms": {
            "n": len(latencies),
            "p50": round(percentile(latencies, 50), 2) if latencies else None,
            "p95": round(percentile(latencies, 95), 2) if latencies else None,
            "p99": round(percentile(latencies, 99), 2) if latencies else None,
            "repeats": repeats,
        },
        "fusion": {"rrf_k": rrf_k, "candidates": candidates, "fts_weight": fts_weight} if mode.startswith("hybrid") else None,
        "stage_ms": {
            key: {"p50": round(percentile(vals, 50), 1), "p95": round(percentile(vals, 95), 1), "n": len(vals)}
            for key in sorted({k for st in stages for k in st})
            for vals in [[st[key] for st in stages if key in st]]
        } if stages else {},
        "questions": per_q,
    }


# ── reporting ───────────────────────────────────────────────────────────────

def fmt(cell: Optional[dict]) -> str:
    if not cell:
        return "n/a"
    ci = f" [{cell['ci95'][0]:.2f}, {cell['ci95'][1]:.2f}]" if cell.get("ci95") else ""
    return f"{cell['mean']:.3f}{ci} (n={cell['n']})"


def fmt_tokens(cell: Optional[dict]) -> str:
    return f"{cell['mean']:.0f} (n={cell['n']})" if cell else "n/a"


def markdown_table(runs: List[dict]) -> str:
    lines = [
        "| mode | chunking | chunk R@1 | chunk R@5 [95% CI] | chunk MRR@10 | note R@5 | note MRR@10 "
        "| ctx tokens@5 | p50 ms | p95 ms | p99 ms | latency n |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        s, lat = r["summary"], r["latency_ms"]
        lines.append(
            f"| {r['mode']} | {r['granularity']} | {fmt(s['chunk_r1'])} | {fmt(s['chunk_r5'])} | "
            f"{fmt(s['chunk_mrr10'])} | {fmt(s['note_r5'])} | {fmt(s['note_mrr10'])} | "
            f"{fmt_tokens(s['ctx_tokens_top5'])} | "
            f"{lat['p50'] if lat['p50'] is not None else '-'} | {lat['p95'] if lat['p95'] is not None else '-'} | "
            f"{lat['p99'] if lat['p99'] is not None else '-'} | {lat['n']} |"
        )
    return "\n".join(lines)


def by_type_table(runs: List[dict]) -> str:
    lines = ["| mode | chunking | type | chunk R@5 | note R@5 | chunk MRR@10 |", "|---|---|---|---|---|---|"]
    for r in runs:
        for t, cells in r["by_type"].items():
            lines.append(f"| {r['mode']} | {r['granularity']} | {t} | {fmt(cells['chunk_r5'])} | "
                         f"{fmt(cells['note_r5'])} | {fmt(cells['chunk_mrr10'])} |")
    return "\n".join(lines)


def stage_table(runs: List[dict]) -> str:
    rows = [r for r in runs if r.get("stage_ms")]
    if not rows:
        return ""
    keys = ["embed_ms", "fts_ms", "vector_ms", "fuse_ms", "total_ms"]
    lines = ["| mode | chunking | " + " | ".join(f"{k} p50 / p95" for k in keys) + " | n |",
             "|---|---|" + "---|" * (len(keys) + 1)]
    for r in rows:
        cells = []
        for k in keys:
            c = r["stage_ms"].get(k)
            cells.append(f"{c['p50']} / {c['p95']}" if c else "-")
        n = next(iter(r["stage_ms"].values()))["n"]
        lines.append(f"| {r['mode']} | {r['granularity']} | " + " | ".join(cells) + f" | {n} |")
    return "\n".join(lines)


def chunk_table(stats: Dict[str, dict]) -> str:
    lines = ["| chunking | chunks | notes | chunks/note | tokens mean | tokens p50 | tokens p95 | tokens max |",
             "|---|---|---|---|---|---|---|---|"]
    for g, s in stats.items():
        lines.append(f"| {g} | {s['chunks']} | {s['notes']} | {s['chunks_per_note_mean']} | {s['tokens_mean']} | "
                     f"{s['tokens_p50']} | {s['tokens_p95']} | {s['tokens_max']} |")
    return "\n".join(lines)


# ── main ────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", default="ilike,fts_or,vector,hybrid")
    ap.add_argument("--chunking", default="window",
                    help="comma list of chunk specs: window | section | note | window:60:100 (gran:target:max)")
    ap.add_argument("--repeats", type=int, default=5, help="latency repeats per question")
    ap.add_argument("--no-real", action="store_true", help="exclude eval/corpus/real/*.json")
    ap.add_argument("--out", default=str(RESULTS_DIR))
    ap.add_argument("--label", default="", help="free-text label stored in the results file")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--candidates", type=int, default=20, help="per-source candidate depth before fusion")
    ap.add_argument("--no-embed", action="store_true", help="index lexically only (no embedding API calls)")
    ap.add_argument("--live-repeats", type=int, default=2,
                    help="latency repeats for modes that call the embedding API per query")
    ap.add_argument("--live-rpm", type=int, default=90, help="pacing for live embedding calls (free tier: 100/min)")
    ap.add_argument("--fts-weight", default="1.0",
                    help="comma list of lexical RRF weights to sweep for hybrid modes (vector weight is 1.0)")
    ap.add_argument("--rrf-ks", default=None, help="comma list of RRF k values to sweep (overrides --rrf-k)")
    args = ap.parse_args(argv)

    notes = load_notes(include_real=not args.no_real, include_adversarial=True)
    qa = load_qa()
    problems = validate(notes, qa)
    if problems:
        print("corpus/QA validation failed:")
        for pr in problems:
            print("  -", pr)
        return 2

    url = resolve_db_url()
    engine = create_engine(url, pool_pre_ping=True)
    db = sessionmaker(bind=engine)()
    user = ensure_user(db)
    slug_to_id = upsert_corpus(db, user, notes)

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    specs = [g.strip() for g in args.chunking.split(",") if g.strip()]
    need_embed = (not args.no_embed) and any(m in ("vector", "hybrid", "hybrid_seq") for m in modes)
    cache = QueryEmbeddingCache() if need_embed else None
    runs: List[dict] = []
    stats: Dict[str, dict] = {}
    for spec in specs:
        cfg = parse_chunk_spec(spec)
        t0 = time.perf_counter()
        results = reindex_user(db, user.id, cfg=cfg, force=True, embed=need_embed)
        stats[spec] = chunk_stats(db, user.id)
        stats[spec]["config"] = cfg.signature()
        stats[spec]["ingest"] = {
            "total_ms": round((time.perf_counter() - t0) * 1000),
            "embedded": sum(r.embedded for r in results),
            "reused_embeddings": sum(r.reused_embeddings for r in results),
            "embedding_ms_total": round(sum(r.embedding_ms for r in results)),
            "statuses": {st: sum(1 for r in results if r.status == st) for st in {r.status for r in results}},
        }
        print(f"indexed {spec}: {stats[spec]['ingest']}", file=sys.stderr)
        rrf_ks = [int(x) for x in args.rrf_ks.split(",")] if args.rrf_ks else [args.rrf_k]
        fts_weights = [float(x) for x in args.fts_weight.split(",")]
        for m in modes:
            if m == "ilike" and spec != specs[0]:
                continue  # ILIKE ignores chunks; run it once
            grid = [(kk, w) for kk in rrf_ks for w in fts_weights] if m.startswith("hybrid") else [(args.rrf_k, 1.0)]
            for kk, w in grid:
                r = run_mode(db, user.id, m, qa, slug_to_id, args.repeats, cache,
                             rrf_k=kk, candidates=args.candidates,
                             live_repeats=args.live_repeats, live_rpm=args.live_rpm, fts_weight=w)
                label = m if not m.startswith("hybrid") or len(grid) == 1 else f"{m}(k={kk},w={w})"
                r["mode"] = label
                r["granularity"] = spec if m != "ilike" else "n/a"
                r["chunk_config"] = cfg.signature()
                runs.append(r)
                print(f"done {label} / {spec}", file=sys.stderr)

    counts = {
        "notes_total": len(notes),
        "notes_synthetic": sum(1 for n in notes if n.source == "synthetic"),
        "notes_real": sum(1 for n in notes if n.source == "real"),
        "notes_adversarial": sum(1 for n in notes if n.adversarial),
        "qa_total": len(qa),
        "qa_by_type": {t: sum(1 for q in qa if q.type == t) for t in sorted({q.type for q in qa})},
    }
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "label": args.label,
        "db_kind": db_kind(url),
        "corpus": counts,
        "embedding_model": model_tag() if need_embed else None,
        "rrf_k": args.rrf_k,
        "candidates": args.candidates,
        "query_embedding_cache_misses": cache.misses if cache else 0,
        "chunk_stats": stats,
        "runs": runs,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = re.sub(r"[^0-9T]", "", out["timestamp"])[:15]
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps(out, indent=2))

    print(f"\ncorpus: {counts}")
    print(f"db: {out['db_kind']}   results: {path}\n")
    print(chunk_table(stats), "\n")
    print(markdown_table(runs), "\n")
    st = stage_table(runs)
    if st:
        print(st, "\n")
    print(by_type_table(runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
