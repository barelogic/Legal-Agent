# AGENTS.md — working rules for this repo

24-hour hackathon: agentic legal assistant where every fact and citation must
be traceable to a retrieved source. A single fabricated fact fails us.

## Who works here

| User | Area | Branch |
| --- | --- | --- |
| Core (phase 1 owner) | `api/ contracts/ generation/ ingest/ retrieval/ verify/ workflows/` | `main` |
| user2 | eval harness + general data work (`eval/`, `data/` seeds/corpus) | `main` for now → own branch soon |
| user3 | UI (new `ui/` dir) | own branch |

All commits share one git username, so **branches — not authors — separate work**.
user2: move off `main` as soon as your eval scaffold exists.

## Non-negotiable grounding policy

- `contracts/schemas.py` is frozen. Never edit it. Ask before any change
  that alters a contract.
- The LLM outputs structured claims only (`text, chunk_ids, quote`); final
  text is rendered FROM verified claims, never from model free text.
- Any claim failing verification is dropped. Nothing survives → refuse with
  `Not found in the provided sources`. Prefer refusal to guessing.
- Citations allowed only if they resolve to a `Doc` in the registry.
- Never let the model recall laws/cases from memory.

## Environment

- venv at `.venv`; always use `python -m pip/pytest/uvicorn` (never system pip).
- fish shell: `source .venv/bin/activate.fish` (bash `activate` will not parse).
- LLM backend via env: `LLM_PROVIDER=mock|gemini|openai_compatible`, `LLM_MODEL`,
  keys in `.env` (never commit `.env`).

## Code standards

- Small typed modules with docstrings; one tiny pytest per module.
- Heavy ML deps stay optional with graceful lexical fallback (E2E over polish).
- New top-level dirs (`eval/`, `ui/`) are fine; do not restructure existing ones.
- Do not commit runtime artifacts: `data/processed/`, `data/uploads/`,
  `data/chroma/`, `.venv/`, `__pycache__/`.

## Before every commit / push

- `.venv/bin/python -m pytest tests/ -q` is green.
- `contracts/schemas.py` untouched (`git diff -- contracts/schemas.py` empty).
- Stay on your branch; `main` takes merges, not direct feature work.
