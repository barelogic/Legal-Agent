# user2 status — eval + data (readable by all agents)

Owner: user2 · Branch: `eval/data-eval` · Worktree: `/home/frost/legal-agent-eval`
Updated: 2026-10-08, corrections re-check vs `origin/main@8c46752` (hybrid seeds union + proportional gate).

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
