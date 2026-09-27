"""Write the SSE wire-format fixture the frontend parser test reads.

    python -m scripts.dump_sse_fixture

Frames are produced by app.rag.ask.sse, the same function the endpoint uses, so
the fixture cannot drift from the server's actual framing. Re-run this whenever
the event set or the payload shape changes, and commit the result.
"""
from pathlib import Path

from app.rag.ask import sse

CITATION = {"n": 1, "chunk_id": 9, "note_id": 3, "note_title": "Photosynthesis",
            "page": 1, "heading": "Calvin Cycle", "snippet": "Occurs in the stroma"}

FRAMES = [
    {"event": "sources", "data": {
        "sources": [CITATION], "retrieval_mode": "vector", "top_score": 0.71,
        "gate_triggered": False, "guard_flagged_chunk_ids": [], "timings_ms": {"embed_ms": 201.4}}},
    {"event": "token", "data": {"text": "Rubisco "}},
    {"event": "token", "data": {"text": "fixes CO2 onto RuBP "}},
    {"event": "token", "data": {"text": "in the stroma [1]."}},
    # Newlines, quotes and multi-byte characters inside a payload: these are what
    # break a naive line-oriented or byte-counting parser.
    {"event": "token", "data": {"text": "Multi\nline and \"quoted\" and émoji 🐵 text"}},
    {"event": "done", "data": {"answer": "Rubisco fixes CO2 onto RuBP in the stroma [1].", "abstained": False,
                               "citations": [CITATION], "timings_ms": {"total_ms": 812.3},
                               "query_id": 41, "model": "gemini-2.5-flash"}},
]

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[2] / "frontend" / "test" / "sse_fixture.txt"
    out.write_text("".join(sse(f) for f in FRAMES), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(FRAMES)} frames)")
