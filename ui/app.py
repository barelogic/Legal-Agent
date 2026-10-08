"""Streamlit UI: grounded legal assistant (judge-friendly).

Screens: (1) sidebar — upload documents (POST /ingest) + case-set picker;
(2) tabs for Chat / Draft / Review / Research; (3) result view with
clickable [cN] evidence chips opening a source side panel.

Only the API base URL has to change to switch mock -> real backend
(env API_BASE_URL or the sidebar field). Every fact renders from verified
claims with quote + chunk link; refusals and missing-info stay prominent.
"""

from __future__ import annotations

import inspect

import streamlit as st

from contracts.schemas import Answer
from ui import api_client
from ui.render import (
    TEMPLATE_IDS,
    USER_VALUE_CSS,
    citation_to_markdown,
    claim_markers,
    confidence_text,
    contradiction_view_model,
    diff_sides,
    docs_by_id,
    draft_html,
    dropped_claims,
    highlight_quote,
    load_template,
    precheck_summary,
    source_label,
    split_text_markers,
    status_badge,
    still_needed_html,
    user_value_html,
    verifier_bar_html,
    verifier_summary,
    verified_claims,
)

WORKFLOWS = ["chat", "draft", "review", "research"]
DOC_TYPES = ["statute", "judgment", "case_file"]
PRESETS: dict[str, str] = {
    "chat": "bail in non-bailable offences?",
    "draft": "Draft a bail prayer using only the sources for FIR 0123/2024.",
    "review": "FIR 0123/2024 — is recovery pending, did the accused join investigation?",
    "research": "What did Satender Kumar Antil v. CBI (2022) hold on arrest?",
}


def _fill_example(workflow: str) -> None:
    """Streamlit click-callback: preset the question box.

    Runs as an ``on_click`` callback (before the next script run), which is
    the only legal moment to write a widget-backed ``session_state`` key —
    writing it after the ``text_area`` is instantiated raises
    ``StreamlitWidgetAlreadyInstantiatedError`` on repeat clicks.
    """
    st.session_state[f"q-{workflow}"] = PRESETS[workflow]


# ``st.dataframe(width=...)`` replaced ``use_container_width`` in newer
# Streamlit; resolve once so the app runs on both old and new versions.
_DATAFRAME_KWARGS: dict = (
    {"width": "stretch"}
    if "width" in inspect.signature(st.dataframe).parameters
    else {"use_container_width": True}
)


def _base() -> str:
    return st.session_state.get("api_base", api_client.base_url())


def _sidebar() -> tuple[dict, dict]:
    st.sidebar.title("Backend")
    st.sidebar.text_input("API base URL (mock → real switch)", value=_base(), key="api_base")
    base = _base()
    try:
        health = api_client.get_health(base)
        st.sidebar.success(f"● OK · {health.get('docs')} docs, {health.get('chunks')} chunks")
    except RuntimeError as e:
        st.sidebar.error(str(e))
        st.sidebar.caption("Start backend: `python -m uvicorn api.main:app`")
    try:
        docs = api_client.list_docs(base)
    except RuntimeError as e:
        st.sidebar.warning(str(e))
        docs = []
    by_id = docs_by_id(docs)

    st.sidebar.header("1 · Documents & case set")
    with st.sidebar.expander("📤 Upload (POST /ingest)", expanded=False):
        ups = st.file_uploader("PDF or TXT", type=["pdf", "txt"], accept_multiple_files=True)
        dtype = st.selectbox("doc_type", DOC_TYPES, index=2)
        if st.button("Ingest", disabled=not ups):
            ok, fail = 0, []
            with st.spinner("Ingesting…"):
                for f in ups or []:
                    try:
                        res = api_client.post_ingest(f.name, f.getvalue(), dtype, base=base)
                        ok += 1
                    except RuntimeError as e:
                        fail.append(f"{f.name}: {e}")
            if ok:
                st.sidebar.success(f"Ingested {ok} file(s)")
            for m in fail:
                st.sidebar.error(m)
            st.rerun()
    st.sidebar.caption("Corpus")
    for d in docs:
        extra = f" · {d.citation}" if d.citation else ""
        st.sidebar.caption(f"`{d.doc_id}` — {d.title} ({d.doc_type}){extra}")
    known = [d.doc_id for d in docs]
    current = [c for c in st.session_state.get("case_set", []) if c in known]
    st.sidebar.multiselect(
        "Case set (doc_ids filter, empty = all)",
        known,
        default=current,
        key="case_set",
    )
    cols = st.sidebar.columns(2)
    if cols[0].button("All docs"):
        st.session_state["case_set"] = []
        st.rerun()
    top_k = cols[1].number_input("top_k", 1, 10, 4, step=1)
    st.session_state["top_k"] = int(top_k)
    return by_id, {"docs": docs}


def _ask_tab(workflow: str, by_id: dict) -> None:
    st.text_area("Question", key=f"q-{workflow}", height=80,
                placeholder=PRESETS[workflow])
    if workflow == "draft":
        st.selectbox("Template (precheck field list)", list(TEMPLATE_IDS),
                     key="template-draft")
    c1, c2 = st.columns([1, 3])
    if c1.button("Ask", key=f"ask-{workflow}", type="primary"):
        q = st.session_state.get(f"q-{workflow}", "").strip()
        if not q:
            st.warning("Type a question first.")
            return
        try:
            with st.spinner("Retrieving → claiming → verifying…"):
                ans = api_client.post_answer(
                    q, workflow=workflow,  # type: ignore[arg-type]
                    top_k=st.session_state.get("top_k", 4),
                    doc_ids=st.session_state.get("case_set") or None,
                    base=_base(),
                )
            st.session_state.setdefault("answers", {})[workflow] = ans.model_dump()
            st.session_state.setdefault("questions", {})[workflow] = q
            st.session_state.pop("selected", None)
        except RuntimeError as e:
            st.error(str(e), icon="⛔")
    if workflow == "draft":
        if c1.button("Run precheck", key="precheck-draft"):
            q = st.session_state.get("q-draft", "").strip()
            if not q:
                st.warning("Type a question first.")
            else:
                try:
                    with st.spinner("Prechecking draft readiness…"):
                        ans = api_client.post_answer(
                            q, workflow="draft",
                            top_k=st.session_state.get("top_k", 4),
                            doc_ids=st.session_state.get("case_set") or None,
                            precheck=True,
                            base=_base(),
                        )
                    st.session_state.setdefault("answers", {})["draft"] = ans.model_dump()
                    st.session_state.setdefault("questions", {})["draft"] = q
                    st.session_state.pop("selected", None)
                except RuntimeError as e:
                    st.error(str(e), icon="⛔")
    c2.button("Fill example", key=f"preset-{workflow}",
              on_click=_fill_example, args=(workflow,))
    saved = (st.session_state.get("answers") or {}).get(workflow)
    if saved:
        st.divider()
        asked = (st.session_state.get("questions") or {}).get(workflow, "")
        if asked:
            st.markdown(user_value_html(asked), unsafe_allow_html=True)
            st.caption("Above: your question — not a sourced fact.")
        _render_result(Answer(**saved), by_id, workflow)


def _render_claim_text_with_chips(answer: Answer, workflow: str) -> None:
    """Render Answer.text; each [cN] marker gets a clickable chip button."""
    markers = claim_markers(answer.text)
    st.markdown(f"_Answer text (workflow `{answer.workflow}`):_")
    buf = ""
    chips: list[str] = []

    def flush(t: str) -> None:
        if t.strip():
            st.markdown(t)

    for seg, cid in split_text_markers(answer.text):
        if cid is None:
            buf += seg
        else:
            buf += f" **[{cid}]**"
            chips.append(cid)
    flush(buf)
    if chips:
        st.caption("Evidence chips — click to inspect the source:")
        cols = st.columns(min(len(chips), 8))
        for i, cid in enumerate(chips):
            if cols[i % len(cols)].button(f"[{cid}]", key=f"chip-{workflow}-{cid}-{i}"):
                st.session_state["selected"] = {"workflow": workflow, "claim_id": cid}


def _render_source_panel(answer: Answer, by_id: dict, workflow: str) -> None:
    sel = st.session_state.get("selected")
    with st.container(border=True):
        st.subheader("Source panel")
        if not sel or sel.get("workflow") != workflow:
            st.caption("Click an evidence chip ([cN]) to inspect its source chunk.")
            return
        cid = sel["claim_id"]
        claim = next((c for c in answer.claims if c.claim_id == cid), None)
        if claim is None:
            st.warning(f"Claim `{cid}` not in this Answer.")
            return
        st.markdown(f"**[{claim.claim_id}] {status_badge(claim.status)}**")
        st.markdown(claim.text)
        st.markdown(f"> {claim.quote}")
        if claim.verifier_note:
            st.caption(f"Verifier: {claim.verifier_note}")
        for chunk_id in claim.chunk_ids:
            st.divider()
            try:
                chunk = api_client.get_source(chunk_id, base=_base())
                doc = by_id.get(chunk.doc_id)
                st.markdown(f"**{doc.title if doc else chunk.doc_id}**" + (f" · p.{chunk.page}" if chunk.page else ""))
                if chunk.section_label:
                    st.caption(chunk.section_label)
                if doc and doc.source_url:
                    st.markdown(f"[open source]({doc.source_url})")
                else:
                    st.caption("Local doc — no external link.")
                st.markdown(
                    highlight_quote(chunk.text, claim.quote),
                    unsafe_allow_html=True,
                )
            except RuntimeError:
                from ui.render import doc_id_of_chunk

                doc = by_id.get(doc_id_of_chunk(chunk_id))
                st.caption(f"📄 {source_label(chunk_id, by_id)}")
                if doc and doc.source_url:
                    st.markdown(f"[open source]({doc.source_url})")
                else:
                    st.caption("Local doc — no external link.")
                st.markdown(f"> {claim.quote}")
                st.caption(
                    "Full chunk fetch unavailable "
                    f"(GET /sources/{chunk_id} not on this backend) — "
                    "showing the verified quote instead."
                )
        if st.button("Close panel", key=f"close-{workflow}"):
            st.session_state.pop("selected", None)
            st.rerun()


def _render_precheck_card(answer: Answer) -> None:
    """Precheck screen: N-of-M fields, confidence, missing list (draft)."""
    try:
        template = load_template(st.session_state.get("template-draft", TEMPLATE_IDS[0]))
    except ValueError as e:
        st.error(str(e))
        return
    summary = precheck_summary(answer, template)
    st.subheader("Precheck — draft readiness")
    st.markdown(
        f"**{summary['sourced_n']} of {summary['total']} required fields sourced** "
        f"(`{summary['template_id']}`)"
    )
    st.caption(
        "“Sourced” = required field the backend did not flag in "
        "`missing_info`. Requested with `precheck=true`; the backend does "
        "not implement it yet, so readiness is derived client-side."
    )
    if summary["unconfirmed"]:
        st.caption("⚠️ Backend returned no missing-info list — counts are unconfirmed.")
    st.markdown(confidence_text(answer))
    for row in summary["rows"]:
        badge = "✅" if row["status"] == "sourced" else "⚠️"
        line = f"{badge} **{row['name']}** — {row['status']}"
        if row["why_needed"]:
            line += f": {row['why_needed']}"
        if row["searched_in"]:
            searched = ", ".join(f"`{d}`" for d in row["searched_in"])
            line += f" (searched: {searched})"
        st.markdown(f"- {line}")


def _render_missing_panel(answer: Answer, workflow: str) -> dict[str, str]:
    """One input box per missing field; returns current non-empty values."""
    st.subheader("Missing info — supply values")
    st.caption(
        "Values are echoed below as user input, never as sourced facts. "
        "Sent back as `provided_values` (forward-compatible — the backend "
        "does not consume them yet)."
    )
    for m in answer.missing_info:
        st.text_input(m.field, key=f"pv-{workflow}-{m.field}", help=m.why_needed)
        searched = ", ".join(f"`{d}`" for d in m.searched_in) or "_nothing searched_"
        st.caption(f"{m.why_needed} (searched: {searched})")
    return {
        m.field: (st.session_state.get(f"pv-{workflow}-{m.field}", "") or "").strip()
        for m in answer.missing_info
    }


def _render_draft_view(answer: Answer, workflow: str, provided: dict[str, str]) -> None:
    """Draft: underlined sourced sentences + chips, placeholders, user vals."""
    st.subheader("Draft")
    st.markdown(draft_html(answer), unsafe_allow_html=True)
    chips = claim_markers(answer.text)
    if chips:
        st.caption("Evidence chips — click to inspect the source:")
        cols = st.columns(min(len(chips), 8))
        for i, cid in enumerate(chips):
            if cols[i % len(cols)].button(f"[{cid}]", key=f"dchip-{workflow}-{cid}-{i}"):
                st.session_state["selected"] = {"workflow": workflow, "claim_id": cid}
    need = still_needed_html(answer, provided)
    if need:
        st.markdown("**Still needed:**")
        st.markdown(need, unsafe_allow_html=True)
        st.caption("Red = unsourced placeholder · amber = your input, not a fact.")


def _render_verifier_bar(answer: Answer) -> None:
    summary = verifier_summary(answer)
    st.markdown(verifier_bar_html(summary), unsafe_allow_html=True)
    if summary["dropped_reasons"]:
        with st.expander(f"Dropped reasons ({len(summary['dropped_reasons'])})"):
            for r in summary["dropped_reasons"]:
                st.caption(r)
            st.caption(f"Reasons from {summary['reasons_source']}.")


def _render_contradictions(answer: Answer) -> None:
    for k in answer.contradictions:
        with st.container(border=True):
            st.markdown(f"**{k.description}**")
            fetched: dict[str, object | None] = {}
            for cid in (k.claim_a, k.claim_b):
                try:
                    fetched[cid] = api_client.get_source(cid, base=_base())
                except RuntimeError:
                    fetched[cid] = None
            vm = contradiction_view_model(k, fetched)
            if vm["text_a"] is None or vm["text_b"] is None:
                st.markdown(f"`{k.claim_a}` vs `{k.claim_b}`")
                st.caption(
                    "Chunk fetch unavailable for one or both sides "
                    "(GET /sources failed) — showing ids only, no text invented."
                )
            else:
                left, right = st.columns(2)
                ha, hb = diff_sides(str(vm["text_a"]), str(vm["text_b"]))
                with left:
                    st.caption(f"📄 `{k.claim_a}`")
                    st.markdown(ha, unsafe_allow_html=True)
                with right:
                    st.caption(f"📄 `{k.claim_b}`")
                    st.markdown(hb, unsafe_allow_html=True)
                st.caption("Differing words highlighted; identical words plain.")


def _render_result(answer: Answer, by_id: dict, workflow: str) -> None:
    if answer.refused:
        st.error(f"⛔ Refused: {answer.text}", icon="⛔")
        if answer.refusal_reason:
            st.markdown(f"**Reason:** {answer.refusal_reason}")
        _render_verifier_bar(answer)
        with st.expander("Trace (debug)"):
            st.json(answer.trace)
        bad = dropped_claims(answer)
        if bad:
            with st.expander(f"Dropped claims audit ({len(bad)})"):
                for c in bad:
                    st.caption(f"`{c.claim_id}` [{c.status}] {c.text}")
        return

    if answer.missing_info:
        st.warning("⚠️ Missing information needed for a complete answer", icon="⚠️")
        for m in answer.missing_info:
            searched = ", ".join(f"`{d}`" for d in m.searched_in) or "_nothing searched_"
            st.markdown(f"- **{m.field}** — {m.why_needed} (searched: {searched})")
    if answer.contradictions:
        st.error("Contradictions found between sources", icon="🚨")
        _render_contradictions(answer)
    _render_verifier_bar(answer)

    if workflow == "draft":
        _render_precheck_card(answer)
        provided: dict[str, str] = {}
        if answer.missing_info:
            provided = _render_missing_panel(answer, workflow)
            if st.button("Draft with provided values", key=f"redraft-{workflow}"):
                vals = {k: v for k, v in provided.items() if v}
                try:
                    with st.spinner("Re-drafting with your values…"):
                        ans = api_client.post_answer(
                            st.session_state.get(f"q-{workflow}", ""),
                            workflow="draft",  # type: ignore[arg-type]
                            top_k=st.session_state.get("top_k", 4),
                            doc_ids=st.session_state.get("case_set") or None,
                            provided_values=vals or None,
                            base=_base(),
                        )
                    st.session_state.setdefault("answers", {})[workflow] = ans.model_dump()
                    st.session_state.pop("selected", None)
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e), icon="⛔")
        _render_draft_view(answer, workflow, provided)

    left, right = st.columns([3, 2])
    with left:
        _render_claim_text_with_chips(answer, workflow)
        st.subheader("Claims")
        rows = [
            {
                "claim": c.claim_id,
                "status": status_badge(c.status),
                "text": c.text,
                "chunks": ", ".join(c.chunk_ids),
            }
            for c in answer.claims
        ]
        st.dataframe(rows, hide_index=True, **_DATAFRAME_KWARGS)
        if answer.citations:
            st.subheader("Sources")
            for cite in answer.citations:
                st.markdown(f"- {citation_to_markdown(cite, by_id)}")
        good = verified_claims(answer)
        st.caption(f"{len(good)} verified / {len(answer.claims)} total claims.")
        if answer.trace:
            with st.expander("Trace (debug)"):
                st.json(answer.trace)
    with right:
        _render_source_panel(answer, by_id, workflow)


def main() -> None:
    st.set_page_config(page_title="Grounded Legal Assistant", layout="wide")
    st.markdown(USER_VALUE_CSS, unsafe_allow_html=True)
    st.title("⚖️ Grounded Legal Assistant")
    st.caption(
        "Every fact links to its source chunk + verbatim quote. "
        "Unverifiable claims are dropped; empty results refuse honestly."
    )
    by_id, _ = _sidebar()
    st.header("2 · Ask by workflow")
    tabs = st.tabs(["Chat", "Draft", "Review", "Research"])
    for tab, wf in zip(tabs, WORKFLOWS):
        with tab:
            _ask_tab(wf, by_id)


if __name__ == "__main__":
    main()
