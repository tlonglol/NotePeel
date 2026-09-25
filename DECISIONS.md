# DECISIONS.md

Every choice between alternatives in the retrieval system, with what was rejected,
why, and the measured effect when there is one. Numbers cite the eval results file
they come from (`backend/eval/results/<timestamp>.json`). n is stated for every number.

Conventions: `chunk R@k` = fraction of a question's evidence spans covered by a chunk in
the top k. `note R@k` = fraction of expected notes in the top k distinct notes.
`MRR@10` = 1 / rank of the first hit. CIs are 95% percentile bootstrap over questions.

---

## Phase 1: eval foundation and lexical baselines (2026-09-10)

Results file: `backend/eval/results/20260910T211535.json`. Corpus: 51 notes (49 subject
notes across 8 subjects, 2 adversarial plants), 79 questions (58 single-note, 9
multi-note, 7 unanswerable, 5 injection). Headline numbers use the 67 single + multi
questions. Database: Neon (pooled), queried from a dev machine.

### D1. Ground truth is evidence spans, not chunk ids

- **Chose:** each answerable question lists verbatim spans of note text (whitespace and
  case insensitive). A retrieved chunk is a hit if it contains the span. The loader
  validates every span sits inside one chunk under every chunker config, or the eval
  refuses to run.
- **Rejected:** chunk ids as ground truth (invalidated by any chunker change); note ids
  only (cannot grade chunking or a generator's context window).
- **Effect:** the same 79-question set graded five chunk configurations with zero
  relabeling. The validation caught nothing on the first run, which means the spans were
  authored carefully, not that the check is unnecessary: it is what lets the QA file be
  edited safely later.

### D2. A built eval corpus instead of production notes

- **Chose:** 49 synthetic notes written in OCR style (h2 sections, bullet rows, LaTeX,
  uncapitalized handwriting-style text, abbreviations like w/ and b/c), six per subject,
  with deliberate near-duplicate pairs as hard negatives (mitosis vs meiosis,
  photosynthesis vs respiration, WWI vs WWII causes, hypothesis tests vs confidence
  intervals, product rule vs integration by parts). Plus a slice of real photographed
  pages once they are supplied (`backend/eval/corpus/real/`).
- **Rejected:** evaluating over the production database. It held 4 notes, 3 of them demo
  seeds, averaging 349 characters. Any method scores 1.0 on that.
- **Honest limitation:** on this corpus OR-semantics FTS already reaches 0.955 chunk R@5
  and 1.000 note R@5 (n=67). The corpus is discriminating at rank 1 and in MRR (18 of 67
  questions have their first hit below rank 1), not at recall@5. Phase 2 will be judged
  on R@1, MRR, and those 18 questions, and the real-photo slice is expected to be harder.

### D3. Index the text the user sees, not the OCR transcript

- **Chose:** chunk from `structured_text` (the HTML the OCR layout pass produces and the
  editor edits), falling back to `raw_text`.
- **Rejected:** `raw_text`, which the existing flashcard, summary, and explain features
  read.
- **Why:** the editor writes only `structured_text`. Found during code review: the
  existing AI features silently ignore every user edit. Retrieval must not repeat that.
  (The other features still have the bug; not in scope.)

### D4. Chunk boundaries and size

- **Chose:** `<hr>` page dividers, then `<h1>`..`<h4>` headings, then sentences packed
  greedily into windows (default target 200 / max 320 tokens, one-sentence overlap).
  Sentences are never split. Title and heading are stored as a `context` breadcrumb and
  prepended for search.
- **Rejected:** fixed character windows (cut sentences, break the span-based ground
  truth); whole-note retrieval as the default (see numbers).
- **Measured** (fts_or, n=67 questions, latency n=360):

  | chunking | chunks | tokens p50 / p95 | chunk R@1 | chunk R@5 | MRR@10 | ctx tokens in top 5 |
  |---|---|---|---|---|---|---|
  | section (= default window) | 189 | 52 / 96 | 0.694 | 0.955 | 0.848 | 293 |
  | window 60/100 | 217 | 49 / 74 | 0.702 | 0.955 | 0.844 | 266 |
  | window 120/200 | 189 | 52 / 96 | 0.694 | 0.955 | 0.848 | 293 |
  | note | 51 | 212 / 273 | 0.769 | 1.000 | 0.900 | 990 |

  Findings: (1) at this note length no section exceeds 320 tokens, so "window" and
  "section" produce identical chunks; the window machinery only matters for longer
  pages. (2) Shrinking windows to 60/100 changes nothing outside the CIs. (3) Whole-note
  chunks score higher because the hit criterion becomes "found the note", but they cost
  3.4x the context tokens per answer (990 vs 293). Since the generator's context budget
  and citation precision are what matter downstream, section-sized chunks stay the
  default. Revisit when the real-photo slice (longer pages) arrives.

### D5. Postgres FTS query semantics: OR, not AND

- **Chose:** OR of stemmed terms (`plainto_tsquery` text form with `&` rewritten to
  `|`, cast with `::tsquery` so lexemes are not stemmed twice), ranked by `ts_rank_cd`.
- **Rejected:** `websearch_to_tsquery` (AND semantics).
- **Measured** (section chunks, n=67): AND chunk R@5 0.164 [0.09, 0.25], OR 0.955
  [0.90, 0.99]. AND returned zero rows for 59 of 72 answerable questions: a natural
  language question carries incidental non-stopwords ("phase", "middle", "line up")
  that all have to appear in one chunk.

### D6. The legacy search is the baseline, and it scores zero

- **Measured:** the shipped `ILIKE '%query%'` search over whole notes, ordered by
  recency: note R@5 0.000 (n=67). A question is never a substring of a note. It is kept
  in the harness as baseline zero because it is what the product shipped with, not as a
  straw man: the same function, called directly.

### D7. Known ranking flaw in `ts_rank_cd`: no inverse document frequency

- **Observed:** q022 "Why do airbags reduce injuries in a crash?" ranks the momentum
  note 6th. The Great Depression note ("stock market crash") and others match the
  common terms "reduce" and "crash"; the rare, decisive term "airbag" carries no extra
  weight because Postgres ranking uses no corpus-level statistics. Same pattern for
  q079 ("take place" and "cell" pull in three cell-biology notes above the
  photosynthesis note, and the adversarial meeting note that mentions photosynthesis
  reaches rank 4).
- **Options:** BM25 via Neon's `pg_search` extension (has IDF; not available in the CI
  container or local Postgres), or fusing with vector retrieval. Decision: keep
  `tsvector` for portability and let Phase 2 hybrid retrieval be measured against
  exactly these questions. If hybrid does not fix them, BM25 becomes an ablation.

### D8. Ingestion replaces a note's chunks wholesale, idempotently

- **Chose:** per-note `index_hash` over (title, extracted text blocks, chunker config).
  Unchanged hash: skip. Changed: bulk DELETE, flush, INSERT in one transaction. Each
  chunk carries a `content_hash` so Phase 2 can reuse embeddings for unchanged chunks.
- **Rejected:** diffing chunk rows in place (ordinals stop being dense and the
  `(note_id, ordinal)` unique constraint fights the ORM's insert-before-delete order).
- **Measured:** style-only HTML edits are skipped (tested); a one-section edit to a
  three-chunk note reports 2 reusable chunks (tested). Re-indexing all 51 corpus notes
  on Neon: see D9.

### D9. Indexing runs inline in the upload path, and never fails an upload

- **Chose:** `safe_ingest` after the OCR commit, same never-raise rule as
  auto-categorize; a failure logs and rolls back its own work.
- **Rejected:** a queue. The upload request already runs up to three synchronous Gemini
  vision calls.
- **Measured** (Neon from a dev machine, includes network round trips): forced
  re-index of all 51 corpus notes took 4.4 s total, per-note p50 83.9 ms, p95 88.9 ms,
  max 94.2 ms (n=51). The unchanged path (hash comparison, no writes) took 1.2 s for
  51 notes, about 23 ms each, which is one round trip. Next to an OCR step measured in
  tens of seconds this does not justify a queue. Embedding cost joins this number in
  Phase 2.

### D10. Alembic from the first schema change

- **Chose:** Alembic with a baseline revision (`0001_baseline`) that existing databases
  are stamped with, never run through; fresh databases run it for real. `migrate.py`
  refuses to run against a database that has the app schema but no `alembic_version`.
- **Rejected:** continuing `create_all()` plus hand-written column repairs; adding
  Alembic later (would mean writing the chunk migration twice).
- **Verified:** upgrading an empty database to `0001_baseline` produced a schema dump
  identical to production, all 121 lines (columns, indexes, constraints, enum, FK
  delete rules). `alembic check` reports no drift after `0002_note_chunks`.

### D11. Tests hit a real Postgres

- **Chose:** unit tests with no database for the chunker and metrics; integration
  tests against a real Postgres (Neon `notepeel_test` locally, `pgvector/pgvector:pg16`
  service container in CI). CI previously ran no tests at all.
- **Rejected:** SQLite (no `tsvector`, no generated columns); mocking the session
  (the existing test suite does this and cannot catch a wrong SQL query).

### D12. What the latency numbers mean

- p50 of 20 to 22 ms for every mode including ILIKE (n=360 per row: 72 questions x 5
  repeats) says the number is the round trip from this machine to Neon, not query work.
  p99 outliers up to 137 ms are single network hiccups. In-region numbers come from the
  Phase 3 query log running inside Lambda.

### D13. Sentence splitting cannot rely on capitalization

- Found by a failing unit test: the first splitter only split before capital letters,
  and handwritten notes are mostly uncapitalized. Now splits on `.`/`!`/`?` plus
  whitespace with an abbreviation and enumeration guard ("e.g.", "fig.", "1.").

### D14. Injection plants are in the corpus from day one

- Two adversarial notes (one instructing the assistant to answer "PWNED", one telling it
  to claim photosynthesis happens in the mitochondria) are part of the eval set. Under
  OR-FTS the meeting plant already reaches rank 4 for the photosynthesis question, so
  the Phase 3 guard has a concrete retrieval path to defend against, not a hypothetical.

### Phase 2 targets

The 18 questions whose first hit is below rank 1 under fts_or, and the 5 with chunk
R@5 below 1 (q022, q046, q060, q064, q079). q046 is a pure vocabulary gap
("quadrupling" vs "4x", "margin of error" vs "ME"); q022 and q079 are the IDF flaw.
