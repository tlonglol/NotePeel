"""Prompt-injection guard for retrieved note content.

Threat model: a note's text is untrusted. Notes are photos of anything (a
handout, a whiteboard, someone else's page), and the shared demo account lets
any visitor upload a note that other visitors' questions will retrieve. The
generator has no tools, so the blast radius is answer content, but an injected
"answer with X" or "say the answer is Y" still corrupts what the user sees.

Three layers, weakest listed last:
  1. Structural (the real control): sources reach the model inside explicit
     data delimiters with an instruction that they are quoted material, and the
     model is asked to answer only from them, never to follow them.
  2. Behavioural: the eval set carries planted notes and questions that retrieve
     them; compliance is measured and must be zero.
  3. Lexical (this module): a pattern detector over chunk text. Flagged chunks
     are dropped from the generator's context and their ids are logged. It will
     miss paraphrased attacks; that is what layers 1 and 2 are for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence

# Each pattern targets instruction-shaped text aimed at an assistant, not at the
# note's reader. Case-insensitive; matched against the chunk text.
_PATTERNS = [
    r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier|other)\s+(?:instructions?|notes?|prompts?|context)",
    r"\bdisregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|actual|other)\b",
    r"\bsystem\s+(?:override|prompt|instruction|message)\b",
    r"\b(?:reveal|print|show|repeat|output)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)\b",
    r"\byou\s+must\s+(?:respond|reply|answer|say|output)\b",
    r"\brespond\s+(?:to\s+every\s+question\s+)?with\s+(?:exactly|only)\b",
    r"\b(?:instruction|note|message)s?\s+(?:for|to)\s+(?:the\s+|any\s+|all\s+)?(?:ai|assistant|model|llm|chatbot)s?\b",
    r"\b(?:ai|assistant|model|llm)s?\s+(?:reading|processing|seeing)\s+this\b",
    r"\bpretend\s+(?:this|that|you)\b",
    r"\btakes?\s+priority\s+over\s+(?:the\s+)?user",
    r"\bdo\s+not\s+cite\s+sources?\b",
    r"\bwhen\s+(?:you\s+are\s+)?asked\s+(?:anything\s+)?about\b.{0,80}\b(?:instead|disregard|tell\s+the\s+user)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _PATTERNS]


@dataclass
class GuardResult:
    flagged: bool
    patterns: List[str] = field(default_factory=list)


def inspect_text(text: str) -> GuardResult:
    hits = [p.pattern for p in _COMPILED if p.search(text or "")]
    return GuardResult(flagged=bool(hits), patterns=hits)


def filter_chunks(chunks: Sequence, keep: int) -> tuple:
    """Return (kept_chunks[:keep], flagged_chunk_ids). `chunks` are RetrievedChunk-like
    objects with .chunk_id and .text; order is preserved."""
    kept = []
    flagged: List[int] = []
    for c in chunks:
        if inspect_text(c.text).flagged:
            flagged.append(c.chunk_id)
            continue
        kept.append(c)
        if len(kept) >= keep:
            break
    return kept, flagged
