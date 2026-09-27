"""Measure whether the LLM judge agrees with a human.

    python -m eval.judge_audit <results.json>            # show unlabelled answers to label
    python -m eval.judge_audit <results.json> --report   # agreement on already-labelled answers

Hand labels live in eval/judge_labels.json, keyed by question id plus a hash of
the exact answer text, so a label is never silently reused for a different
answer (change the model, and its answers show up as unlabelled again).

This exists because the judge's `matches_reference` verdict was measurably
miscalibrated on the first run: it marked "In metaphase, chromosomes line up at
the metaphase plate" as not matching the reference "Metaphase." Faithfulness
and correctness are only trustworthy to the extent this audit says they are.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict

from eval.corpus import load_qa

LABELS_PATH = Path(__file__).resolve().parent / "judge_labels.json"
VERDICTS = ("yes", "partial", "no")


def answer_key(qid: str, answer: str) -> str:
    return f"{qid}:{hashlib.sha256((answer or '').strip().encode()).hexdigest()[:12]}"


def load_labels() -> Dict[str, dict]:
    return json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)

    d = json.load(open(args.results))
    qa = {q.id: q for q in load_qa()}
    labels = load_labels()
    answered = [q for q in d["questions"]
                if not q.get("error") and q["type"] in ("single", "multi") and not q["abstained"] and q.get("judge")]

    rows, unlabelled = [], []
    for q in answered:
        k = answer_key(q["id"], q["answer"])
        if k in labels:
            rows.append((q, labels[k]))
        else:
            unlabelled.append((q, k))

    if not args.report:
        print(f"{len(rows)} labelled, {len(unlabelled)} unlabelled of {len(answered)} answered\n")
        for q, k in unlabelled:
            print(f'  "{k}": {{"matches_reference": "?", "faithful": true, "note": ""}},')
            print(f"      # Q:   {q['question']}")
            print(f"      # ref: {qa[q['id']].answer}")
            print(f"      # got: {q['answer']}")
            print(f"      # judge said: {q['judge']['matches_reference']}, faith={q.get('faithfulness')}")
        return 0

    if not rows:
        sys.exit("no labelled answers in this results file; run without --report first")
    agree = sum(1 for q, lab in rows if q["judge"]["matches_reference"] == lab["matches_reference"])
    judge_correct = sum(1 for q, _ in rows if q["judge"]["matches_reference"] == "yes")
    human_correct = sum(1 for _, lab in rows if lab["matches_reference"] == "yes")
    faith_agree = sum(1 for q, lab in rows if (q.get("faithfulness") == 1.0) == bool(lab.get("faithful", True)))
    print(f"labelled answers: {len(rows)}")
    print(f"| metric | judge | human | agreement |")
    print(f"|---|---|---|---|")
    print(f"| correct (matches_reference = yes) | {judge_correct / len(rows):.3f} | {human_correct / len(rows):.3f} "
          f"| {agree / len(rows):.3f} |")
    print(f"| faithful (all claims supported) | "
          f"{sum(1 for q, _ in rows if q.get('faithfulness') == 1.0) / len(rows):.3f} | "
          f"{sum(1 for _, lab in rows if lab.get('faithful', True)) / len(rows):.3f} | {faith_agree / len(rows):.3f} |")
    print("\ndisagreements (judge verdict vs human):")
    for q, lab in rows:
        if q["judge"]["matches_reference"] != lab["matches_reference"]:
            print(f"  {q['id']}: judge={q['judge']['matches_reference']} human={lab['matches_reference']}"
                  f"{' — ' + lab['note'] if lab.get('note') else ''}")
            print(f"     Q: {q['question']}")
            print(f"     A: {q['answer'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
