"""LLM entailment judge: does QUOTE clearly support claim TEXT?

Verdicts: "yes" (every factual element supported) / "no" / "partial".
Only a clear "yes" passes verification. Temperature 0. Judge model is
LLM_JUDGE_MODEL when set, else a different model from the generator so the
judge is not the generator parroting itself. Skipped under MockClient
(deterministic offline double has no judgement to offer) and whenever no
judge client can be built — the skip is reported, never silent.
"""

import re

from generation.config import get_llm_judge_model, get_llm_model, get_llm_provider


def is_mock_client(llm) -> bool:
    """MockClient (or no client) carries no entailment judgement."""
    return llm is None or type(llm).__name__ == "MockClient"


def get_judge_model(generator_model: str | None = None, provider: str | None = None) -> str:
    """LLM_JUDGE_MODEL wins; otherwise pick a model unlike the generator's."""
    forced = get_llm_judge_model()
    if forced:
        return forced
    provider = provider or get_llm_provider()
    gen = (generator_model or get_llm_model()).strip()
    if provider in ("openai_compatible", "openai"):
        return "gpt-4o" if gen != "gpt-4o" else "gpt-4o-mini"
    if provider == "gemini":
        return "gemini-1.5-flash" if gen != "gemini-1.5-flash" else "gemini-2.0-flash"
    return gen


def make_judge_client(llm) -> tuple:
    """Build a judge client for a generator llm.

    Returns (client, skip_reason): client is None when judgement is
    unavailable — caller must record skip_reason in Answer.trace.
    """
    if is_mock_client(llm):
        return None, "entailment skipped (MockClient)"
    try:
        from generation.llm import GeminiClient, OpenAICompatibleClient

        provider = get_llm_provider()
        gen_model = getattr(llm, "model", None) or get_llm_model()
        model = get_judge_model(gen_model, provider)
        if provider == "gemini":
            return GeminiClient(model=model, temperature=0), None
        if provider in ("openai_compatible", "openai"):
            return OpenAICompatibleClient(model=model), None  # temperature 0 fixed
        return None, f"entailment skipped (provider {provider})"
    except Exception as e:
        return None, f"entailment skipped (judge unavailable: {e})"


_JUDGE_TEMPLATE = (
    "You are a strict entailment judge. QUOTE is a verbatim source span; "
    "CLAIM is a statement allegedly drawn from it.\n"
    "Reply with exactly one word:\n"
    '- "yes" ONLY if every factual element of CLAIM (names, numbers, dates, '
    "sections, amounts, case names) is stated in or directly implied by QUOTE;\n"
    '- "no" if CLAIM contradicts QUOTE or adds facts QUOTE does not contain;\n'
    '- "partial" if some but not all of CLAIM is supported.\n'
    "QUOTE: {quote}\nCLAIM: {text}\nOne word:"
)


def judge_entailment(judge_client, quote: str, text: str) -> str:
    """Ask the judge; unparseable answers and errors are "skip", never "yes"."""
    try:
        raw = judge_client.complete_claims(
            _JUDGE_TEMPLATE.format(quote=quote, text=text)
        )
    except Exception:
        return "skip"
    m = re.search(r"\b(yes|no|partial)\b", (raw or "").strip().lower())
    return m.group(1) if m else "skip"
