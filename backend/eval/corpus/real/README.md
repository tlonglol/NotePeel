# Real photographed notes

Drop photos of your handwritten pages here, named `NN_subject_topic-words.jpg`
(`03_bio_krebs-cycle.jpg`; multi-page: `07_hist_ww2-causes_p1.jpg`, `_p2.jpg`, ...).
Subject codes: bio, chem, phys, calc, dsa, stat, hist, econ, psych, misc.
Formats: jpg, jpeg, png, heic, webp.

Then run `python -m eval.ocr_real_pages` from `backend/` (needs GEMINI_API_KEY).
It writes one JSON per note through the production OCR pipeline. Images are
gitignored; the JSON transcripts are committed and loaded by the eval harness.
Add QA pairs for each new note to `eval/qa.json` using the JSON stem as the slug.
