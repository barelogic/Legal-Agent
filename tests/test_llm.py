"""LLM config/factory: env-driven, mock default."""

import os

from generation.config import get_llm_model, get_llm_provider
from generation.llm import MockClient, make_client


def test_provider_default_mock(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert get_llm_provider() == "mock"
    assert isinstance(make_client(), MockClient)


def test_model_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini-2.0-flash")
    assert get_llm_model() == "gemini-2.0-flash"


def test_gemini_missing_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    try:
        make_client()
        assert False, "should raise"
    except RuntimeError:
        assert True
    finally:
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        os.environ.pop("LLM_PROVIDER", None)
