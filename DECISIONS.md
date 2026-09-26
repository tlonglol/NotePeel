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

---

## Phase 2: dense retrieval and fusion (2026-09-25 to 26)

Results files: `backend/eval/results/20260926T015642.json` (main run, section chunks,
live latency) and `20260926T015909.json` (fusion parameter sweep, accuracy only).
Same corpus and question set as Phase 1. Latency n: 360 for database-only modes
(72 questions x 5 repeats), 144 for modes that call the embedding API per query
(72 x 2, paced under the rate limit, see D16).

### D15. Embedding model: gemini-embedding-001 truncated to 768 dimensions

- **Chose:** `gemini-embedding-001` with `output_dimensionality=768`, L2-normalized
  client-side, asymmetric task types (RETRIEVAL_DOCUMENT for chunks, RETRIEVAL_QUERY
  for questions). Same API key OCR already uses.
- **Rejected:** the default 3072 dimensions (4x the storage and scan cost; the model is
  trained with Matryoshka representation learning so the truncated prefix keeps most
  of the quality). The 768 vs 1536 comparison is a Phase 4 ablation. A second model
  (Bedrock Titan v2) is a full-version item.
- **Measured:** one query embedding p50 200 ms, p95 338 ms (n=144) from the dev
  machine. Embedding the 189-chunk corpus: 51 batched calls (one per note), 42 s
  including rate-limit retries.

### D16. The API key is on the free tier: 100 embedding requests per minute

- **Found when:** the first latency pass fired 1,080 live embedding calls and hit
  429 with "retry in 35 s" while the retry logic capped its wait at 16 s.
- **Changes:** retries now parse and honor the server's `retryDelay` (cap 45 s, 6
  attempts). Ingestion embeds one batched call per note, not per chunk, which is why
  a 189-chunk corpus costs 51 requests. The harness paces live calls at 90/min, uses
  2 repeats for embedding-backed modes, and caches query embeddings on disk so every
  accuracy pass costs zero API calls (re-running the full Phase 2 accuracy grid made
  7 calls, all for new questions).
- **Production implication:** more than about 100 note uploads per minute would leave
  some notes lexically indexed but un-embedded. That path is handled: the ingest
  result is "partial", the note stays un-hashed, and the next ingest or backfill
  embeds it (D22). Moving to the paid tier is a one-line change and not needed at
  this usage.

### D17. A 30-line vector column type instead of the pgvector Python package

- **Chose:** `app/rag/vector_type.py`: formats a list as the `[...]` text literal on
  the way in and parses it on the way out. Queries cast explicitly with
  `CAST(:q AS vector)`.
- **Rejected:** the `pgvector` package, which depends on numpy (about 25 MB in the
  Lambda bundle) to do the same two conversions. Cost of the choice: `alembic check`
  logs one warning that it cannot reflect the `vector` type; it still detects drift
  on every other column.

### D18. No ANN index: exact cosine scan filtered by owner

- **Chose:** `ORDER BY embedding <=> query` with `WHERE owner_id = :u` and no index.
  The largest user (the eval corpus) has 189 chunks.
- **Rejected:** HNSW at this scale. With an owner filter, HNSW walks the graph first
  and filters after, which can return fewer than k rows or miss the true nearest
  neighbours, and the build cost buys nothing at hundreds of rows.
- **Measured:** vector stage p50 27 ms, p95 66 ms inside the hybrid path (n=144),
  which at this size is mostly the round trip to Neon. Scale test (random unit
  vectors under one owner, timings from the dev machine, `eval/results/scale_test.log`):

  | chunks under one owner | exact scan p50 ms | exact p95 ms | HNSW p50 ms | HNSW build s | HNSW recall@10 vs exact | queries |
  |---|---|---|---|---|---|---|
  | 200 | 39.0 | 39.8 | 20.8 | 0.1 | 1.000 | 20 x 3 repeats |
  | 2,000 | 45.2 | 46.1 | 20.8 | 1.3 | 0.645 | 20 x 3 repeats |
  | 10,000 | 70.4 | 71.3 | 53.2 | 12.6 | 1.000 | 20 x 3 repeats |

  Reading it: the exact scan adds about 30 ms going from 200 to 10,000 chunks per
  user, on top of a round trip that is itself about 20 ms. HNSW saves 17 ms at 10,000
  rows for a 12.6 s index build, and the 0.645 recall at 2,000 rows is the known
  worst case for HNSW: random high-dimensional points have no cluster structure and
  `ef_search=40` is the default, not a tuned value. Real embeddings cluster and would
  score higher, so this row overstates the risk and the timing rows are the point.
  Crossover: an owner would need on the order of 10,000 chunks (about 2,700 notes at
  3.7 chunks each) before an index is worth its build cost and its filtered-recall
  caveat. The largest real user has 4 notes.

  TOAST check (`eval/storage_test.py`): a 768-float vector is ~3 KB, above the 2 KB
  TOAST threshold, and pgvector's default storage for the type is EXTERNAL
  (out-of-line, uncompressed), so each scanned row is fetched from the TOAST
  relation. On the real 189-chunk corpus: EXTERNAL p50 21.0 ms, p95 23.1; PLAIN
  p50 20.6 ms, p95 22.0 (n=300 each). No measurable effect at this size, so no
  storage migration. Side finding: the deleted scale-test rows left 82 MB of TOAST
  bloat until `VACUUM FULL` ran; bulk-deleting vectors needs a vacuum afterwards.

### D19. Vector-only beats the hybrid on this corpus; hybrid ships behind a flag

- **Measured** (section chunks, n=67 headline questions):

  | mode | chunk R@1 | chunk R@5 | chunk MRR@10 | note MRR@10 |
  |---|---|---|---|---|
  | fts_or | 0.694 [0.58, 0.80] | 0.955 [0.90, 0.99] | 0.848 [0.78, 0.91] | 0.908 |
  | vector | 0.918 [0.87, 0.96] | 1.000 [1.00, 1.00] | 0.993 [0.98, 1.00] | 1.000 |
  | hybrid, RRF k=60, equal weights | 0.821 [0.74, 0.90] | 1.000 [1.00, 1.00] | 0.938 [0.90, 0.98] | 0.993 |

  Per question (`python -m eval.compare`): of the 18 questions FTS had below rank 1,
  vector fixed 17 to rank 1 and improved the 18th (q060, rank 5 to 2). Equal-weight
  hybrid fixed 9, improved 4, left 5 unchanged, and pushed 8 questions that vector had
  at rank 1 down to rank 2 or 3.
- **Why fusion hurt:** with k=60 and 20 candidates per list, a chunk ranked first in
  one list alone scores 1/61 = 0.0164, while a chunk ranked 2nd in vector and 20th in
  FTS scores 1/62 + 1/80 = 0.0286. Any chunk present in both top-20 lists outranks
  any chunk present in one, whatever the positions. The lexical list has no IDF (D7),
  so its top entries are often wrong but still overlap vector's top 20, and the
  consensus rule promotes them.
- **Sweep** (`20260926T015909.json`, RRF k in {1, 10, 60} x lexical weight in
  {1.0, 0.5, 0.25}): weight 1.0 hurts at every k (R@1 0.821 to 0.836). Weight 0.5 or
  0.25 at any k ties vector-only exactly (R@1 0.918, MRR 0.993; k=60 w=0.5 MRR 0.990).
  Nothing beats vector-only.
- **Decision:** the ask endpoint defaults to vector-only (`rag_retrieval_mode`).
  Hybrid stays available at lexical weight 0.5 because it is measured harmless and
  because this corpus under-represents the case lexical search exists for: rare exact
  tokens. The single vector regression is that case (q078, the name "Priya", rank 2).
  The lexical list also remains the second candidate source for the Phase 4 reranker.
- **Caveat:** the fusion parameters were chosen on the same 67 questions they are
  reported on. There is no held-out set yet; the real-photo slice will be the first.

### D20. Overlapping the embedding call with the FTS query: measured as noise, default off

- **Measured** (n=144 each): hybrid with overlap p50 237.4 ms, p95 377 ms; sequential
  p50 236.0 ms, p95 414 ms. The stage table shows why: FTS is 20 ms p50 while the
  embedding call is 180 to 200 ms p50 with a p95 of 318 to 338 ms. The most the
  overlap can save is the FTS time, which is smaller than the embedding call's own
  run-to-run variance.
- **Decision:** `overlap=False` by default. The code path stays (six lines and a test)
  so the ablation is reproducible, but the request path is the simpler one. This is
  the "async retrieval" item from the plan, kept in reduced form and then measured
  out.

### D21. Embedding reuse on edit is keyed by chunk content hash

- Re-chunking the unchanged 51-note corpus: 0 API calls, 5.0 s total (vs 47.5 s when
  every chunk was embedded). A one-section edit to a three-chunk note re-embeds one
  chunk (tested). Edits that only change HTML styling are skipped entirely.

### D22. Embedding failure never blocks lexical search

- If the embedding call fails, chunk rows are still written with NULL embeddings,
  lexical search works immediately, vector search skips NULL rows, the note is left
  un-hashed so the next ingest or `scripts/reindex.py` retries, and the result status
  is "partial" (tested end to end with an injected failure).

### D23. Abstain signal for Phase 3: the top-1 cosine score, with a thin margin

- **Measured** on the eval user (cached query embeddings): top-1 cosine for answerable
  questions min 0.622, p25 0.674, median 0.704 (n=67); for the 7 unanswerable
  questions max 0.649, median 0.632. A threshold of 0.65 lets 0 of 7 unanswerable
  questions through and blocks 4 of 67 answerable ones; 0.60 lets 6 of 7 through.
- FTS gives no abstain signal at all: OR semantics matched at least 5 chunks for every
  unanswerable question.
- **Decision for Phase 3:** use 0.65 as a soft gate combined with the generator's own
  "insufficient evidence" flag, and grow the unanswerable set (7 is too few to trust
  a threshold to two decimals).

### D24. Phase 2 code is not deployable until migration 0003 runs in production

- The ORM now selects `note_chunks.embedding`. Production is at revision 0002. A
  lexical-only backfill attempted on 2026-09-25 failed on exactly this and wrote
  nothing. Deploying the Phase 2 Lambda before 0003 would make every chunk read fail
  (uploads would still succeed because ingestion is wrapped, but nothing would be
  indexed). 0003 waits for a new Neon rollback branch per the migration rule.

### Phase 3 targets

q078 (rare token, vector rank 2) and q060 (multi-note, rank 2) are the only
below-rank-1 questions under vector-only. Injection questions retrieve their plant by
design; the Phase 3 guard and generator are measured on whether the answer complies.
Unanswerable set grows from 7 toward 20 before the abstain threshold is trusted.
