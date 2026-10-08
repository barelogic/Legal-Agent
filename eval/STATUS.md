# user2 status — eval + data (readable by all agents)

Owner: user2 · Branch: `eval/data-eval` · Worktree: `/home/frost/legal-agent-eval`
Updated: 2026-10-08, after merging `main@9db7519`.

## Landed on main

- `9ea0d03` harness: `eval/` baselines (lexical+verify / no-verify / hybrid+verify /
  injected-fault), retrieval + groundedness metrics, `JUDGE_MODEL != LLM_MODEL`
  judge, ablations, one-command `eval/run_all.py`.
- `c1bbf28` corpus + first eval set: 47 docs / 1489 chunks via
  `corpus/build_corpus.py` → `data/processed/` (gitignored runtime state):
  3 MHA bare-Act PDFs, 16 India Code bail sections (per-section `source_url`),
  20 HF bail judgments (`source_pdf_s3_url` each), 8 `[SYNTHETIC]` case files.
  `corpus/section_map.json` (3 official repeal rows only, zero from memory),
  `eval/queries.jsonl` (40: 10×chat/review/research/draft, 10 traps,
  10 holdout; all 30 answerable spans verified verbatim by
  `eval/build_queries.py`).

## Core relay (verified by me, no action needed)

- Refusal probe is now zero-overlap (`zxqv wugbench florpnik`); I confirmed
  empty overlap against the live corpus vocab. The old `quantum` collision
  was stale-fixture, not stale-data. No rollback.
- `GET /sources/{chunk_id}` live on `main:api/main.py` (frozen `Chunk`, 404
  on unknown). user3's duplicate route is redundant; merges auto-resolve.
- `min_overlap=2` gate in `retrieval/store.py:search()` (+ opt-out param,
  + unit tests). My harness inherits it via defaults — no eval code change.

## Implications for my numbers (pending re-run)

Last tables predate the gate. After this merge I will re-run
`eval/build_queries.py` + `eval/run_all.py` + full pytest and report
before/after deltas (expect trap refusal_R to rise from 0.0; small hit-rate
cost possible). Do not quote pre-gate numbers as current.

## Flags for other areas (not mine to fix)

- Core: `retrieval/hybrid.py` TF fallback still fires on ≥1-token overlap,
  so lexical and hybrid now disagree on the refusal boundary. Suggest
  aligning it with `min_overlap` (their file, their call).
- UI/user3: stale untracked copies of my early work sit in the main tree
  (`/home/frost/legal-agent`: `corpus/`, `data/raw/` with 13-row HF set,
  buggy `build_corpus.py`). Safe to delete; canonical versions are on `main`.
- All: `data/processed/` is per-worktree runtime state. My 47-doc build
  lives in this worktree only; other trees rebuild via `corpus/build_corpus.py`.
