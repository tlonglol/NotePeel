"""Eval corpus loader.

Notes live in eval/corpus/notes/<slug>.md with a small front-matter block and a
markdown-subset body:

    ---
    title: Photosynthesis
    subject: Biology
    topic: Plant Biology
    tags: photosynthesis, chloroplast
    adversarial: false        # true = prompt-injection plant; never seeded into the demo
    ---
    ## Section heading
    Paragraph text. Another sentence.

    - bullet item
    - bullet item

    ===PAGE===                (page break: becomes the <hr> the multi-page merge emits)

Each note is rendered two ways, mirroring what the OCR pipeline stores:
  structured_text  -> HTML via scripts/note_html (h2 / p / ◆ bullets / hr)
  raw_text         -> plain transcript in reading order

Real photographed notes, once OCR'd, land in eval/corpus/real/*.json with the
same fields (see eval/ocr_real_pages.py) and are loaded alongside.

QA pairs live in eval/qa.json. Evidence spans must be verbatim substrings of
the note (whitespace/case-insensitive) and fit inside one sentence, which the
loader validates so ground truth can never silently rot.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts.note_html import PAGE_DIVIDER, bullets, h, p

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
NOTES_DIR = CORPUS_DIR / "notes"
REAL_DIR = CORPUS_DIR / "real"
QA_PATH = Path(__file__).resolve().parent / "qa.json"


@dataclass
class CorpusNote:
    slug: str
    title: str
    subject: str
    topic: str
    tags: str
    raw_text: str
    structured_text: str
    adversarial: bool = False
    source: str = "synthetic"   # "synthetic" | "real"


@dataclass
class Evidence:
    note: str      # slug
    span: str      # verbatim substring of that note's text


@dataclass
class QAItem:
    id: str
    type: str                       # single | multi | unanswerable | injection
    question: str
    notes: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    answer: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @property
    def answerable(self) -> bool:
        """Has ground-truth evidence to retrieve. Injection questions do too: the
        plant note also carries the legitimate answer, and Phase 3 checks the
        answer ignores the injected instruction."""
        return self.type in ("single", "multi", "injection")

    @property
    def headline(self) -> bool:
        """Counts toward the headline retrieval numbers (injection is reported separately)."""
        return self.type in ("single", "multi")


# ── markdown subset -> (raw_text, structured_text) ──────────────────────────

def _parse_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("missing front matter")
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.split("#", 1)[0].strip()
    return meta, m.group(2)


def render_body(body: str) -> tuple[str, str]:
    """Return (raw_text, structured_html) for a markdown-subset body."""
    raw_lines: List[str] = []
    html_parts: List[str] = []
    pending_bullets: List[str] = []
    pending_para: List[str] = []

    def flush() -> None:
        nonlocal pending_bullets, pending_para
        if pending_para:
            para = " ".join(pending_para)
            html_parts.append(p(para))
            raw_lines.append(para)
            pending_para = []
        if pending_bullets:
            html_parts.append(bullets(pending_bullets))
            raw_lines.extend(pending_bullets)
            pending_bullets = []

    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "===PAGE===":
            flush()
            html_parts.append(PAGE_DIVIDER)
            raw_lines.append("")
        elif stripped.startswith("## "):
            flush()
            heading = stripped[3:].strip()
            html_parts.append(h(heading))
            raw_lines.append(heading)
        elif stripped.startswith("- "):
            if pending_para:
                flush()
            pending_bullets.append(stripped[2:].strip())
        elif not stripped:
            flush()
        else:
            if pending_bullets:
                flush()
            pending_para.append(stripped)
    flush()
    return "\n".join(raw_lines).strip(), "".join(html_parts)


def load_synthetic_notes(notes_dir: Path = NOTES_DIR) -> List[CorpusNote]:
    notes: List[CorpusNote] = []
    for path in sorted(notes_dir.glob("*.md")):
        meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        raw, html = render_body(body)
        notes.append(CorpusNote(
            slug=path.stem,
            title=meta["title"],
            subject=meta.get("subject", ""),
            topic=meta.get("topic", ""),
            tags=meta.get("tags", ""),
            raw_text=raw,
            structured_text=html,
            adversarial=meta.get("adversarial", "false").lower() == "true",
            source="synthetic",
        ))
    return notes


def load_real_notes(real_dir: Path = REAL_DIR) -> List[CorpusNote]:
    notes: List[CorpusNote] = []
    for path in sorted(real_dir.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        notes.append(CorpusNote(
            slug=path.stem, title=d["title"], subject=d.get("subject", ""),
            topic=d.get("topic", ""), tags=d.get("tags", ""),
            raw_text=d.get("raw_text", ""), structured_text=d.get("structured_text", ""),
            adversarial=False, source="real",
        ))
    return notes


def load_notes(include_real: bool = True, include_adversarial: bool = True) -> List[CorpusNote]:
    notes = load_synthetic_notes()
    if include_real:
        notes += load_real_notes()
    if not include_adversarial:
        notes = [n for n in notes if not n.adversarial]
    slugs = [n.slug for n in notes]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise ValueError(f"duplicate slugs: {sorted(dupes)}")
    return notes


def load_qa(path: Path = QA_PATH) -> List[QAItem]:
    items = json.loads(path.read_text(encoding="utf-8"))
    out: List[QAItem] = []
    for d in items:
        out.append(QAItem(
            id=d["id"], type=d["type"], question=d["question"],
            notes=d.get("notes", []),
            evidence=[Evidence(**e) for e in d.get("evidence", [])],
            answer=d.get("answer"), tags=d.get("tags", []),
        ))
    ids = [q.id for q in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate QA ids")
    return out


# ── validation ──────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def validate(notes: List[CorpusNote], qa: List[QAItem]) -> List[str]:
    """Return a list of problems (empty = valid). Checks slugs resolve and every
    evidence span is found whole inside one chunk under every granularity."""
    from app.rag.chunker import ChunkConfig, chunk_note

    by_slug: Dict[str, CorpusNote] = {n.slug: n for n in notes}
    problems: List[str] = []
    cfgs = [ChunkConfig(granularity=g) for g in ("window", "section", "note")]
    chunk_cache: Dict[tuple, List[str]] = {}

    for q in qa:
        if q.type not in ("single", "multi", "unanswerable", "injection"):
            problems.append(f"{q.id}: unknown type {q.type}")
        if q.answerable and not q.evidence:
            problems.append(f"{q.id}: answerable but no evidence")
        if q.type == "multi" and len(set(q.notes)) < 2:
            problems.append(f"{q.id}: multi question must span at least two notes")
        if q.type == "single" and len(set(q.notes)) != 1:
            problems.append(f"{q.id}: single question must reference exactly one note")
        if not q.answerable and (q.notes or q.evidence):
            problems.append(f"{q.id}: {q.type} question must not list notes/evidence")
        for slug in q.notes:
            if slug not in by_slug:
                problems.append(f"{q.id}: unknown note {slug}")
        for ev in q.evidence:
            if ev.note not in by_slug:
                problems.append(f"{q.id}: evidence references unknown note {ev.note}")
                continue
            if ev.note not in q.notes:
                problems.append(f"{q.id}: evidence note {ev.note} not in notes list")
            n = by_slug[ev.note]
            for cfg in cfgs:
                key = (ev.note, cfg.granularity)
                if key not in chunk_cache:
                    chunk_cache[key] = [norm(c.text) for c in chunk_note(n.structured_text, n.raw_text, cfg)]
                if not any(norm(ev.span) in t for t in chunk_cache[key]):
                    problems.append(f"{q.id}: span not inside any {cfg.granularity} chunk of {ev.note}: {ev.span!r}")
    return problems
