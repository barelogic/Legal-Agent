# user2 handoff — eval + live local-LLM numbers (2026-10-08, evening)

Owner: user2 · Branch: `eval/data-eval` · Worktree: `/home/frost/legal-agent-eval`
Tip: `30316d8` on `origin/eval/data-eval`; merged to `origin/main@d82e17f`.
(Note: this file now exists on `main` too via that merge.)

## What was done since the last handoff (`12cb968`)
- New `eval/plain_rag.py`: `baseline_plain_rag` (HybridIndex top-5 + one
  free-text prompt via the pipeline LLM, no claims/verifier; unresolved
  citations kept as fabrications) + eval-time atomic-claim extraction and
  independent-judge verdicts, all modes logged, deterministic fallbacks.
- `eval/systems.py`: pipeline systems use `make_client()` (mock default
  identical; live when `LLM_PROVIDER` says so) + `trace["llm_client"]`.
- Metrics: `fabrication_count`, `trap_refusal_recall`, `latency_ms_mean`
  (all systems); plain RAG scored at its own top_k=5; judge usefulness 0-5.
- Local LLM: Ollama `llama3.1:8b` pulled (4.9 GB); this worktree's `.env`
  (gitignored) points at it (`openai_compatible`, `localhost:11434/v1`).
  Copied working `GEMINI_API_KEY` from main's `.env` first (ours 401'd),
  but Gemini judge 404s on `:generateContent` — judge stays fallback.
- Full live `run_all.py --hf-limit 0 --top-k 4` on dev split (n=30):
  verifier takes pipeline fab 6→0; plain RAG best retrieval (0.640/0.550),
  top usefulness (3.667) but worst fab (17/30, trap_ref 0.000); hybrid
  trap_ref 0.800. Table in `user2.md` + `eval/results/tables.md`.
- New `eval/live_progress.py` (watch the background run) and
  `eval/tests/test_plain_rag.py` (8 tests incl. simulated-live hallucination).
- Merged eval→main (`d82e17f`): main tree updated to `3bd71b2` first (core
  verifier hardening + UI demo fallback), auto-merge no conflicts,
  **140 passed** on merged tree, schemas clean, pushed `origin/main`.

## State
- `origin/eval/data-eval` = `30316d8`, `origin/main` = `d82e17f`.
- Suite: `89 passed` here (`LLM_PROVIDER=mock` override keeps it offline);
  `140 passed` on merged main (adds core's verifier tests).
- `contracts/schemas.py` untouched; no core/ edits; UI + core worktrees untouched.
- `eval/results/` + `eval/datasets/` are gitignored runtime state.

## Reproduce (one command each)
- Suite (offline): `LLM_PROVIDER=mock .venv/bin/python -m pytest tests/ eval/tests/ corpus/tests/ -q`
- Live numbers (needs Ollama + model): `.venv/bin/python eval/run_all.py --hf-limit 0 --top-k 4`
- Plain-RAG probes: `.venv/bin/python -m pytest eval/tests/test_plain_rag.py -q`
- Watch a run: `.venv/bin/python eval/live_progress.py --log <bg-out>`
- Schemas guard: `git diff -- contracts/schemas.py` (must be empty)

## Pending / next (in priority order)
1. **10 near-vocab traps** (user asked): fake case names, absent-Act sections,
   absent fact from a real file, real name + wrong year/court; ≥3 to holdout;
   per-trap max-overlap log. Recon done (20 HF party names, 8 synth files).
   Do AFTER any running eval finishes (run_all re-resolves queries.jsonl at
   the end); then bump `build_queries.py` asserts (40→50, traps 10→20).
2. **Threshold sweep**: BLOCKED — `min_coverage` / `RERANK_MIN_SCORE` exist
   nowhere (checked core + eval + all branches). Waiting on user call:
   (a) P1 lands the knobs, or (b) eval-side prototype sweep to recommend values.
3. Judge liveness: needs a working `JUDGE_MODEL` (different string from
   `LLM_MODEL`); options are a second Ollama model or a fixed Gemini key.
   Do NOT burn quota blind-probing model names.
