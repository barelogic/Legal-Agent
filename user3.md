# user3 status — UI + legal content (readable by all agents)

Owner: user3 · Branch: `ui/streamlit` · Worktree: `/home/frost/legal-agent`
Updated: 2026-10-09, at `a5a36b4` (synced to `origin/main` `3ac2d8b`; corrections fresh-pass clean).

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
- `17b9af3` + `099745b` + `cf78097` merges from `origin/main` (refusal
  hardening, corpus, core corrections, DOCX export batch). `AGENTS.md`
  hand-merged where conflicted (kept both sides); `tests/test_api.py`
  always keeps the `zxqv` probe side.
- `f8d76d4` corrections fixes: `_fill_example` on_click callback
  (double-click crash), `_DATAFRAME_KWARGS` width compat (AppTest-verified).
- `3a52db8` user-provided distinction: amber `user-provided` badge +
  asked-question echo; honest `/sources` fallback wording.
- `ef990ac` draft flow: precheck card (template N-of-M, confidence),
  missing-info inputs → `provided_values`, draft view (underline + quote
  hover, `[cN]` chips, red `[MISSING]` / amber `[USER-PROVIDED]`),
  verifier bar on every result, contradiction side-by-side word-diff.
- `97a3709` DOCX export (`python-docx` in `ui/requirements.txt`): draft +
  Still needed + Sources appendix (chunk_id, Doc title, citation, quote);
  screen parity via shared `draft_segments()`, test-pinned headings.
- `63008f3` offline fallback: `ui/fixtures/*.json` (chat / precheck /
  draft / review / refusal valid Answers + `chunks.json` registry) and
  sidebar "Use fixtures" toggle — every screen works with zero HTTP.
- `83e965e` redesign (compare tab, trace `backend`/`fallbacks` banners,
  `trace.field_status` precheck with fallback, List View banner, dark
  theme, `docs/writeup.md` 4-min script): `draft_type` + `doc_types`
  sent forward-compatibly; fixtures regenerated from the live backend.
  `ui/demo.md` superseded by the writeup.
- Fresh-pass (2026-10-09) residual: branch ahead of `main` — merged to
  close out; crash/dep/template findings all verified fixed by tester.

## Grounding guarantees (pinned by tests, not assumed)

- `contracts/schemas.py` frozen — zero diff, every commit.
- UI renders facts only from verified claims (`chunk_ids` + verbatim
  `quote` enforced in `ui/render.py` pure helpers, before any Streamlit
  code); unverifiable claims surface as dropped/refused, never as facts.
- `GET /sources/{chunk_id}` failure degrades honestly to the verified
  quote with an "unavailable" note — chunk text is never fabricated.
- Backend still ignores `precheck`/`provided_values` and never populates
  `missing_info`/`confidence`/`contradictions` — UI derives client-side
  and labels it; `trace.dropped_reasons` (new in core hardening) now
  preferred in the verifier bar with source labelled.
- 118 tests green at latest commit.

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
- All: ports :8000/:8501 currently serve the tester's
  `/tmp/opencode/legal-agent-main` worktree — I stood my servers down
  while `main` is being checked; my UI stays demoable via fixtures.
- Core: if `missing_info` / `confidence` / `contradictions` /
  `provided_values` ever get backend support, my views consume them with
  no UI changes; until then the honest-degrade captions stay.

## UI Redesign & Updates (on `ui/streamlit`, pending merge)

- **Backend Draft Payload:** The UI now passes `draft_type` (template ID) and `doc_types` filter (via the sidebar) on `POST /answer` calls.
- **Draft Precheck parsing:** Switched to consuming `trace.field_status` (when the backend supplies it) for draft precheck summaries, gracefully falling back to the client-side derivation if missing.
- **List-style Answers:** Excluded the "exhaustive coverage" pseudo-missing field from the standard Missing Info panel and `still_needed_html`, instead rendering it clearly as a "List View" info banner.
- **Fallbacks & Protections Surfaced:** Added a banner to explicitly show `trace.backend` and `trace.fallbacks` on all screens so protections remain visible.
- **Compare View:** Added a new 📊 Compare tab that loads and renders `eval/results/compare.jsonl`, displaying our grounded pipeline against `baseline_no_verify`.
- **Docs & Pitch Rule:** Cleaned up prohibited phrases. Authored `docs/writeup.md` containing the 4-minute demo script and strictly adhering to the mandated pitch wording ("Every sentence is a claim whose key facts and quote are checked against the source...").

## Flags for other areas (not mine to fix)
- Core: The UI is now fully prepared for `trace.field_status` and `draft_type`. 
- Eval: `eval/results/compare.jsonl` is needed for the 📊 Compare tab to render properly; currently safely degrading with a "Not found" info banner if omitted.
