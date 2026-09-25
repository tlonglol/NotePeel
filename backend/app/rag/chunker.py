"""Structural chunker for note text.

Input is the note's structured_text: the HTML the OCR layout pass produces and
the rich-text editor edits. It falls back to raw_text (the plain OCR transcript)
when there is no HTML. Output is a list of Chunk records with stable ordinals.

Boundaries, in priority order:
  1. <hr>         -> page break (the multi-page merge inserts one per page)
  2. <h1>..<h4>   -> section heading (the OCR pass emits one <h2> per header)
  3. sentences    -> packed greedily into windows of about `target_tokens`

Sentences are never split. That is what lets the eval harness define ground
truth as short evidence spans: a span inside one sentence always lands whole
inside at least one chunk, whatever the window size.

Token counts are estimated as words * 1.3, which tracks BPE tokenizers on
English prose closely enough to size windows. Nothing here needs the exact
count.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Literal, Optional, Tuple

Granularity = Literal["note", "section", "window"]

HEADING_TAGS = {"h1", "h2", "h3", "h4"}
BLOCK_TAGS = {
    "p", "div", "li", "tr", "blockquote", "pre", "section", "article",
    "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6",
}
_FAILED_PAGE_RE = re.compile(r"\[Page \d+ (?:failed[^\]]*|extraction failed)\]")
_BULLET_PREFIX_RE = re.compile(r"^[◆•▪●○■\-–—*]+\s*")
_EMOJI_PREFIX_RE = re.compile(r"^[\U0001F300-\U0001FAFF☀-➿]+\s*")
_LABELS_RE = re.compile(r"^Labels:\s*", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Tokens that end with a period but do not end a sentence. Handwritten notes are
# often uncapitalized, so the splitter cannot rely on the next word's case.
_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "dr", "mr", "mrs", "ms", "prof", "fig", "eq", "eqn",
    "approx", "ex", "ch", "chap", "pg", "no", "st", "vol", "al", "cf", "def", "thm",
    "sec", "lec", "hw", "p", "pp", "cont", "govt", "dept", "avg", "max", "min",
}
_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")


@dataclass(frozen=True)
class ChunkConfig:
    granularity: Granularity = "window"
    target_tokens: int = 200      # close a window once it reaches this
    max_tokens: int = 320         # never exceed this unless a single sentence does
    overlap_sentences: int = 1    # sentences carried into the next window
    min_tail_tokens: int = 40     # a trailing window smaller than this merges backward

    def signature(self) -> str:
        return (
            f"{self.granularity}:{self.target_tokens}:{self.max_tokens}:"
            f"{self.overlap_sentences}:{self.min_tail_tokens}"
        )


DEFAULT_CONFIG = ChunkConfig()


@dataclass
class Chunk:
    ordinal: int
    page: int
    heading: Optional[str]
    text: str
    token_estimate: int
    content_hash: str


@dataclass
class Block:
    kind: Literal["heading", "text", "page_break"]
    text: str = ""


# ── text extraction ─────────────────────────────────────────────────────────

def _clean_line(line: str) -> str:
    line = _FAILED_PAGE_RE.sub("", line)
    line = _WS_RE.sub(" ", line).strip()
    line = _BULLET_PREFIX_RE.sub("", line)
    line = _EMOJI_PREFIX_RE.sub("", line)
    line = _LABELS_RE.sub("Labels: ", line)
    if not re.search(r"[A-Za-z0-9]", line):
        return ""
    return line


class _BlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: List[Block] = []
        self._buf: List[str] = []
        self._heading_depth = 0
        self._heading_buf: List[str] = []

    def _flush_text(self) -> None:
        raw = "".join(self._buf)
        self._buf = []
        for line in raw.split("\n"):
            line = _clean_line(line)
            if line:
                self.blocks.append(Block("text", line))

    def handle_starttag(self, tag, attrs):
        if tag == "hr":
            self._flush_text()
            self.blocks.append(Block("page_break"))
        elif tag in HEADING_TAGS:
            self._flush_text()
            self._heading_depth += 1
        elif tag == "br":
            (self._heading_buf if self._heading_depth else self._buf).append("\n")
        elif tag in BLOCK_TAGS:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag in HEADING_TAGS and self._heading_depth:
            self._heading_depth -= 1
            text = _clean_line("".join(self._heading_buf))
            self._heading_buf = []
            if text:
                self.blocks.append(Block("heading", text))
        elif tag in BLOCK_TAGS:
            self._buf.append("\n")

    def handle_data(self, data):
        (self._heading_buf if self._heading_depth else self._buf).append(data)

    def close(self):
        super().close()
        self._flush_text()


def looks_like_html(text: Optional[str]) -> bool:
    return bool(text) and _TAG_RE.search(text) is not None


def html_to_blocks(html: str) -> List[Block]:
    parser = _BlockParser()
    parser.feed(html)
    parser.close()
    return _drop_leading_and_double_breaks(parser.blocks)


def plain_to_blocks(text: str) -> List[Block]:
    blocks: List[Block] = []
    for line in (text or "").split("\n"):
        line = _clean_line(line)
        if line:
            blocks.append(Block("text", line))
    return blocks


def _drop_leading_and_double_breaks(blocks: List[Block]) -> List[Block]:
    out: List[Block] = []
    for b in blocks:
        if b.kind == "page_break" and (not out or out[-1].kind == "page_break"):
            continue
        out.append(b)
    while out and out[-1].kind == "page_break":
        out.pop()
    return out


def note_blocks(structured_text: Optional[str], raw_text: Optional[str]) -> Tuple[List[Block], str]:
    """Pick the source text for a note. Returns (blocks, source_name)."""
    if looks_like_html(structured_text):
        blocks = html_to_blocks(structured_text or "")
        if blocks:
            return blocks, "structured_text"
    if structured_text and structured_text.strip():
        blocks = plain_to_blocks(structured_text)
        if blocks:
            return blocks, "structured_text"
    return plain_to_blocks(raw_text or ""), "raw_text"


def extract_plain_text(structured_text: Optional[str], raw_text: Optional[str]) -> str:
    """Flat text of a note as the chunker sees it (headings included). Used by the
    eval harness to validate that evidence spans exist verbatim."""
    blocks, _ = note_blocks(structured_text, raw_text)
    return "\n".join(b.text for b in blocks if b.kind != "page_break")


# ── sentences and packing ───────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


def _ends_with_abbreviation(piece: str) -> bool:
    last = piece.rsplit(None, 1)[-1] if piece.strip() else ""
    if not last.endswith("."):
        return False
    core = last[:-1].lower().strip("(\"'")
    if core in _ABBREVIATIONS:
        return True
    if len(core) == 1 and core.isalpha():      # initials: "J. Smith"
        return True
    if core.isdigit():                          # enumerations: "1. Nucleus"
        return True
    return False


def split_sentences(line: str) -> List[str]:
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(line) if p.strip()]
    merged: List[str] = []
    for p in parts:
        if merged and (merged[-1].count("$") % 2 == 1 or _ends_with_abbreviation(merged[-1])):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def _tok(sentences: List[str]) -> int:
    return sum(estimate_tokens(s) for s in sentences)


def pack_windows(sentences: List[str], cfg: ChunkConfig) -> List[List[str]]:
    """Greedy packing with sentence overlap. Never splits a sentence."""
    windows: List[List[str]] = []
    cur: List[str] = []
    fresh = 0  # sentences in `cur` that were not carried over as overlap

    def close() -> None:
        nonlocal cur, fresh
        windows.append(cur)
        carry = cur[-cfg.overlap_sentences:] if cfg.overlap_sentences > 0 else []
        cur, fresh = list(carry), 0

    for s in sentences:
        if fresh and _tok(cur) + estimate_tokens(s) > cfg.max_tokens:
            close()
        cur.append(s)
        fresh += 1
        if _tok(cur) >= cfg.target_tokens:
            close()
    if fresh:
        windows.append(cur)

    if len(windows) >= 2 and _tok(windows[-1]) < cfg.min_tail_tokens:
        merged = windows[-2] + [s for s in windows[-1] if s not in windows[-2]]
        if _tok(merged) <= cfg.max_tokens:
            windows[-2:] = [merged]
    return windows


@dataclass
class _Section:
    page: int
    heading: Optional[str]
    sentences: List[str]


def _sections(blocks: List[Block]) -> List[_Section]:
    sections: List[_Section] = []
    page = 1
    cur = _Section(page, None, [])
    for b in blocks:
        if b.kind == "page_break":
            if cur.sentences:
                sections.append(cur)
            page += 1
            cur = _Section(page, None, [])
        elif b.kind == "heading":
            if cur.sentences:
                sections.append(cur)
            cur = _Section(page, b.text, [])
        else:
            sents = split_sentences(b.text)
            if sents:
                sents[-1] = sents[-1] + "\n"   # keep the line boundary for display
                cur.sentences.extend(sents)
    if cur.sentences:
        sections.append(cur)
    return sections


def _join_sentences(sentences: List[str]) -> str:
    """Join sentences with spaces, honouring the line-break markers left by
    _sections so bullet lists stay one item per line."""
    out = " ".join(sentences)
    out = re.sub(r"[ \t]*\n[ \t]*", "\n", out)
    return out.strip()


def content_hash(heading: Optional[str], text: str) -> str:
    return hashlib.sha256(f"{heading or ''}\x1f{text}".encode("utf-8")).hexdigest()


def note_content_hash(
    title: Optional[str],
    structured_text: Optional[str],
    raw_text: Optional[str],
    cfg: ChunkConfig,
) -> str:
    """Hash of everything that influences the chunk rows: title (it feeds
    `context`), the extracted blocks, and the chunker config."""
    blocks, source = note_blocks(structured_text, raw_text)
    flat = "\n".join(f"{b.kind}:{b.text}" for b in blocks)
    payload = f"{title or ''}\x1f{source}\x1f{cfg.signature()}\x1f{flat}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── public entry point ──────────────────────────────────────────────────────

def chunk_note(
    structured_text: Optional[str],
    raw_text: Optional[str],
    cfg: ChunkConfig = DEFAULT_CONFIG,
) -> List[Chunk]:
    blocks, _ = note_blocks(structured_text, raw_text)
    sections = _sections(blocks)
    if not sections:
        return []

    chunks: List[Chunk] = []

    def emit(page: int, heading: Optional[str], sentences: List[str]) -> None:
        text = _join_sentences(sentences)
        if not text:
            return
        chunks.append(Chunk(
            ordinal=len(chunks),
            page=page,
            heading=heading,
            text=text,
            token_estimate=estimate_tokens(text),
            content_hash=content_hash(heading, text),
        ))

    if cfg.granularity == "note":
        parts: List[str] = []
        for s in sections:
            if s.heading:
                parts.append(s.heading + ".")
            parts.extend(s.sentences)
        emit(sections[0].page, None, parts)
        return chunks

    for s in sections:
        if cfg.granularity == "section" and _tok(s.sentences) <= cfg.max_tokens:
            emit(s.page, s.heading, s.sentences)
            continue
        for window in pack_windows(s.sentences, cfg):
            emit(s.page, s.heading, window)
    return chunks


def build_context(title: Optional[str], heading: Optional[str]) -> str:
    """The 'title > heading' breadcrumb stored beside each chunk and prepended
    for lexical and vector search."""
    parts = [p.strip() for p in (title, heading) if p and p.strip()]
    return " > ".join(parts)[:600]
