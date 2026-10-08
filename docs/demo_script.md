# Demo script (4 minutes) + integration log

Backend: `python -m uvicorn api.main:app` (default `http://localhost:8000`).
UI: `python -m pip install -r requirements.txt -r ui/requirements.txt`
then `streamlit run ui/app.py`. One-click **Reset session** in the sidebar
clears all answers, inputs and selections between beats.

## Beats (4:00)

1. **Upload unseen file (0:00–0:45).** Sidebar → Upload a `.txt` case file
   (`doc_type=case_file`) → success caption shows `doc_id` + chunk count;
   the doc appears in the corpus list. Bad responses surface per-file errors.
2. **Precheck (0:45–1:30).** Draft tab → pick `bail_application` → paste the
   FIR question → **Run precheck** (`precheck=true`). Read the Draft
   Readiness bar: "N of M required fields sourced", confidence, and the
   missing list with field / why-needed / searched docs.
3. **Supply one value + draft (1:30–2:20).** Type `0123/2024` into the FIR
   number box → **Draft with provided values**. Draft view: sourced runs
   underlined (hover = verbatim quote), red `[MISSING: …]`, amber
   `[USER-PROVIDED: 0123/2024]`. Note the caption: this backend ignores
   `provided_values`, so sourcing is unchanged — values are input, not facts.
4. **Two source chips (2:20–3:00).** Click two `[cN]` chips → source panel
   shows claim + quote + full chunk with `<mark>` highlight and doc link.
5. **Trap refusal (3:00–3:20).** Research tab → nonsense/off-corpus query →
   red `Not found in the provided sources` + reason + verifier bar.
6. **Compare (3:20–3:50).** 📊 Compare tab → pick a query: grounded answer
   vs baseline with its fabricated-claim count expanded. Source label says
   measured eval file or hand-built sample (illustrative, never measured).
7. **Fallback (3:50–4:00).** Sidebar → **Use fixtures**: all tabs serve
   bundled Answers with zero backend. **Reset session** before Q&A.

Pitch line: "Every sentence is a claim whose key facts and quote are checked
against the source, with the quote shown beside it."

## Integration log — 3 unseen docs (2026-10-09, backend `:8001`, live Gemini)

Files: `/tmp/opencode/u6docs/` (`case_theft_047.txt`, `case_assault_109.txt`,
`remand_note_22.txt`). Upload: 3/3 ingested, 1 chunk each, doc_ids as named.

- `POST /answer` draft + `doc_ids=["case_theft_047"]` → **refused**, 0 claims,
  `missing=[supporting evidence]`. Repro:
  `curl -X POST 127.0.0.1:8001/answer -d '{"question":"Draft a bail prayer for FIR 0047/2025.","workflow":"draft","top_k":4,"doc_ids":["case_theft_047"]}'`
  → owner: **user1** (live-LLM zero-candidate nondeterminism on thin corpus;
  refusal honest, no grounding violation).
- `POST /answer` review + `doc_ids=["case_assault_109"]` → 1 verified claim
  (`no recovery…` context). `GET /sources/case_assault_109::p1::c0` → 200.
- `POST /answer` draft + `precheck:true` + `provided_values` on
  `remand_note_22` → 3 claims, flags accepted-and-ignored as designed.
- `top_k=0` → 422 (core validation holds; UI `number_input` already min 1).
- No UI-side failures: chips, panel, export and fixture paths unaffected.

## Backup cases (ingested + tested, no upload needed)

1. Seeds: `case_file_demo` (FIR 0123/2024 — joined investigation, no
   recovery), `bnss_2023` (bail discretion), `sc_bail_2022` (Antil arrest rule).
2. Above 3 u6 docs on the `:8001` backend (my worktree `data/`).
3. Fixtures toggle: `chat` / `precheck` / `draft` / `review` / `refusal` +
   compare sample — works with no backend at all.
