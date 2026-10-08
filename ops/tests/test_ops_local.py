"""Ops-local tests: env pins stay committable + loopback guard holds."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_env_example_pins_local_ollama():
    txt = (ROOT / "ops" / "env.local-llm.example").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=openai_compatible" in txt
    assert "LLM_MODEL=llama3.1:8b" in txt
    assert "http://localhost:11434/v1" in txt


def test_root_env_example_stays_nonlocal():
    txt = (ROOT / ".env.example").read_text(encoding="utf-8")
    for i, line in enumerate(txt.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        val = s.split("=", 1)[1].lower()
        assert "localhost" not in val and "11434" not in val, f".env.example:{i}"


def test_check_refuses_nonlocal(monkeypatch):
    from ops.check_local import is_loopback, ollama_tags

    assert is_loopback("http://localhost:11434/v1")
    assert is_loopback("http://127.0.0.1:11434/v1")
    assert not is_loopback("https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    try:
        ollama_tags()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected refusal on non-loopback base")
