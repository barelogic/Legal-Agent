# user2 handoff — eval corrections re-check (2026-10-08)

Owner: user2 · Branch: `eval/data-eval` · Worktree: `/home/frost/legal-agent-eval`
Tip: `9366fd7` (pushed to both `origin/eval/data-eval` and `origin/main`).
This file exists ONLY on `eval/data-eval` (not on `main`).

## What was done
- Read `/home/frost/correctionsfile.md` user2 items (`eval/`, `data/` seeds/corpus).
- Merged `origin/main@8c46752` (core: hybrid seeds union + proportional gate,
  `retrieval/hybrid.py`, `retrieval/store.py`) into `eval/data-eval`.
- Verified the two core bugs from the eval side (no core edits — read-only probes):
  - API `get_index()` lacked seeds pre-fix (`doc_ids=["case_file_demo"]` → `[]`);
    post-fix hits. Harness (`eval/systems.py:65`, `eval/metrics_retrieval.py:30`)
    builds `HybridIndex` directly, so its numbers never skewed.
  - Single-token `"bail"` refused pre-fix, answers post-fix (2 claims);
    `"xyzzy"` still refuses. Matches `eval/metrics_grounded.py:78-82` intent.
- Added `eval/tests/test_short_queries.py` (4 tests, eval-owned regression lock).
- Re-ran `eval/run_all.py --hf-limit 0 --top-k 4` on branch AND on
  `/tmp/opencode/legal-agent-main@8c46752`: tunable tables IDENTICAL
  (lexical `0.520/0.380`, hybrid `0.600/0.500`, `refusal_R 0.000`,
  fabrication `0.0` clean / `1.0` injected).
- Updated `user2.md`, committed `9366fd7`, pushed eval branch, then
  fast-forwarded `origin/main 8c46752..9366fd7` from the `/tmp` main checkout
  (cleaned its `test_demo` pollution, rebuilt `47 docs / 1489 chunks`).

## State
- `origin/eval/data-eval` = `9366fd7`, `origin/main` = `9366fd7` (same SHA).
- Suite: `81 passed` (`tests/ eval/tests/ corpus/tests/`), `contracts/schemas.py` clean.
- Main tree `/home/frost/legal-agent` untouched (`ui/streamlit@17b9af3`, clean).
- `eval/results/` + `eval/datasets/` are gitignored runtime state (rebuilt by one command).

## Reproduce (one command each)
- Suite: `/home/frost/legal-agent/.venv/bin/python -m pytest tests/ eval/tests/ corpus/tests/ -q`
- Numbers: `/home/frost/legal-agent/.venv/bin/python eval/run_all.py --hf-limit 0 --top-k 4`
- Seed/gate probes: `/home/frost/legal-agent/.venv/bin/python -m pytest eval/tests/test_short_queries.py -q`
- Schemas guard: `git diff -- contracts/schemas.py` (must be empty)

## Pending / next
- Hand-built `eval/queries.jsonl` (40) has no single-token items by design;
  short-query behavior is locked by the new test file, not the JSONL (its
  40-count asserts in `eval/build_queries.py:23,58-60` must not be broken).
- If core changes the gate again, re-run the two commands above and update
  `user2.md` numbers; tunable split currently has no single-token so it is
  gate-insensitive, the test file is the sensitive guard.
- Do NOT push `main` from this handoff; `main` already contains `9366fd7`.
