# 2-minute judge demo

Backend first (terminal 1):

```bash
source .venv/bin/activate.fish  # or: source .venv/bin/activate
python -m uvicorn api.main:app
```

UI (terminal 2):

```bash
source .venv/bin/activate.fish
python -m pip install -r ui/requirements.txt
streamlit run ui/app.py
```

## Clicks (in order)

1. **"Bail in non-bailable offences?"** → 1+ verified claim cards, each with
   verbatim quote + `bnss_2023` chunk link. Point at Sources list.
2. **"Antil (2022) arrest rule"** → judgment claim from `sc_bail_2022`.
3. **"FIR 0123/2024 status"** → case-file facts (transfer date, joined
   investigation, no recovery pending).
4. **"Refusal demo (off-corpus)"** → big red `Not found in the provided
   sources` banner + reason. This is the honesty proof.
5. (If time) Sidebar → upload a `.txt` (`case_file`), re-ask — new doc
   appears in corpus list and answers cite it.

## What to say

- "Final text is rendered FROM verified claims only — model free text is
  never shown."
- "No chunk + verbatim quote, no fact. Failures land in the dropped-claims
  audit, refusals stay prominent."
