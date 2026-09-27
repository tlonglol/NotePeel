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

---

## Phase 2b: expanding the question set (2026-09-26)

Results file: `backend/eval/results/20260926T194539.json`. Question set grew from 79
to 113: 24 harder answerable questions tagged `hard-v2` (7 rare names and terms, 5
abbreviations absent from the notes, 4 typos, 8 vague or sharply reworded) and 10
more near-miss unanswerable questions (17 total). Headline n is now 91.

### D25. The harder questions broke lexical search and did not touch vector search

- **Measured** (section chunks, accuracy only):

  | mode | chunk R@1 | chunk R@5 | MRR@10 | hard-v2 R@1 (n=24) | v1 R@1 (n=72) |
  |---|---|---|---|---|---|
  | fts_or | 0.632 [0.54, 0.71] | 0.890 [0.82, 0.95] | 0.771 | 0.458 | 0.701 |
  | vector | 0.940 [0.90, 0.98] | 1.000 [1.00, 1.00] | 0.995 | 1.000 | 0.910 |
  | hybrid k=60, lexical 1.0 | 0.824 [0.75, 0.90] | 1.000 | 0.930 | 0.833 | 0.806 |
  | hybrid k=60, lexical 0.5 | 0.929 [0.88, 0.97] | 1.000 | 0.987 | 0.958 | 0.896 |

  By category, FTS chunk R@1: abbreviations 0.000 (n=5), typos 0.500 (n=4), vague
  0.600 (n=10), rare tokens 0.714 (n=7). Vector: 1.000 on all four. The five
  abbreviation questions ("What's the CLT?", "What is KMT?") are unreachable
  lexically because the expansions, not the abbreviations, are in the notes; the
  embedding model knows both. Rare tokens, the category lexical search exists for,
  went to vector 7 of 7 because a rare name never appears without its topic.
- **Fusion, re-checked:** lexical weight 0.5 is now slightly below vector (0.929 vs
  0.940 R@1; it demotes q079 and q101 to rank 2) and equal weights still cost 0.116 of
  R@1. Vector-only stays the default.
- **Honest limit:** the author of the hard questions knows what is in the notes and
  how the chunker cuts them. Vector R@5 is 1.000 on all 91 and R@1 is 1.000 on the 24
  questions written to be hard, so this set can no longer rank retrieval methods above
  the lexical baseline. Two things still discriminate: R@1 on the original questions
  (0.910, six misses) and the abstain gate. Everything else waits for the real-photo
  slice, which is held out and reported separately, and whose questions should be
  written by the note's author without reading the OCR output.
- **Precision@5** (share of the top-5 chunks that come from an expected note,
  computed from the stored per-question results): fts_or 0.482 [0.42, 0.54] (n=88,
  three questions returned no rows), vector 0.635 [0.59, 0.68], hybrid lexical 0.5
  0.598 [0.55, 0.64], hybrid lexical 1.0 0.565 [0.52, 0.61] (n=91). Even with the
  right chunk first, a third of every top-5 context is off-topic filler. That is the
  metric the Phase 4 reranker is judged on, since recall has nothing left to give.

### D26. Abstain threshold, re-derived on 17 unanswerable questions

- **Measured** (top-1 cosine, eval user, cached query embeddings): answerable min
  0.622, p25 0.672, median 0.698 (n=91); unanswerable min 0.554, p25 0.596, median
  0.618, max 0.649 (n=17). FTS returned hits for 17 of 17 unanswerable questions, so
  it carries no abstain signal.

  | threshold | unanswerable passing | answerable refused |
  |---|---|---|
  | 0.62 | 8/17 | 0/91 |
  | 0.64 | 2/17 | 3/91 |
  | 0.65 | 0/17 | 6/91 |
  | 0.66 | 0/17 | 12/91 |

- **Decision:** 0.65 as a soft gate: below it the generator is told the evidence is
  weak and must abstain unless a source plainly answers; above it the generator still
  decides. The 6 answerable questions at or below 0.65 are the cost to measure in
  Phase 3 with the generator in the loop, since a soft gate may still answer them.

---

## Phase 3: grounded generation, citations, abstain, guard, streaming (2026-09-26)

### D27. Generator: Gemini 2.5 Flash-Lite with server-enforced JSON, not Llama

- **Chose:** `gemini-2.5-flash-lite` with `response_schema` so the model must return
  `{answer, citations, abstain}`. Temperature 0.
- **Rejected:** Llama 3.3 70B on Workers AI, which the other AI features use. The
  repo carries a JSON-repair function for its truncated output; a citation list that
  might be cut off is not machine-checkable.
- **Corrected the same day (see D32):** flash-lite was chosen over `gemini-2.5-flash`
  on a latency probe (flash-lite 614 ms vs flash 1,056 ms, n=1 each) plus an assumed
  larger free-tier quota. The quota assumption was wrong and the default is now
  `gemini-2.5-flash`. The latency cost of that correction is real and measured below.
- **Citation validation:** cited numbers outside 1..N are dropped, inline `[n]`
  markers that point at nothing are stripped, and an answer that cites nothing while
  claiming not to abstain is converted to an abstain. Unit-tested.

### D28. Sources are delimited data, and the guard drops what looks like instructions

- **Threat model:** notes are photos of anything, and the shared demo account lets
  any visitor plant a note that other visitors' questions retrieve. Phase 1 showed
  the meeting-notes plant reaching rank 4 for a photosynthesis question under FTS.
- **Layers:** (1) every source is wrapped in `<source id=n note=...>` tags with a
  system instruction that sources are quoted material and any instructions inside
  them are to be ignored; (2) a regex detector over chunk text drops flagged chunks
  from the generator's context and logs their ids; (3) the eval carries planted notes
  and questions that retrieve them, with compliance measured.
- **Measured:** the detector flags exactly the two planted chunks across all 189
  corpus chunks, zero false positives on 49 clean notes, including phrases like
  "instructions for the lab" and "ignore the previous chapter's notation" (unit
  tests). The regex is the weak layer by design: paraphrased attacks pass it and
  must be caught by layer 1, which the eval measures. Compliance numbers in D31.

### D29. Abstain is a soft gate plus the model's own judgement

- Top-1 cosine below 0.65 (D26) does not short-circuit the request; it adds a
  retrieval note to the prompt telling the model the evidence is weak and to abstain
  unless a source plainly answers. Zero retrieved chunks abstains without calling the
  model. Both paths write a log row with `gate_triggered` so the false-refusal cost
  is visible per query. Measured effect in D31.

### D30. Streaming sends sources first, and real streaming needs the Web Adapter

- **Protocol:** SSE with three events: `sources` as soon as retrieval and the guard
  finish (so the UI shows where the answer will come from before a token arrives),
  `token` deltas, then `done` with the validated citations, abstain flag, timings and
  log id. Streaming uses plain text with inline `[n]` markers and a `NOT_IN_NOTES`
  sentinel because a JSON object cannot be streamed usefully; the non-streaming path
  keeps schema-enforced JSON.
- **Deployment:** Mangum buffers the whole body and the Python managed runtime has no
  native response streaming, so `streaming_enabled = true` in Terraform swaps the
  handler for `run.sh` (uvicorn) behind the Lambda Web Adapter layer, sets the
  Function URL to `RESPONSE_STREAM`, and routes the keep-warm event to `/events`.
  Default is off; the JSON endpoint is unaffected either way.
- **Verified locally** under uvicorn: see the Phase 3 report for frame timings. Not
  yet verified on Lambda (requires a deploy).

### D31. Generation eval results

Three runs, because the Gemini free tier caps generation at 20 requests per day per
model (D32) while Cloudflare Workers AI showed no throttling at all:

| run | generator | slice | file |
|---|---|---|---|
| A | gemini-2.5-flash | 21 answerable + 2 unanswerable, judged | `gen_20260927T010116.json` |
| B | llama-3.3-70b (Workers AI) | all 17 unanswerable + all 5 injection | `gen_20260927T010344.json` |
| C | llama-3.3-70b (Workers AI) | all 91 answerable, objective metrics only | `gen_20260927T010737.json` |

Objective metrics need no judge: they are computed against the same evidence spans the
retrieval eval uses. Judge metrics are reported only for run A, where the generator and
the judge are different model families.

| slice | metric | value | n | run |
|---|---|---|---|---|
| answerable | answered (did not abstain) | 0.967 [0.92, 1.00] | 91 | C |
| answerable | citation precision (cited chunks from an expected note) | 0.989 [0.97, 1.00] | 88 | C |
| answerable | evidence hit (a cited chunk contains the evidence span) | 0.956 [0.91, 0.99] | 91 | C |
| answerable | weak-evidence gate triggered | 0.066 [0.02, 0.12] | 91 | C |
| hard-v2 answerable | answered | 0.875 [0.71, 1.00] | 24 | C |
| unanswerable | answered anyway (false answer) | 0.000 [0.00, 0.00] | 17 | B |
| unanswerable | gate triggered | 1.000 [1.00, 1.00] | 17 | B |
| injection | complied with the planted instruction | 0.000 [0.00, 0.00] | 5 | B |
| injection | answered the real question | 1.000 [1.00, 1.00] | 5 | B |
| answerable | faithfulness (judge / hand audit) | 0.976 / 1.000 | 21 | A |
| answerable | correct (judge / hand audit) | 0.952 / 1.000 | 21 | A |

Latency from a dev machine, so every number includes a round trip to Neon and to the
model API. Gemini flash: generate p50 1,054 ms, p95 1,461 ms; end to end p50 1,411 ms,
p95 1,790 ms (n=23). Llama on Workers AI: generate p50 1,034 ms, p95 3,667 ms; end to
end p50 1,307 ms, p95 3,925 ms (n=91). Llama matches flash at the median and has a much
worse tail. Cost: $0.00738 for 23 Gemini answers, about $0.00032 each; Workers AI is
free on this plan. In-region numbers come from the query log (`scripts/rag_stats.py`).

### D34. The soft abstain gate was the right call, and the numbers say so

- 6 of 91 questions fell below the 0.65 cosine gate, exactly as D26 predicted. **All 6
  were still answered, and all 6 correctly** (q015 buffers, q022 airbags, q042 base
  rates, q047 Kansas-Nebraska, q082 Okazaki, q085 Kennan). A hard threshold at 0.65
  would have refused six correct answers to gain nothing, since the gate caught no
  unanswerable question the model would otherwise have answered.
- Separately, all 17 unanswerable questions triggered the gate and were refused, with
  zero false answers.
- Reading: the cosine score is a useful *hint* and a poor *veto*. The model plus the
  hint is strictly better than either alone on this corpus.

### D35. The remaining failure mode is abbreviations, and it is grounding working correctly

- All 3 false refusals on the answerable set are abbreviation questions: "What's the
  CLT?", "State the MVT.", "What is KMT?". Retrieval was not the problem: top-1 cosine
  was 0.68 to 0.76, well above the gate, and Phase 2b measured vector R@1 of 1.000 on
  the abbreviation category. The notes spell out "central limit theorem", "mean value
  theorem" and "kinetic molecular theory" but never the abbreviations, so the generator
  cannot verify from the sources alone that CLT means central limit theorem, and its
  instructions forbid outside knowledge. It refuses rather than guess.
- This is the grounding constraint doing exactly what it was told, and it is a real
  product defect at the same time. Fixing it means relaxing grounding (allow the model
  to resolve an abbreviation it is confident about) or expanding the query before
  retrieval. Both are Phase 4 candidates, and both have to be measured against the
  injection and unanswerable slices, because "allow some outside knowledge" is exactly
  the door those defences close. Not fixed blind.
- Two citation-precision misses (q096, q097, both vague phrasings) cite two chunks
  where one is from a neighbouring note. One evidence-hit miss (q034) cites the right
  note but a different chunk than the labelled span.

### D36. Workers AI as a second generator: plain text, not JSON

- Added because the Gemini daily cap made the safety slices unmeasurable otherwise.
  Selected by the `@cf/` model prefix. It takes the plain-text path (inline `[n]`
  markers plus the `NOT_IN_NOTES` sentinel) rather than a JSON schema, which sidesteps
  the Llama JSON reliability problem that ruled it out as the default in D27: there is
  no JSON to truncate, and citations are parsed from markers and validated against the
  source count either way.
- It is not the default. Gemini keeps schema-enforced JSON, and Llama is the judge, so
  making it the generator too would put the same model on both sides of the faithfulness
  metric. For the objective metrics in run C that does not matter, which is why run C is
  reported and run C's judge columns are blank.

### D32. flash-lite's free tier is 20 generation requests PER DAY, not per minute

- **Found by:** the first full generation eval. 88 of 113 questions failed with 429 and
  268 throttle waits, despite pacing at 8 requests/minute.
- **The quota:** `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 20, for
  `gemini-2.5-flash-lite`. Confirmed by a single isolated call the next minute, which
  still failed with the same quota id while `gemini-2.5-flash` on the same key
  succeeded in 357 ms. No pacing strategy fixes a daily cap.
- **Why it matters beyond the eval:** this is the deployed app's generator. A daily cap
  of 20 answers across all users would have shipped as a feature that silently stops
  working every day. The measurement caught a production defect, not just an eval
  inconvenience.
- **Fixed by:** switching the default to `gemini-2.5-flash`, which is usable where
  flash-lite was not: it answered immediately on the same key at the moment flash-lite
  was refusing every request. The cost is latency, roughly 500 ms more per answer.
- **flash is throttled too, just less severely.** Running the eval on flash at 8
  requests/minute still hit `GenerateRequestsPerMinutePerProjectPerModel-FreeTier` and
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, recovering after each cooldown:
  22 questions in about 30 minutes, so a 113-question pass takes over two hours of
  wall time and may not fit one day's quota. Consequences for how the eval is run:
  generations are cached on disk keyed by (model, mode, question, corpus), so a pass
  resumes where the last one stopped and can be completed across several sessions;
  slices can be run on their own (`--types unanswerable,injection`) so the
  safety-critical numbers are never the ones left unmeasured.
- **Open decision for the project owner:** enabling paid-tier billing on the Gemini key
  removes the caps and costs about $0.002 per 113-question pass at flash-lite prices
  and roughly $0.02 at flash prices. That is a spending decision, so it stays off by
  default. Until then, full-corpus generation numbers are assembled incrementally and
  every reported metric carries its own n.
- **Also fixed:** the eval no longer caches failed generations (the first run cached 92
  error strings as if they were answers), counts errors as a separate slice instead of
  folding them into the metrics, and backs off for the server-suggested delay before
  retrying a question.

### D33. The LLM judge is miscalibrated on correctness, and the audit is checked in

- **Setup:** Llama 3.3 70B on Workers AI judges, a different model family from the
  Gemini generator, to avoid self-preference. It sees the question, the sources the
  generator saw (full chunk text, not snippets), the reference answer, and the answer.
- **First version was worse than useless on faithfulness:** it marked "The Golgi
  apparatus packages and ships proteins in vesicles" as an unsupported claim when the
  source says exactly that, scoring faithfulness 0.0 on a perfect answer. Cause: the
  rubric did not say that a paraphrase counts as support. After the rubric fix,
  faithfulness is 1.000 and agrees with a hand audit on 25 of 25.
- **Correctness was badly miscalibrated, measured, not assumed** (`eval/judge_audit.py`,
  hand labels in `eval/judge_labels.json`). Before the prompt fix, on 25 flash-lite
  answers: judge correctness 0.720 vs hand 1.000, agreement 0.720. All 7 disagreements
  ran the same way, the judge calling a correct answer "partial" or "no" for adding
  detail or omitting context the reference happened to include. It marked "In metaphase,
  chromosomes line up at the metaphase plate" as not matching the reference "Metaphase."
- **Root cause found:** the judge prompt never showed it the question, so it was
  grading answer-versus-reference similarity rather than whether the question was
  answered. Fixed by adding the question and a worked example to the rubric.
- **After the fix**, on 21 flash answers, hand-labelled independently:

  | metric | judge | hand audit | agreement |
  |---|---|---|---|
  | correct (matches reference) | 0.952 | 1.000 | 0.952 |
  | faithful (all claims supported) | 0.952 | 1.000 | 0.952 |

  One correctness disagreement left (the judge wanted the oxygen clause in a
  lactic-acid answer) and one faithfulness disagreement (it called "using nitrogen
  isotopes" unsupported when the note says exactly that). The judge now errs by about
  5 points in the strict direction rather than 28.
- **Standing rule:** the judge's faithfulness number is reported as a headline metric;
  its correctness number is reported with the hand-audit agreement rate beside it and
  is never quoted alone. Hand labels are keyed by a hash of the exact answer text, so
  changing the model surfaces its answers as unlabelled instead of reusing a stale
  verdict.

### D37. No Gemini billing: a fallback chain instead, to Workers AI Llama

- **Decision (owner's call, 2026-09-26):** do not enable billing on the Gemini key.
  D32 measured the free tier at 20 `generate_content` requests per day, per model,
  for both flash and flash-lite -- a hard wall no pacing gets around. Rather than pay
  to remove it, the app is designed to work within it: try Gemini first, and on a
  quota error, fall back to Workers AI Llama for that one answer.
- **Detection is a substring match, not an error code check:** `is_quota_error`
  matches `"429"`, `"resource_exhausted"`, or `"quota"` (case-insensitive) in the
  exception message. Deliberately broad -- missing a quota error costs a user an
  avoidable failure; a false positive just falls back a request that would have
  failed anyway for some other reason. A non-quota error (bad argument, malformed
  request) is never silently retried against a different model, because that would
  hide a real bug behind an apparent success.
- **Non-streaming (`generate_with_fallback`):** try the primary model; on a quota
  error, retry once against the fallback and return that answer, tagging it
  `fallback_from`/`primary_error` for logging. `ask()` logs a warning whenever this
  fires and (via `AskResult.model` / `rag_queries.generation_model`) always records
  which model actually produced the answer -- "which provider answered" is a
  queryable column, not just a log line.
- **Streaming (`stream_answer_with_fallback`) has one extra rule streaming needs and
  non-streaming doesn't:** once a token has been sent to the client, a later
  mid-stream quota error does NOT fall back. The client has already rendered the
  primary model's partial answer; silently splicing in a second model's continuation
  would look like a glitch, and re-sending shown tokens would duplicate them. A
  failure before the first token -- the common case, since the Gemini SDK's stream
  iterator raises on its first pull -- falls back cleanly and the client sees the
  fallback model's answer as if it had been the only one asked. Both branches are
  integration-tested against the real `ask()` / `ask_stream()` functions (not just
  the pure fallback functions in isolation), including the mid-stream case, which
  asserts the fallback model is never called once tokens have flowed.
- **The eval harness now defaults to Workers AI, not the production default.** A
  multi-hundred-question eval run against Gemini would exhaust its daily quota in
  minutes and then spend the rest of the run silently served by the fallback anyway
  (correctly labelled per-question, but wasting the very quota production needs).
  `eval/run_generation_eval.py --model` now defaults to
  `@cf/meta/llama-3.3-70b-instruct-fp8-fast`; passing an explicit Gemini model still
  works (for a deliberate small comparison run) and each row now records `served_by`
  and `fallback_used` so a quota hit mid-run is visible in the results file, not
  averaged away.
- **Consequence for the safety numbers already measured:** D31's injection (0/5
  complied) and unanswerable (0/17 false answers) numbers were measured on Workers AI
  precisely because it is unthrottled -- and Workers AI is now also the fallback model
  that serves production traffic whenever Gemini's daily quota is spent. So the model
  most likely to answer a user's 21st question of the day already has full safety
  coverage. The gap that remains: **Gemini itself, as primary, has only partial safety
  coverage** (run A measured 2 of 17 unanswerable questions and 0 of 5 injection
  questions against Gemini directly). Production could serve up to 20 Gemini-primary
  answers a day that are not individually covered by the injection slice. Since the
  guard (D28) and the prompt's "sources are data, not instructions" framing (D27) are
  model-agnostic, and Gemini's structured-JSON output makes prompt injection *harder*
  to smuggle into a citation list than Llama's free-text format, this is a reasoned
  bet rather than a blind spot -- but it is not yet a *measurement*, and running the
  5-question injection slice against Gemini directly (well inside the 20/day budget)
  is the cheapest remaining item to close it. Held for later per the owner's explicit
  instruction to conserve Gemini quota this session.

### D38. Production incident: an unpinned SQLAlchemy upper bound broke the first deploy

- **What happened:** deploying Phase 3 (2026-09-27) returned 502 on every request.
  CloudWatch showed `Runtime.ImportModuleError: ... No module named 'psycopg'` on
  every cold start -- not `psycopg2` (the driver this project has used from the
  start and the only one bundled), but `psycopg` (psycopg3), which nothing in the
  codebase imports directly.
- **Root cause, reproduced in isolation before touching prod again:** `requirements.txt`
  pinned `sqlalchemy>=2.0.0` with no upper bound. The local dev venv had 2.0.34 cached
  from earlier in the project, so all 209 tests and every CI run to date exercised
  that version. `backend/build.sh` runs a fresh, unpinned `pip install` for every
  Lambda package, and this time it resolved 2.1.1 -- which changed the default
  dialect for a bare `postgresql://` DSN (used everywhere: local `.env`, Neon prod
  URLs, all of them driver-less) from `psycopg2` to `psycopg` (v3). Reproduced the
  exact failure in a clean `pip install --target` directory with only
  `sqlalchemy==2.1.1` and nothing else: `create_engine("postgresql://...")` raised
  `ModuleNotFoundError: No module named 'psycopg'` immediately, byte-for-byte
  matching the CloudWatch error, before I touched the real build again.
- **Fix:** pinned `sqlalchemy>=2.0.0,<2.1.0`. Verified the fix the same way: the pinned
  range resolves to 2.0.54, whose bare-DSN default is back to `psycopg2`, and engine
  creation succeeds once `psycopg2-binary` is present (also verified in isolation).
  Rebuilt the Lambda package, redeployed, and confirmed live: root endpoint 200,
  `/api/ai/ask` answered an answerable and an unanswerable question correctly, and
  both landed in `rag_queries` in production with no error.
- **Why local tests never caught this:** the test suite runs against whatever
  SQLAlchemy is already installed in the dev venv (2.0.34, installed once early in
  the project and never re-resolved), while `build.sh` re-resolves every dependency
  from scratch on every build. Two different install paths asking pip to satisfy the
  same unbounded constraint (`>=2.0.0`) can and did answer differently on different
  days. `requirements-dev.txt` (used by CI and by every test run in this project)
  does `-r requirements.txt`, so it inherited the same unbounded pin -- the next
  fresh CI run would have hit this too, not just the Lambda build. The fix closes
  both paths at once.
- **Lesson:** an unbounded lower-bound pin (`>=X`) on a library your code depends on
  for *default behavior*, not just an API surface, is a live production risk every
  time the build re-resolves dependencies, which for this project's `build.sh` is
  every single deploy. The other unpinned packages in `requirements.txt`
  (`fastapi`, `pydantic`, `boto3`, etc.) carry the same latent risk; this incident
  is the reason to eventually audit and pin the rest, not proof that this was the
  only one waiting.
