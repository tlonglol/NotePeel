"""Per-question comparison of two modes from one results file.

    python -m eval.compare eval/results/<file>.json fts_or hybrid [--chunking section]

Lists every question whose first relevant chunk was below rank 1 in mode A,
with its rank in mode B, and flags regressions (rank 1 in A, worse in B).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, Optional

from eval.corpus import load_qa


def first_rank(rec: dict) -> Optional[int]:
    mrr = rec.get("chunk_mrr10")
    if mrr is None:
        return None
    return round(1 / mrr) if mrr > 0 else None   # None = not in top 10


def fmt_rank(r: Optional[int]) -> str:
    return str(r) if r is not None else ">10"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("mode_a")
    ap.add_argument("mode_b")
    ap.add_argument("--chunking", default=None)
    ap.add_argument("--tag", default=None, help="only questions carrying this tag (e.g. hard-v2)")
    args = ap.parse_args(argv)

    d = json.load(open(args.results))
    qa = {q.id: q for q in load_qa()}

    def pick(mode: str) -> dict:
        cands = [r for r in d["runs"]
                 if r["mode"] == mode and (args.chunking is None or r["granularity"] == args.chunking)]
        if not cands:
            sys.exit(f"no run for mode={mode} chunking={args.chunking}")
        return cands[0]

    a, b = pick(args.mode_a), pick(args.mode_b)
    ra: Dict[str, dict] = {r["id"]: r for r in a["questions"] if not args.tag or args.tag in r.get("tags", [])}
    rb: Dict[str, dict] = {r["id"]: r for r in b["questions"] if r["id"] in ra}

    below = [qid for qid, r in ra.items() if first_rank(r) != 1]
    fixed = improved = same = worse = 0
    print(f"{args.mode_a} -> {args.mode_b} ({a['granularity']}): "
          f"questions below rank 1 in {args.mode_a}: {len(below)}\n")
    print(f"| id | type | question | rank {args.mode_a} | rank {args.mode_b} | result |")
    print("|---|---|---|---|---|---|")
    for qid in below:
        fa, fb = first_rank(ra[qid]), first_rank(rb[qid])
        ia = fa if fa is not None else 99
        ib = fb if fb is not None else 99
        if ib == 1:
            res, fixed = "fixed", fixed + 1
        elif ib < ia:
            res, improved = "improved", improved + 1
        elif ib == ia:
            res, same = "same", same + 1
        else:
            res, worse = "worse", worse + 1
        print(f"| {qid} | {ra[qid]['type']} | {qa[qid].question} | {fmt_rank(fa)} | {fmt_rank(fb)} | {res} |")
    print(f"\nfixed to rank 1: {fixed}, improved: {improved}, unchanged: {same}, worse: {worse}")

    regressions = [qid for qid, r in ra.items() if first_rank(r) == 1 and first_rank(rb[qid]) != 1]
    print(f"\nregressions (rank 1 in {args.mode_a}, not in {args.mode_b}): {len(regressions)}")
    for qid in regressions:
        print(f"  {qid}: {qa[qid].question}  -> rank {fmt_rank(first_rank(rb[qid]))} in {args.mode_b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
