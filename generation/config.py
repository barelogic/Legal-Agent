"""Runtime LLM configuration from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_llm_provider() -> str:
    """One of: mock | gemini | openai_compatible. Defaults to mock."""
    return os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"


def get_llm_model() -> str:
    return os.getenv("LLM_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"


def get_gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")


def get_top_k(default: int = 4) -> int:
    try:
        return int(os.getenv("TOP_K", str(default)))
    except ValueError:
        return default
