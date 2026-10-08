# Handoff — user3 (UI + legal content), branch `ui/streamlit`

Date: 2026-10-08 · Worktree: `/home/frost/legal-agent` · HEAD: `f8d76d4`
Upstream: `origin/ui/streamlit` in sync (this file not yet pushed at write time).

## What is done (all on `ui/streamlit`, all pushed except this file)

- `991f8a0` Streamlit app (`ui/`): Chat/Draft/Review/Research tabs, upload +
  case-set sidebar, clickable `[cN]` chips + source side panel
  (`GET /sources/{chunk_id}` with honest quote-fallback), claims table,
  refusal/missing-info/contradiction banners, single base-URL mock→real switch.
- `templates/` (bail application, legal notice, affidavit — no hardcoded
  section numbers, test-enforced) + `docs/templates_sources.md`.
- `b4747aa` `GET /sources` route (superseded by core `04d98da`; merges auto-resolve).
- `17b9af3`, `099745b` merges from `origin/main` (refusal hardening, corpus,
  core corrections fixes + eval recheck). Conflicts met so far: AGENTS.md
  (kept both sides) and `tests/test_api.py` (always keep the `zxqv` probe side).
- `f8d76d4` corrections fixes: `_fill_example` on_click callback (double-click
  crash), `_DATAFRAME_KWARGS` width compat. AppTest-verified (double-click,
  no exception) on branch AND main.
- `user3.md` status note (mirrors `user1.md`/`user2.md`).

## Current state / how to verify

- Suite: 66 passed (`tests/`), schema (`contracts/schemas.py`) clean — every commit.
- `origin/main` already contains all of the above (fast-forwarded to `f8d76d4`).
- Re-verify anytime: `.venv/bin/python -m pytest tests/ -q` from this worktree
  (shared venv — never system pip).

## Open / for next session

- Nothing blocking on UI side. Next UI work branches fresh from `main`.
- Do NOT commit `corpus/`, `data/raw/`, `eval/` leftovers or
  `total_agent_idea.md` from this tree — other collaborators' files.
  Stale-copy backup (if still needed): `/tmp/opencode/legal-agent-untracked-backup/`.
- Do NOT touch `/tmp/opencode/legal-agent-main` (tester's worktree, has
  `test_demo` pollution per `correctionsfile.md`) or other users' worktrees.
- Protocol (`AGENTS.md`): stay on `ui/streamlit`, `main` takes merges only,
  status+branch check before touching shared files, HTTP-only UI, verified
  quotes only, never fabricate chunk text.
