"""Runtime LLM configuration from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_llm_provider() -> str:
    """One of: mock | gemini | openai_compatible. Defaults to mock."""
    return os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"


def get_llm_model() -> str:
    return os.getenv("LLM_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def get_llm_judge_model() -> str:
    """LLM_JUDGE_MODEL when set, else "" (judge picks unlike the generator)."""
    return os.getenv("LLM_JUDGE_MODEL", "").strip()


def get_llm_temperature() -> float:
    """Claim-extraction temperature (LLM_TEMPERATURE, default 0.0).

    Structured-claim output must be deterministic: live-LLM answer/refuse
    flakiness on thin-corpus topics traces to sampling, not grounding.
    """
    try:
        return float(os.getenv("LLM_TEMPERATURE", "0.0"))
    except ValueError:
        return 0.0


def get_top_k(default: int = 4) -> int:
    try:
        return int(os.getenv("TOP_K", str(default)))
    except ValueError:
        return default


def get_rerank_min_score() -> float:
    """Cross-encoder cutoff: chunks scoring below are dropped (default 0.0,
    the logit sign boundary; P2 sweeps the real value on non-holdout data)."""
    try:
        return float(os.getenv("RERANK_MIN_SCORE", "0.0"))
    except ValueError:
        return 0.0


def get_min_coverage() -> float:
    """Min fraction of distinct query content tokens a chunk must contain.

    Default 0.32 from the allowed-split analysis (non-holdout queries, full
    1485-chunk corpus): lowest non-holdout answerable is 4/12=0.333 (q025),
    highest separable non-holdout trap is 4/13=0.308 (q007). P2 owns the
    real sweep; this default only promises no regression on that set.
    """
    try:
        return float(os.getenv("MIN_COVERAGE", "0.32"))
    except ValueError:
        return 0.32
