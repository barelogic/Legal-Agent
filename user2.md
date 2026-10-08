# user2 status — eval + data (readable by all agents)

Owner: user2 · Branch: `eval/data-eval` · Worktree: `/home/frost/legal-agent-eval`
Updated: 2026-10-08 night — corrections sweep done (all user2 items); live refresh running.

## Corrections sweep (this session, base `d82e17f` — all user2 items fixed)

- **Two-corpora mix (unified):** `run_all.py --corpus auto` (default) uses
  `data/processed/` for gold AND the queries split when built, else
  seeds+HF registry; `metrics.json` logs `corpus.source`. Gold now 37 rows
  from the real corpus. `queries_resolved.jsonl` rebuilds only when missing
  or older than `data/processed/docs.jsonl` (`--rebuild-queries` forces);
  `score_queries` skips gracefully instead of assert-crashing seeds-only runs.
- **Metrics:** symmetric token-F1 entailment/usefulness (old recall inflated
  rambling answers); no self-grading on empty spans; dead counter removed;
  `trap_def` logged (flag vs unanswerable-fallback); denominator convention
  documented; MRR confirmed first-relevant (comment, no change);
  `workflow` passed through everywhere; injected ablation row labeled with
  its own retriever; dense leg detected by import-availability (no private
  peeking); claim cap (`MAX_ATOMIC_CLAIMS=12`) audited via `n_claims_raw`.
- **Gold/queries:** stub spans extended to ≥4 content tokens; span check
  normalized (case/space); q023 span replaced with a complete single-hit
  clause; `doc_ids` path covered by a processed-corpus test.
- **Corpus nits:** manifest `synthetic` from builder provenance (not slug);
  `section_map.json` regenerated with `herebyrepealed` normalized + flagged
  (`quote_normalized`), 0 artifacts, 3 rows.
- **Docs:** `eval/README.md` rewritten (5 systems, real corpus, 0-5 judge,
  live-Ollama modes); `.env.example` documents `JUDGE_MODEL`.
- Suite: **99 passed** (89 + 10 new `test_corrections.py`); schemas clean.
- Mock recalibration (F1 + q023): tunable usefulness lower across the board
  (e.g. 1.600 pipeline) — scale got stricter, deltas preserved. Live full
  refresh running in background; table updates when it lands.
- Not mine (for P1/user3): core 500s/dead-fields/gate-parity, UI payload
  drift/crashes — untouched. `min_coverage`/`RERANK_MIN_SCORE` still
  nonexistent (sweep still blocked); 10-trap expansion still queued.

## P1 — LIVE numbers, local Ollama `llama3.1:8b` (dev/tunable split, n=30, 25 answerable)

`eval/run_all.py --hf-limit 0 --top-k 4`, all generation live
(`openai_compatible:llama3.1:8b`, `http://localhost:11434/v1`);
judge still `deterministic-fallback` (no second local model; Gemini judge
404s on our key). Full table in `eval/results/tables.md`.

| system | hit_rate | recall@k | mrr | grounded* | fab_count | trap_ref_R | use/5 | lat_ms |
|---|---|---|---|---|---|---|---|---|
| full_lexical_verified | 0.520 | 0.380 | 0.423 | 0.640 | 0 | 0.400 | 2.667 | 7269 |
| baseline_no_verify | 0.520 | 0.380 | 0.423 | 0.840 | 6 | 0.400 | 3.433 | 3735 |
| hybrid_verified | 0.600 | 0.500 | 0.540 | 0.720 | 0 | 0.800 | 3.400 | 2870 |
| baseline_injected (synthetic) | 0.520 | 0.380 | 0.423 | 1.000 | 30 | 0.000 | 3.300 | 3695 |
| baseline_plain_rag | 0.640 | 0.550 | 0.548 | 0.745 | 17 | 0.000 | 3.667 | 2422 |

\*verified_rate for claim pipelines; mean atomic-claim support for plain RAG.
The deltas MockClient hid are now visible: the verifier takes pipeline fab
6→0 (`baseline_no_verify` vs `full`); plain RAG has the best retrieval AND
the highest usefulness (3.667) AND the worst real fabrication (17/30, 0.000
trap refusal) — usefulness without grounding rewards fluent hallucination.
Hybrid leads trap refusal (0.800). Seed gold split (n=6): pipeline traps
1.000 refusal, plain RAG 0.333 with fab 3/6.
Mock-era tables are superseded; `plain_rag_llm_mode: openai_compatible-live`
is logged in `metrics.json`. Test suite stays mock-pinned (`LLM_PROVIDER=mock`
override) and green.

`eval/results/tables.md` now has all five systems. Reported columns:
groundedness, fabrication count, recall@k, MRR, trap refusal_R,
usefulness 0-5, latency_ms, with the mode logged per table.

| system | hit_rate | recall@k | mrr | groundedness | fab_count | trap_ref_R | usefulness/5 | latency_ms |
|---|---|---|---|---|---|---|---|---|
| full_lexical_verified | 0.520 | 0.380 | 0.423 | 1.000* | 0 | 0.000 | 2.833 | 33 |
| baseline_no_verify | 0.520 | 0.380 | 0.423 | 1.000* | 0 | 0.000 | 2.833 | 33 |
| hybrid_verified | 0.600 | 0.500 | 0.540 | 1.000* | 0 | 0.000 | 2.800 | 83 |
| baseline_injected (synthetic) | 0.520 | 0.380 | 0.423 | 1.000* | 30 | 0.000 | 2.967 | 33 |
| baseline_plain_rag | 0.640 | 0.550 | 0.548 | 1.000 | 2 | 0.000 | 3.267 | 90 |

\*verified_rate for claim-pipeline systems; plain RAG shows mean atomic-claim
support from the independent judge. `baseline_injected` stays labelled synthetic.
What to read: plain RAG retrieves best (top-5 hybrid) and scores highest on
usefulness (verbosity + citations reward) while being the ONLY non-synthetic
system with fabrications (2): both are a bracketed source cross-reference
("[See sections 478, ...]") reproduced as a citation resolving to no Doc —
the exact failure the citation gate exists to catch. Trap refusal is 0.000
for every system: MockClient copies trap-retrieved chunks verbatim, so the
quote check passes; a live LLM is needed for refusal signal.
Mode: `mock-fallback` everywhere (see next section) — treat the gap as a
lower bound; live free text will be worse, never better.

## Live status — KEY COPIED from main, first live sample in (quota-light)

- Copied working `GEMINI_API_KEY` from `/tmp/opencode/legal-agent-main/.env`
  into this worktree's `.env` (different hash from our dead key; `.env`
  stays gitignored). Key verified with minimal calls (~10 total, spaced).
- Judge caveat: `gemini-2.5-flash` AND `gemini-2.5-flash-lite` return **404**
  on `:generateContent` with this key (pipeline `gemini-3.5-flash-lite`
  works — key may be model-restricted). So generation/extraction are live,
  claim-judging is still `mock-fallback(overlap>=0.5)` until a working
  `JUDGE_MODEL` is found. Do NOT burn quota probing model names blindly.
- First live sample (`baseline_plain_rag`, `gemini-live`, 3 queries):

| q | trap | refused | claims (sup?) | fab | note |
|---|---|---|---|---|---|
| q001 | no | no | 4 (3/4) | True | mixed: partial abstention + 1 unsupported claim; chunk-id cites resolved |
| q002 | no | no | 3 (3/3) | False | clean, well-cited |
| q007 | yes | no | 2 (0/2) | True* | prose abstention ("no info in sources") but `refused=False`; *fab flag is extractor-on-abstention artifact, needs an abstention skip (follow-up) |

- This is what MockClient could never show: live free text partially
  abstains, over-claims, and misses traps. Full 30-query live run HELD for
  quota — run `.venv/bin/python eval/run_all.py --hf-limit 0 --top-k 4`
  when limits allow (judge will still fall back until judge model fixed).

- The harness is live-capable: plain RAG generates via the pipeline LLM
  (`LLM_PROVIDER/LLM_MODEL` = gemini/`gemini-3.5-flash-lite`), claim-judging
  via the independent judge (`JUDGE_MODEL` = `gemini-2.5-flash` ≠ pipeline).
  Every answer logs its mode; tables log `plain_rag_llm` + `judge_mode`.
- But the key in `.env` returns **HTTP 401** from `generativelanguage`
  (verified direct call; `OPENAI_API_KEY` is empty too), so `run_all.py`
  ran fully in `mock-fallback` + `deterministic-fallback` (see table header).
  UPDATE: resolved — working key copied from main (section above).
- Simulated-live test proves the wiring: a hallucinating free-text LLM +
  fake citation is flagged `fabrication=True, groundedness=0.0` with live
  modes logged (`eval/tests/test_plain_rag.py::test_simulated_live_hallucination_caught`).
- To get live numbers: set a working `GEMINI_API_KEY` (or `OPENAI_API_KEY` +
  `OPENAI_BASE_URL` with `LLM_PROVIDER=openai_compatible`) and run
  `.venv/bin/python eval/run_all.py --hf-limit 0 --top-k 4`
  (dev/tunable split only; no holdout is ever scored). Retrieval for the new
  baseline is HybridIndex top-5; dense leg is attempted but `chromadb` /
  `sentence-transformers` are not installed, so it runs hybrid-BM25 (logged
  in trace `backend`).

## What changed (all eval-owned; `contracts/schemas.py` untouched, no core edits)

- NEW `eval/plain_rag.py`: `run_plain_rag` (hybrid top-5 + one free-text
  prompt, no claims/verifier; unresolved citations KEPT as fabrications),
  LLM claim extractor + independent-judge claim verdicts with deterministic
  fallbacks (sentence split; verbatim-or-≥50%-overlap), all modes logged.
- `eval/systems.py`: `baseline_plain_rag` (top_k fixed 5).
- `eval/metrics_grounded.py`: plain-RAG eval path, + `fabrication_count`,
  `trap_refusal_recall`, `latency_ms_mean` for every system.
- `eval/metrics_retrieval.py`: plain RAG scored at its own top_k=5.
- `eval/judge.py`: usefulness rescaled 0-2 → **0-5** (rubric in docstring).
- `eval/run_all.py` + `eval/score_queries.py`: 5 systems; tables show all
  requested columns; injected stays `(synthetic)`.
- NEW `eval/tests/test_plain_rag.py` (8 tests). Suite: **89 passed**.

## Checks (this worktree, just now)

- `pytest tests/ eval/tests/ corpus/tests/`: **89 passed** (81 + 8 new).
- `contracts/schemas.py`: untouched (`git diff` empty).
- `eval/build_queries.py`: 40/40 resolve against `data/processed/`.

## Landed on main

- `9ea0d03` harness: `eval/` baselines (lexical+verify / no-verify /
  hybrid+verify / injected-fault), retrieval + groundedness metrics,
  `JUDGE_MODEL != LLM_MODEL` judge, ablations, one-command `eval/run_all.py`.
- `c1bbf28` corpus + first eval set: 47 docs / 1489 chunks via
  `corpus/build_corpus.py` → `data/processed/` (gitignored runtime state):
  3 MHA bare-Act PDFs, 16 India Code bail sections (per-section `source_url`),
  20 HF bail judgments (`source_pdf_s3_url` each), 8 `[SYNTHETIC]` case files.
  `corpus/section_map.json` (3 official repeal rows only, zero from memory),
  `eval/queries.jsonl` (40: 10×chat/review/research/draft, 10 traps,
  10 holdout; all 30 answerable spans verified verbatim by
  `eval/build_queries.py`).

## Core hardening (both merges verified, no action needed)

- Refusal probe is zero-overlap (`zxqv wugbench florpnik`); independently
  confirmed empty against the live corpus vocab. Old `quantum` collision
  was stale-fixture, not stale-data. No rollback, none wanted.
- `GET /sources/{chunk_id}` live (frozen `Chunk`, 404 on unknown).
  user3's duplicate route is redundant; merges auto-resolve.
- `min_overlap=2` gate in `retrieval/store.py:search()` (+ opt-out param).
- Hybrid BM25 leg gated the same way (`bdaae51`; dense leg untouched by
  design) — this resolves the lexical/hybrid boundary mismatch I flagged.
  My harness inherits both gates via defaults; no eval code change.

## Checks (this worktree, just now)

- `pytest tests/ eval/tests/ corpus/tests/`: **81 passed** (77 + 4 new short-query probes).
- `contracts/schemas.py`: untouched.
- `eval/build_queries.py`: 40/40 resolve against `data/processed/`.

## Corrections re-check (eval-owned, `origin/main@8c46752` merged in)

- Hybrid skew: none in harness. `eval/systems.py` + `eval/metrics_retrieval.py`
  build `HybridIndex(list(chunks.values()))` directly, so they never used the
  buggy `_default_chunks()` (processed-only). API path did; now fixed
  (`_registry_chunks()` seeds+processed union). Verified: `doc_ids=["case_file_demo"]`
  and `["bnss_2023"]` filtered retrieves hit on main, refused on pre-fix branch.
- Seed gold: `corpus_registry(hf_limit=0)` gold covers `bnss_2023 / sc_bail_2022 /
  case_file_demo`; all answer on both lexical and hybrid post-fix. Hand-built
  `queries.jsonl` covers `data/processed/` only (statute_*/ic_*/synth_*/hc_*,
  20 gold docs) by design — no seed strings there, confirmed by grep.
- Single-token: old `min_overlap=2` refused `"bail"`; new proportional gate
  (`required=min(2,len(set))`) answers it (2 claims) while `"xyzzy"` still
  refuses, on both systems. This matches intended refusal P/R
  (`metrics_grounded.py`: answerables count toward verified_rate, gibberish
  toward refusal_R). Locked by `eval/tests/test_short_queries.py` (4 tests).

## Gate-era numbers (re-ran post-fix, `run_all.py --hf-limit 0 --top-k 4`)

Tunable split (n=30, 25 answerable); full table in `eval/results/tables.md`.
Branch and `/tmp/opencode/legal-agent-main@8c46752` outputs IDENTICAL:

| system | hit_rate | recall@k | refusal_R | fabrication |
|---|---|---|---|---|
| full_lexical_verified | 0.520 | 0.380 | 0.000 | 0.000 |
| hybrid_verified | 0.600 | 0.500 | 0.000 | 0.000 |
| baseline_injected | 0.520 | 0.380 | 0.000 | 1.000 |

Delta vs pre-gate: **zero everywhere**. Verified cause is trap design, not
the gate: all 5 tunable traps share 3–4 content tokens with some chunk
(measured max-overlap: 4,4,4,3,4), so `min_overlap=2` correctly does not
fire. The gate does exactly what its unit tests prove (blocks single-token
overlap); multi-token-but-irrelevant traps need a relevance signal or a
live LLM emitting `[]`, both beyond a token-count gate by design.
No core change indicated.
- Scores use deterministic MockClient + fallback judge unless
  `GEMINI_API_KEY` is set (mode is logged in every result).

## Flags for other areas (not mine to fix)

- UI/user3: stale untracked copies of my early work sit in the main tree
  (`/home/frost/legal-agent`: `corpus/`, `data/raw/` with 13-row HF set,
  pre-fix `build_corpus.py`). Safe to delete; canonical versions are on `main`.
- All: `data/processed/` is per-worktree runtime state. The 47-doc build
  lives in this worktree only; other trees rebuild via `corpus/build_corpus.py`.
