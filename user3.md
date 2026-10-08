# user3 status — UI + legal content (readable by all agents)

Owner: user3 · Branch: `ui/streamlit` · Worktree: `/home/frost/legal-agent`
Updated: 2026-10-08, at merge `17b9af3` (origin/main refusal-hardening + corpus merged into UI branch, pushed to `origin/main`).

## Landed on main

- `991f8a0` Streamlit app + legal content + tests + AGENTS contract:
  `ui/` tabbed app (Chat / Draft / Review / Research), upload + case-set
  sidebar, clickable `[cN]` evidence chips with source side panel, claims
  table with status badges, refusal / missing-info / contradiction banners;
  single mock→real switch (API base URL only). `templates/` (bail
  application, legal notice, affidavit JSON — zero hardcoded section
  numbers, test-enforced) + `docs/templates_sources.md` (public sources
  with URLs). `tests/test_ui_render.py` + `tests/test_templates.py`.
- `b4747aa` `GET /sources/{chunk_id}` route for the UI source view
  (verbatim `Chunk`, 404 if unknown). Superseded by core's `04d98da`
  (identical content); merge hunks auto-resolved, `zxqv` probe kept.
- `17b9af3` Merge origin/main into `ui/streamlit`, pushed `ui/streamlit:main`
  (fast-forward `939d943..17b9af3`). AGENTS.md hand-merged: worktree table
  + shared-checkout protocol from main, UI↔backend contract from UI side
  (`GET /sources` marked landed).

## Grounding guarantees (pinned by tests, not assumed)

- `contracts/schemas.py` frozen — zero diff, every commit.
- UI renders facts only from verified claims (`chunk_ids` + verbatim
  `quote` enforced in `ui/render.py` pure helpers, before any Streamlit
  code); unverifiable claims surface as dropped/refused, never as facts.
- `GET /sources/{chunk_id}` failure degrades honestly to the verified
  quote with an "unavailable" note — chunk text is never fabricated.
- 62 tests green at merge landing.

## Corrections fixes (2026-10-08, on `ui/streamlit`, verified here + main)

- "Fill example" crash (`ui/app.py`): preset write moved to an `on_click`
  callback (`_fill_example`) — writing a widget-backed key after
  instantiation raised `StreamlitWidgetAlreadyInstantiatedError` on repeat
  clicks. Verified via `AppTest`: two `preset-chat` clicks, no exception,
  `q-chat` == preset.
- `st.dataframe` deprecation (`ui/app.py`): `_DATAFRAME_KWARGS` resolves
  `width="stretch"` vs legacy `use_container_width` from the installed
  signature at import — runs warning-free on old and new Streamlit.
- Contract reminder: unchanged — HTTP-only, verified quotes, honest
  404 fallback. 66 tests green, `contracts/schemas.py` untouched.

## Flags for other areas (not mine to fix)

- All: pre-merge backup of early untracked copies (`corpus/`, `data/raw/`,
  `eval/`, `total_agent_idea.md`) sits at
  `/tmp/opencode/legal-agent-untracked-backup/` — safe to delete once
  the tracked versions on `main` are confirmed canonical.
- All: impeccable skill (v4.1.0) installed globally at
  `~/.claude/skills/impeccable/` (OpenCode V2 auto-discovers as
  skill ID `impeccable`); user-level install, repo untouched.
- Core/eval: nothing blocking from UI side. `ui/streamlit` == `main`
  content for UI dirs; further UI work branches fresh from `main`.
