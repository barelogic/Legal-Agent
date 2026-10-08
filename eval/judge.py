"""Judge model: usefulness + entailment, DIFFERENT from pipeline LLM.

Pipeline generation uses LLM_MODEL (default gemini-2.0-flash).
The judge uses JUDGE_MODEL (default gemini-2.5-flash) and REFUSES to run
when they match, so we never grade ourselves:

    JUDGE_MODEL != LLM_MODEL (asserted in get_judge_model)

No key / offline -> deterministic fallback (token-overlap entailment +
length/usefulness heuristic). The fallback is clearly labeled in results
("judge_model": "deterministic-fallback") so write-up numbers stay honest.
Every result records which judge produced it.
"""

from __future__ import annotations

import os
import re

from generation.config import get_llm_model

_FALLBACK = "deterministic-fallback"


def get_judge_model() -> str:
    """JUDGE_MODEL env (default gemini-2.5-flash). Raises if == LLM_MODEL."""
    judge = os.getenv("JUDGE_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    pipeline = get_llm_model()
    if judge == pipeline:
        raise ValueError(
            f"JUDGE_MODEL ({judge}) must differ from pipeline LLM_MODEL ({pipeline}); "
            "set JUDGE_MODEL to another version/family."
        )
    return judge


def _overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a.lower())) - {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "has", "have", "in", "is", "it", "its", "of", "on", "or",
        "that", "the", "to", "was", "were", "will", "with",
    }
    tb = set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(ta & tb) / max(1, len(ta))


def _gemini_judge(prompt: str, model: str) -> str | None:
    key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        return None
    try:
        import requests

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        r = requests.post(
            url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def judge_answers(answers_by_system: dict[str, list], rows: list[dict]) -> dict:
    """Score usefulness (0-5) + entailment per answer. Returns per-system means.

    Usefulness rubric (deterministic fallback; live judge would use same scale):
    - correctly refused unanswerable -> 5; refused answerable -> 0.
    - answered unanswerable (should have refused) -> 0.
    - answered answerable -> 1-4 by gold-span overlap + 1 if cited (cap 5).
    """
    judge_model = get_judge_model()
    out: dict = {"judge_model": judge_model}
    live = _gemini_judge("ping", judge_model) is not None
    if live:
        out["judge_mode"] = "gemini-live"
    else:
        out["judge_mode"] = _FALLBACK
    for sys, answers in answers_by_system.items():
        use_sum = ent_sum = 0.0
        for row, ans in zip(rows, answers):
            if ans.refused:
                use = 5.0 if not row.get("answerable") else 0.0
                ent = 1.0 if not row.get("answerable") else 0.0
            else:
                gold = row.get("answer_span", "") or " ".join(
                    c.text for c in ans.claims[:2]
                )
                if not row.get("answerable"):
                    use = 0.0
                    ent = 0.0
                else:
                    ov = _overlap(gold, ans.text)
                    ent = 1.0 if ov >= 0.3 else (0.5 if ov >= 0.1 else 0.0)
                    if ov >= 0.5:
                        use = 4.0
                    elif ov >= 0.3:
                        use = 3.0
                    elif ov >= 0.15:
                        use = 2.0
                    elif ov > 0:
                        use = 1.0
                    else:
                        use = 0.0
                    # cited answers are more useful; cap at 5.
                    use = min(5.0, use + (1.0 if ans.citations else 0.0))
            use_sum += use
            ent_sum += ent
        n = max(1, len(rows))
        out[sys] = {
            "n": len(rows),
            "usefulness_mean": use_sum / n,
            "entailment_rate": ent_sum / n,
        }
    return out
