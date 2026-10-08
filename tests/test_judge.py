"""Judge: mock skip, verdict parsing, model separation."""

from generation.llm import MockClient
from verify.judge import (
    get_judge_model,
    is_mock_client,
    judge_entailment,
    make_judge_client,
)


class _Yes:
    model = "gen-model"

    def complete_claims(self, prompt: str) -> str:
        assert "QUOTE" in prompt and "CLAIM" in prompt
        return "yes, fully supported"


class _Partial:
    model = "gen-model"

    def complete_claims(self, prompt: str) -> str:
        return "Partial support only."


def test_mock_skipped():
    assert is_mock_client(MockClient())
    client, reason = make_judge_client(MockClient())
    assert client is None and "Mock" in reason


def test_verdict_parsing():
    assert judge_entailment(_Yes(), "q", "t") == "yes"
    assert judge_entailment(_Partial(), "q", "t") == "partial"


def test_unparseable_is_skip_never_yes():
    class _Weird:
        def complete_claims(self, prompt: str) -> str:
            return "maybe, unclear"

    assert judge_entailment(_Weird(), "q", "t") == "skip"


def test_judge_model_differs_from_generator(monkeypatch):
    monkeypatch.setenv("LLM_JUDGE_MODEL", "")
    assert get_judge_model("gemini-2.0-flash", "gemini") != "gemini-2.0-flash"
    monkeypatch.setenv("LLM_JUDGE_MODEL", "custom-judge")
    assert get_judge_model("gemini-2.0-flash", "gemini") == "custom-judge"
