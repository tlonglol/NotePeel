"""OCR real photographed pages into eval/corpus/real/*.json through the
production OCR pipeline, so the "real" eval slice has genuine OCR noise.

Drop images into eval/corpus/real/ named  NN_subject_topic-words.jpg
    03_bio_krebs-cycle.jpg           -> one-page note "Krebs Cycle", subject Bio
    07_hist_ww2-causes_p1.jpg        -> multi-page note: same stem, _p1 _p2 ... suffixes
    07_hist_ww2-causes_p2.jpg
Accepted: .jpg .jpeg .png .heic .webp. Title comes from the topic words.

    GEMINI_API_KEY=... python -m eval.ocr_real_pages [--force]

Writes <stem>.json beside the images (raw_text, structured_text, per-page OCR
pass numbers). Existing JSON is kept unless --force. Then add QA pairs for the
new notes to eval/qa.json using the slug (= the JSON stem) as the note id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

REAL_DIR = Path(__file__).resolve().parent / "corpus" / "real"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
SUBJECTS = {
    "bio": "Biology", "chem": "Chemistry", "phys": "Physics", "calc": "Math", "math": "Math",
    "dsa": "Computer Science", "cs": "Computer Science", "stat": "Statistics", "hist": "History",
    "econ": "Economics", "psych": "Psychology", "misc": "General",
}


def group_pages(paths):
    groups = defaultdict(list)
    for p in paths:
        stem = re.sub(r"_p\d+$", "", p.stem)
        groups[stem].append(p)
    for stem in groups:
        groups[stem].sort(key=lambda p: int(re.search(r"_p(\d+)$", p.stem).group(1)) if re.search(r"_p(\d+)$", p.stem) else 0)
    return groups


def title_from_stem(stem: str):
    parts = stem.split("_", 2)
    subject_code = parts[1] if len(parts) > 1 else "misc"
    topic = parts[2] if len(parts) > 2 else stem
    title = topic.replace("-", " ").strip().title()
    return title, SUBJECTS.get(subject_code.lower(), subject_code.title())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--note-type", default="default", choices=["default", "lecture", "meeting"])
    args = ap.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    from app.controllers.note_controller import NoteController, _convert_heic_to_jpeg
    from scripts.note_html import PAGE_DIVIDER

    images = [p for p in sorted(REAL_DIR.iterdir()) if p.suffix.lower() in IMAGE_EXTS]
    if not images:
        print(f"no images in {REAL_DIR}")
        return 0
    groups = group_pages(images)
    for stem, pages in groups.items():
        out = REAL_DIR / f"{stem}.json"
        if out.exists() and not args.force:
            print(f"skip {stem} (json exists)")
            continue
        title, subject = title_from_stem(stem)
        raw_parts, html_parts, passes, failed = [], [], [], []
        for i, page in enumerate(pages, 1):
            content, _ = _convert_heic_to_jpeg(page.read_bytes())
            try:
                raw, html = NoteController._ocr_page_to_html(content, args.note_type)
                raw_parts.append(raw)
                html_parts.append(html)
                passes.append(None)
            except Exception as exc:  # noqa: BLE001
                failed.append(i)
                print(f"  page {i} of {stem} failed: {exc}", file=sys.stderr)
        if not raw_parts:
            print(f"FAILED {stem}: no page produced text")
            continue
        doc = {
            "title": title,
            "subject": subject,
            "topic": "",
            "tags": "",
            "raw_text": "\n\n".join(raw_parts),
            "structured_text": PAGE_DIVIDER.join(html_parts),
            "pages": len(pages),
            "failed_pages": failed,
            "source_files": [p.name for p in pages],
        }
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        words = len(doc["raw_text"].split())
        print(f"wrote {out.name}: {len(pages)} page(s), {words} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
