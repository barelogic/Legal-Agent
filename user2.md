# user2 status — eval + data (readable by all agents)

Owner: user2 · Branch: `eval/data-eval` · Worktree: `/home/frost/legal-agent-eval`
Updated: 2026-10-08, at merge `c2bb941` (main's hybrid gate merged in).

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

- `pytest tests/ eval/tests/ corpus/tests/`: **63 passed**.
- `contracts/schemas.py`: untouched.
- `eval/build_queries.py`: 40/40 resolve against `data/processed/`.

## Pending on me (not blocking)

- Regenerate `eval/results/` tables under the new gates and report
  before/after deltas (expect trap refusal_R up from 0.0). Pre-gate numbers
  in earlier messages are stale — do not quote them.
- Scores use deterministic MockClient + fallback judge unless
  `GEMINI_API_KEY` is set (mode is logged in every result).

## Flags for other areas (not mine to fix)

- UI/user3: stale untracked copies of my early work sit in the main tree
  (`/home/frost/legal-agent`: `corpus/`, `data/raw/` with 13-row HF set,
  pre-fix `build_corpus.py`). Safe to delete; canonical versions are on `main`.
- All: `data/processed/` is per-worktree runtime state. The 47-doc build
  lives in this worktree only; other trees rebuild via `corpus/build_corpus.py`.
