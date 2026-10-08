"""Plain-RAG baseline: dense top-5 retrieval + one free-text prompt.

Unlike the grounded pipeline this system does NOT use structured claims or
the verifier: the LLM writes free text with citations in a single call.
Evaluation (not the pipeline) then splits the answer into atomic claims
with an LLM claim extractor and judges each claim against the retrieved
text with the INDEPENDENT judge (JUDGE_MODEL != LLM_MODEL).

Live-capable: generation uses the same live LLM as the pipeline
(LLM_PROVIDER/LLM_MODEL), the extractor uses the pipeline LLM, and claim
judging uses JUDGE_MODEL. With no key / offline / key invalid, every step
falls back deterministically and the mode is logged, so tables stay honest
about which numbers are live and which are mock-fallback.
"""

from __future__ import annotations

import re
import time

from contracts.schemas import Answer, Chunk, Citation, Doc
from verify.citations import resolve_raw
from workflows.answer import REFUSAL

PLAIN_RAG_TOP_K = 5

_CITE_RE = re.compile(r"\[([^\[\]]{1,120})\]")

# Probe cache: None = unprobed, True/False = live reachable or not.
_LIVE: dict[str, bool | None] = {"pipeline": None, "judge": None}


def pipeline_info() -> tuple[str, str]:
    """(provider, model) of the generation LLM — same as the pipeline uses."""
    from generation.config import get_llm_model, get_llm_provider

    return get_llm_provider(), get_llm_model()


def judge_info() -> str:
    from eval.judge import get_judge_model

    return get_judge_model()


def _pipeline_text(prompt: str, timeout: int = 20) -> str:
    """One raw text completion via the pipeline LLM. Raises without key/fail."""
    import generation.config  # noqa: F401  (loads .env)

    from generation.llm import make_client

    client = make_client()
    if type(client).__name__ == "MockClient":
        raise RuntimeError("mock provider has no free-text generation")
    return client.complete_claims(prompt)  # generic text completion over REST


def _judge_text(prompt: str, timeout: int = 20) -> str:
    """One raw completion via the INDEPENDENT judge model. Raises on fail."""
    import os

    import generation.config  # noqa: F401  (loads .env)

    from eval.judge import get_judge_model

    model = get_judge_model()  # raises if judge == pipeline LLM
    key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        # OpenAI-compatible judge path when only those vars are set.
        okey = os.getenv("OPENAI_API_KEY", "")
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not okey:
            raise RuntimeError("no judge key set")
        import requests

        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {okey}"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    import requests

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]},
                      timeout=timeout)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def live_reachable(which: str) -> bool:
    """Cached single-ping probe so tests/offline never pay per-call timeouts."""
    assert which in ("pipeline", "judge")
    if _LIVE[which] is None:
        try:
            if which == "pipeline":
                _pipeline_text("Reply with exactly: OK")
            else:
                _judge_text("Reply with exactly: OK")
            _LIVE[which] = True
        except Exception:
            _LIVE[which] = False
    return bool(_LIVE[which])


def build_plain_rag_prompt(question: str, chunks: list[Chunk]) -> str:
    src = "\n\n".join(
        f"[{c.chunk_id} | doc: {c.doc_id}] {c.text}" for c in chunks
    )
    return (
        "You are a legal assistant. Answer the QUESTION using the SOURCES below.\n"
        "Write a short free-text answer (2-5 sentences). Cite every factual "
        "statement with the source doc_id in square brackets, e.g. [my_doc]. "
        "If the sources do not contain the answer, say so honestly.\n\n"
        f"SOURCES:\n{src}\n\nQUESTION: {question}\n\nANSWER:"
    )


def mock_plain_text(question: str, chunks: list[Chunk]) -> str:
    """Deterministic offline stand-in: concatenates source sentences + cites.

    Copies whole first sentences (never truncates mid-sentence, never
    invents), so fallback numbers measure retrieval/refusal, not
    hallucination — the mode label makes this explicit.
    """
    lines = []
    for c in chunks[:PLAIN_RAG_TOP_K]:
        first = c.text.split(". ")[0].strip()
        if not first.endswith("."):
            first += "."
        lines.append(f"{first} [{c.doc_id}]")
    return " ".join(lines) if lines else REFUSAL


def complete_answer_text(prompt: str, question: str,
                         chunks: list[Chunk]) -> tuple[str, str]:
    """Free-text answer via the live pipeline LLM, else mock fallback."""
    provider, model = pipeline_info()
    if provider != "mock" and live_reachable("pipeline"):
        try:
            return _pipeline_text(prompt), f"{provider}-live:{model}"
        except Exception as e:
            return mock_plain_text(question, chunks), \
                f"mock-fallback({provider}-error:{e.__class__.__name__})"
    return mock_plain_text(question, chunks), "mock-fallback(no-live-llm)"


def retrieve_top5(question: str,
                  chunks: dict[str, Chunk]) -> tuple[list[Chunk], str]:
    """Hybrid (BM25 + dense when installed) top-5; lexical fallback offline."""
    vals = list(chunks.values())
    try:
        from retrieval.hybrid import HybridIndex

        idx = HybridIndex(vals)
        hits = idx.retrieve(question, top_k=PLAIN_RAG_TOP_K)
        backend = "hybrid-bm25+dense" if idx._dense_enabled() and idx._dense_ok \
            else "hybrid-bm25"
        return [c for c, _ in hits], backend
    except Exception as e:
        from retrieval.store import Registry

        r2 = Registry()
        for c in vals:
            if c.doc_id not in r2.docs:
                from contracts.schemas import Doc as _D

                r2.register_doc(_D(doc_id=c.doc_id, title=c.doc_id,
                                   doc_type="judgment"))
            r2.chunks[c.chunk_id] = c
        return r2.search(question, top_k=PLAIN_RAG_TOP_K), \
            f"lexical-fallback:{e.__class__.__name__}"


def parse_plain_citations(text: str, docs: dict[str, Doc],
                          chunks: list[Chunk]) -> list[Citation]:
    """Parse [doc_id] mentions; KEEP unresolved ones (they are fabrications)."""
    by_chunk = {c.chunk_id: c for c in chunks}
    out: list[Citation] = []
    seen: set[str] = set()
    for raw in _CITE_RE.findall(text):
        key = " ".join(raw.split())
        if not key or key in seen:
            continue
        seen.add(key)
        doc = None
        if key in docs:
            doc = docs[key]
        elif key in by_chunk and by_chunk[key].doc_id in docs:
            doc = docs[by_chunk[key].doc_id]
        else:
            doc = resolve_raw(key, docs)
        if doc is not None:
            out.append(Citation(cite_id=doc.doc_id, raw=key,
                                doc_id=doc.doc_id, resolved=True))
        else:
            out.append(Citation(cite_id=key, raw=key, doc_id=None,
                                resolved=False))
    return out


def run_plain_rag(question: str, docs: dict[str, Doc],
                  chunks: dict[str, Chunk],
                  workflow: str = "chat") -> Answer:
    """Dense top-5 + one free-text prompt. No claims, no verifier."""
    t0 = time.perf_counter()
    retrieved, backend = retrieve_top5(question, chunks)
    provider, model = pipeline_info()
    if not retrieved:
        ms = int((time.perf_counter() - t0) * 1000)
        return Answer(
            workflow=workflow,  # type: ignore[arg-type]
            text=REFUSAL,
            claims=[],
            citations=[],
            refused=True,
            refusal_reason="no retrieved chunks",
            trace={"retrieved_chunk_ids": [], "backend": backend,
                   "latency_ms": ms, "top_k": PLAIN_RAG_TOP_K,
                   "llm": f"{provider}:{model}", "unverified": True},
        )
    prompt = build_plain_rag_prompt(question, retrieved)
    text, llm_mode = complete_answer_text(prompt, question, retrieved)
    if not text.strip():
        text = REFUSAL
    chunk_map = {c.chunk_id: c for c in retrieved}
    citations = parse_plain_citations(text, docs, retrieved)
    _ = chunk_map
    ms = int((time.perf_counter() - t0) * 1000)
    trace = {"retrieved_chunk_ids": [c.chunk_id for c in retrieved],
             "backend": backend, "latency_ms": ms,
             "top_k": PLAIN_RAG_TOP_K, "llm": f"{provider}:{model}",
             "llm_mode": llm_mode, "unverified": True,
             "no_claims_no_verifier": True}
    refused = text.strip() == REFUSAL
    ans = Answer(
        workflow=workflow,  # type: ignore[arg-type]
        text=text,
        claims=[],
        citations=citations,
        refused=refused,
        refusal_reason=None if not refused else "model declined on sources",
        trace=trace,
    )
    ans.trace["plain_rag_eval"] = evaluate_plain_answer(
        text, citations, retrieved, docs)
    return ans


# -- eval-time claim extraction + independent judging -----------------------

_EXTRACT_PROMPT = (
    "Split the ANSWER below into atomic factual statements, one per line, "
    "numbered '1. ...'. Keep each statement short and self-contained. "
    "Output ONLY the numbered list, no prose.\n\nANSWER:\n{answer}"
)

_JUDGE_PROMPT = (
    "You judge groundedness. Claim:\n{claim}\n\nSources:\n{sources}\n\n"
    "Is every factual part of the claim stated in the sources? "
    "Reply with exactly SUPPORTED or NOT_SUPPORTED, nothing else."
)


def _sent_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", text.strip())
    claims = []
    for p in parts:
        p = p.strip().rstrip(".")
        # Skip citation-only / stub fragments ("[doc]", "NO. 45 OF 2023"):
        # they carry no factual claim and must not count as fabrications.
        bare = re.sub(r"\[[^\]]+\]", "", p).strip()
        if len(bare) < 20 or len(_content(bare)) < 4:
            continue
        claims.append(p)
    return claims


def extract_atomic_claims(answer_text: str) -> tuple[list[str], str]:
    """LLM extractor live; deterministic sentence split offline."""
    if answer_text.strip() == REFUSAL or not answer_text.strip():
        return [], "none(refused)"
    provider, _ = pipeline_info()
    if provider != "mock" and live_reachable("pipeline"):
        try:
            raw = _pipeline_text(_EXTRACT_PROMPT.format(answer=answer_text))
            lines = [re.sub(r"^\d+[\).\:\-]\s*", "", ln).strip()
                       for ln in raw.strip().splitlines() if ln.strip()]
            claims = [ln for ln in lines
                      if len(re.sub(r"\[[^\]]+\]", "", ln).strip()) >= 20][:12]
            if claims:
                _, model = pipeline_info()
                return claims, f"{provider}-live-extractor:{model}"
        except Exception:
            pass
    return _sent_split(answer_text)[:12], "mock-fallback(sent-split)"


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be but by for from has have in is it its of on or that the to was were will with".split()
)


def _content(s: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(s.lower()) if t not in _STOP}


def fallback_supported(claim: str, retrieved_texts: list[str]) -> bool:
    """Deterministic support check: verbatim span or >=50% token overlap."""
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s)
        return " ".join(s.split()).casefold()

    nq = norm(re.sub(r"\[[^\]]+\]", "", claim))
    if nq and any(nq in norm(t) for t in retrieved_texts):
        return True
    ct = _content(claim)
    if not ct:
        return False
    return any(len(ct & _content(t)) / len(ct) >= 0.5 for t in retrieved_texts)


def judge_claim_supported(claim: str,
                          retrieved_texts: list[str]) -> tuple[bool, str]:
    """Independent-judge support verdict live; overlap heuristic offline."""
    if live_reachable("judge"):
        try:
            src = "\n".join(f"- {t[:800]}" for t in retrieved_texts[:5])
            raw = _judge_text(_JUDGE_PROMPT.format(claim=claim, sources=src))
            verdict = raw.strip().upper()
            if "NOT_SUPPORTED" in verdict:
                return False, f"judge-live:{judge_info()}:NOT_SUPPORTED"
            if "SUPPORTED" in verdict:
                return True, f"judge-live:{judge_info()}:SUPPORTED"
        except Exception:
            pass
    texts = [re.sub(r"\[[^\]]+\]", "", t) for t in retrieved_texts]
    return fallback_supported(claim, texts), "mock-fallback(overlap>=0.5)"


def evaluate_plain_answer(answer_text: str, citations: list[Citation],
                          retrieved: list[Chunk],
                          docs: dict[str, Doc]) -> dict:
    """Atomic-claim eval of one plain-RAG answer. Pure data -> JSON-able dict."""
    if answer_text.strip() == REFUSAL or not answer_text.strip():
        return {"refused": True, "n_claims": 0, "n_supported": 0,
                "groundedness": 1.0, "unresolved_citations": 0,
                "fabrication": False, "claims": [], "supported": [],
                "extract_mode": "none(refused)", "judge_mode": "none(refused)"}
    claims, extract_mode = extract_atomic_claims(answer_text)
    texts = [c.text for c in retrieved]
    flags: list[bool] = []
    judge_modes: set[str] = set()
    for cl in claims:
        ok, jm = judge_claim_supported(cl, texts)
        flags.append(ok)
        judge_modes.add(jm.split(":")[0])
    unresolved = sum(1 for c in citations if not c.resolved)
    # A citation raw string that names no Doc is a fabrication even if the
    # prose claims are supported.
    fab = (any(not f for f in flags) if flags else True) or unresolved > 0
    grounded = (sum(flags) / len(flags)) if flags else 0.0
    return {"refused": False, "n_claims": len(claims),
            "n_supported": sum(flags), "groundedness": grounded,
            "unresolved_citations": unresolved, "fabrication": fab,
            "claims": claims, "supported": flags,
            "extract_mode": extract_mode,
            "judge_mode": "+".join(sorted(judge_modes)) or "none"}
