"""Prod path guards: Ollama stays dev-only; Gemini liveness/competence probe.

Offline (always run):
- committed `.env.example` never points at a loopback endpoint;
- config defaults are mock provider + public OpenAI base (no localhost);
- `live_progress._ollama_model` refuses non-loopback bases without a call.

Live (gated: GEMINI_LIVE_TEST=1 AND a GEMINI key present, else skipped):
- ping latency + a claims-format task over sample chunks (parses? quotes
  verbatim?). Prints timings so the runner can judge fast/competent.
"""

import os

import pytest

GEMINI_MODEL = os.getenv("GEMINI_TEST_MODEL", "gemini-3.5-flash-lite")
LIVE = bool(os.getenv("GEMINI_LIVE_TEST", ""))


def _gemini_key() -> str:
    import generation.config  # noqa: F401 (loads .env)

    from generation.config import get_gemini_key

    return get_gemini_key()


def test_committed_defaults_not_local():
    root = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
    example = (root / ".env.example").read_text(encoding="utf-8")
    for i, line in enumerate(example.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        val = s.split("=", 1)[1].lower()
        assert "localhost" not in val and "127.0.0.1" not in val and \
            "11434" not in val, f".env.example:{i} points at loopback: {s}"


def test_config_defaults_not_local(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_BASE_URL",
                "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from generation.config import get_llm_provider
    from generation.llm import OpenAICompatibleClient

    assert get_llm_provider() == "mock"
    c = OpenAICompatibleClient(model="x", api_key="x")
    assert "localhost" not in c.base_url and "11434" not in c.base_url


def test_progress_watcher_skips_nonlocal(monkeypatch):
    from eval.live_progress import _ollama_model

    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    assert _ollama_model().startswith("n/a")


live_only = pytest.mark.skipif(
    not (LIVE and _gemini_key()),
    reason="needs GEMINI_LIVE_TEST=1 + a GEMINI key in env/.env",
)


@live_only
def test_prod_gemini_ping_latency():
    import time

    import generation.config  # noqa: F401
    from generation.llm import GeminiClient

    t0 = time.perf_counter()
    out = GeminiClient(model=GEMINI_MODEL).complete_claims("Reply with exactly: OK")
    ms = (time.perf_counter() - t0) * 1000
    print(f"\n[PROD] {GEMINI_MODEL} ping: {ms:.0f}ms reply={out.strip()[:20]!r}")
    assert "OK" in out


@live_only
def test_prod_gemini_claims_competence():
    import time

    import generation.config  # noqa: F401
    from contracts.schemas import Chunk
    from generation.claims import build_prompt, parse_claims
    from generation.llm import GeminiClient

    chunks = [
        Chunk(chunk_id="c1", doc_id="d1",
              text="A person arrested for a bailable offence must be released on bail."),
        Chunk(chunk_id="c2", doc_id="d1",
              text="The surety bond shall not exceed the amount fixed by the Magistrate."),
    ]
    t0 = time.perf_counter()
    raw = GeminiClient(model=GEMINI_MODEL).complete_claims(
        build_prompt("When must a bailable arrestee be released?", chunks))
    ms = (time.perf_counter() - t0) * 1000
    claims = parse_claims(raw)
    verbatim = [c for c in claims
                if any(c.quote and c.quote in ch.text for ch in chunks)]
    print(f"\n[PROD] {GEMINI_MODEL} claims: {ms:.0f}ms "
          f"parsed={len(claims)} verbatim={len(verbatim)}")
    assert claims, f"no parsable claims. raw={raw[:300]!r}"
    assert verbatim, f"no verbatim quote. raw={raw[:300]!r}"
