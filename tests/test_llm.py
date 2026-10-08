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


def test_openai_malformed_wrapped(monkeypatch):
    from generation.llm import OpenAICompatibleClient

    class _BadResp:
        text = '{"oops": 1}'

        def raise_for_status(self):
            pass

        def json(self):
            return {"oops": 1}

    import generation.llm as llm_mod

    monkeypatch.setattr(llm_mod.requests, "post", lambda *a, **k: _BadResp())
    c = OpenAICompatibleClient(model="m", api_key="k", base_url="http://x")
    try:
        c.complete_claims("hi")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "unexpected OpenAI-compatible response" in str(e)


def test_temperature_default_zero(monkeypatch):
    from generation.config import get_llm_temperature

    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    assert get_llm_temperature() == 0.0
    monkeypatch.setenv("LLM_TEMPERATURE", "junk")
    assert get_llm_temperature() == 0.0
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    assert get_llm_temperature() == 0.7


def test_gemini_sends_temperature_zero(monkeypatch):
    import generation.llm as llm_mod
    from generation.llm import GeminiClient

    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    seen = {}

    class _GoodResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

    def _post(url, json=None, **k):
        seen.update(json or {})
        return _GoodResp()

    monkeypatch.setattr(llm_mod.requests, "post", _post)
    c = GeminiClient(model="m", api_key="k")
    assert c.complete_claims("hi") == "[]"
    assert seen["generationConfig"] == {"temperature": 0.0}


def test_make_client_honors_temperature_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    try:
        assert make_client().temperature == 0.7
    finally:
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("LLM_TEMPERATURE", None)


def test_trace_records_llm_policy(monkeypatch):
    from contracts.schemas import Chunk, Doc
    from retrieval.store import Registry
    from workflows.answer import answer_question

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    reg = Registry()
    reg.register_doc(Doc(doc_id="d", title="D", doc_type="statute"))
    reg.chunks["d::p1::c0"] = Chunk(
        chunk_id="d::p1::c0", doc_id="d",
        text="The surety stands in the sum of Rs. 50,000.")
    ans = answer_question("What sum stands as surety?", "chat", reg, MockClient())
    assert ans.trace["llm"]["provider"] == "mock"
    assert ans.trace["llm"]["temperature"] == "mock (deterministic)"


def test_mock_first_sentence_skips_abbreviations():
    import json as _json

    from contracts.schemas import Chunk
    from generation.llm import MockClient

    ch = Chunk(chunk_id="d::p1::c0", doc_id="d",
               text="FIR No. 0451/2024 records that Rs. 50,000 stood deposited. Next event.")
    out = _json.loads(MockClient(chunks=[ch]).complete_claims("q"))
    assert out[0]["text"] == "FIR No. 0451/2024 records that Rs. 50,000 stood deposited"
