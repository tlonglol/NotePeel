"""Text embeddings via Gemini (`gemini-embedding-001`), the same key OCR uses.

Design points (see DECISIONS.md):
  * 768 dimensions via `output_dimensionality`. gemini-embedding-001 is trained
    with Matryoshka representation learning, so truncating the 3072-d vector
    keeps most of its quality at a quarter of the storage. Truncated vectors
    are not unit length, so they are L2-normalized here before storage; every
    stored vector and every query vector is therefore comparable by cosine.
  * Asymmetric task types: RETRIEVAL_DOCUMENT for chunks, RETRIEVAL_QUERY for
    questions. The model is trained for that pairing.
  * Batched calls with exponential backoff on 429/5xx, because ingestion of a
    multi-page note embeds all its chunks at once.
  * The client is lazy so importing this module never needs the API key.
"""
from __future__ import annotations

import logging
import math
import os
import re
import time
from typing import List, Optional, Sequence

from app.config import get_settings

log = logging.getLogger("notepeel.rag.embeddings")

BATCH_SIZE = 50
MAX_RETRIES = 6
MAX_RETRY_WAIT_S = 45.0   # the free tier (100 requests/min) asks for waits of up to ~40 s

_client = None


class EmbeddingError(RuntimeError):
    pass


def model_tag() -> str:
    s = get_settings()
    return f"{s.rag_embedding_model}@{s.rag_embedding_dims}"


def _get_client():
    global _client
    if _client is None:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
        if not key:
            raise EmbeddingError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=key)
    return _client


def l2_normalize(v: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0.0:
        return list(v)
    return [x / norm for x in v]


_RETRY_DELAY_RE = re.compile(r"retry(?:Delay|\s+in)['\":\s]*([0-9.]+)\s*s", re.IGNORECASE)


def suggested_delay(exc: Exception) -> Optional[float]:
    """Seconds the API asked us to wait, parsed from a 429 body
    ("Please retry in 35.2s" / "'retryDelay': '35s'"), else None."""
    m = _RETRY_DELAY_RE.search(str(exc))
    return float(m.group(1)) if m else None


def _is_retryable(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    msg = str(exc)
    return any(t in msg for t in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "deadline", "overloaded"))


def _embed_batch(texts: List[str], task_type: str) -> List[List[float]]:
    from google.genai import types
    s = get_settings()
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            resp = _get_client().models.embed_content(
                model=s.rag_embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=s.rag_embedding_dims,
                ),
            )
            vectors = [l2_normalize(e.values) for e in resp.embeddings]
            if len(vectors) != len(texts):
                raise EmbeddingError(f"expected {len(texts)} embeddings, got {len(vectors)}")
            return vectors
        except Exception as exc:  # noqa: BLE001
            if attempt < MAX_RETRIES - 1 and _is_retryable(exc):
                wait = suggested_delay(exc)
                wait = min(MAX_RETRY_WAIT_S, (wait + 1.0) if wait is not None else delay)
                log.warning("embedding retry %d in %.1fs after: %s", attempt + 1, wait, str(exc)[:160])
                time.sleep(wait)
                delay = min(delay * 2, 16.0)
                continue
            raise EmbeddingError(str(exc)) from exc
    raise EmbeddingError("unreachable")


def embed_documents(texts: Sequence[str]) -> List[List[float]]:
    """Embed chunk texts (RETRIEVAL_DOCUMENT), batched, order preserved."""
    out: List[List[float]] = []
    texts = list(texts)
    for i in range(0, len(texts), BATCH_SIZE):
        out.extend(_embed_batch(texts[i:i + BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
    return out


def embed_query(text: str) -> List[float]:
    """Embed a question (RETRIEVAL_QUERY)."""
    return _embed_batch([text], "RETRIEVAL_QUERY")[0]


def embedding_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def reset_client_for_tests(client: Optional[object]) -> None:
    global _client
    _client = client
