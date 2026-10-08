"""Streamlit UI: grounded legal assistant.

Layout philosophy:
  - Use Streamlit's native components; only inject HTML for things Streamlit
    genuinely cannot express (status badges, quote blocks, confidence gauge).
  - No component-level CSS overrides — the theme in .streamlit/config.toml
    handles colours and typography.

Screens:
  1. Sidebar  — backend toggle, document upload, case-set picker.
  2. Tabs     — Chat / Draft / Review / Research.
  3. Source panel — @dialog modal showing chunk text when a [cN] chip is clicked.

Chat and Research tabs keep a scrollable conversation history.
"""

from __future__ import annotations

import inspect

import streamlit as st
from pydantic import ValidationError

from contracts.schemas import Answer, Claim
from ui import api_client
from ui import fixtures as fx
from ui.render import (
    TEMPLATE_IDS,
    USER_VALUE_CSS,
    citation_to_markdown,
    claim_markers,
    confidence_text,
    contradiction_view_model,
    copy_button_html,
    diff_sides,
    docs_by_id,
    doc_id_of_chunk,
    draft_html,
    dropped_claims,
    export_draft_docx,
    highlight_quote,
    load_template,
    missing_chip,
    precheck_summary,
    source_label,
    split_text_markers,
    status_badge,
    status_badge_html,
    still_needed_html,
    user_value_html,
    verifier_bar_html,
    verifier_summary,
    verified_claims,
)
from ui.styles import GLOBAL_CSS

WORKFLOWS = ["chat", "draft", "review", "research", "compare"]
DOC_TYPES = ["statute", "judgment", "case_file"]
PRESETS: dict[str, str] = {
    "chat":     "bail in non-bailable offences?",
    "draft":    "Draft a bail prayer using only the sources for FIR 0123/2024.",
    "review":   "FIR 0123/2024 — is recovery pending, did the accused join investigation?",
    "research": "What did Satender Kumar Antil v. CBI (2022) hold on arrest?",
}
TAB_LABELS = ["💬 Chat", "📝 Draft", "🔍 Review", "📚 Research", "📊 Compare"]

_DATAFRAME_KWARGS: dict = (
    {"width": "stretch"}
    if "width" in inspect.signature(st.dataframe).parameters
    else {"use_container_width": True}
)


# ─── Session state helpers ────────────────────────────────────────────────────

def _base() -> str:
    return st.session_state.get("api_base", api_client.base_url())


def _fixtures_on() -> bool:
    return bool(st.session_state.get("use_fixtures", False))


def _get_chunk(chunk_id: str):
    if _fixtures_on():
        return fx.get_chunk(chunk_id)
    return api_client.get_source(chunk_id, base=_base())


def _fill_example(workflow: str) -> None:
    st.session_state[f"q-{workflow}"] = PRESETS[workflow]


def _history(workflow: str) -> list[dict]:
    return st.session_state.setdefault("history", {}).setdefault(workflow, [])


def _push(workflow: str, q: str, ans: dict) -> None:
    _history(workflow).append({"q": q, "a": ans})


def _clear_history(workflow: str) -> None:
    st.session_state.setdefault("history", {})[workflow] = []


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def _sidebar() -> tuple[dict, dict]:
    with st.sidebar:
        st.markdown("### ⚖️ Legal Assistant")
        st.caption("Every fact traces to a retrieved source.")
        st.divider()

        st.toggle("Offline demo (fixtures)", key="use_fixtures",
                  help="Serve bundled demo answers + chunks; no backend calls.")

        if st.button("Reset session", key="reset-session", use_container_width=True,
                     help="Clear all answers, questions, inputs and selections."):
            for k in [k for k in st.session_state
                      if k.startswith(("answers", "questions", "history", "q-", "pv-", "redrafted-"))
                      or k in ("selected",)]:
                st.session_state.pop(k, None)
            st.rerun()

        if _fixtures_on():
            docs, _ = fx.load_registry()
            by_id = docs_by_id(docs)
            st.success("Fixture mode — offline demo active")
            st.markdown("**Corpus**")
            for d in docs:
                extra = f" · {d.citation}" if d.citation else ""
                st.caption(f"`{d.doc_id}` — {d.title} ({d.doc_type}){extra}")
            st.caption("Upload requires the live backend.")
            return by_id, {"docs": docs}

        # ── Live mode ──────────────────────────────────────────────────────
        st.text_input("API base URL", value=_base(), key="api_base",
                      help="Change to point at a real backend (default localhost:8000)")
        base = _base()
        try:
            health = api_client.get_health(base)
            st.success(f"Connected · {health.get('docs')} docs, {health.get('chunks')} chunks")
        except RuntimeError as e:
            st.error(str(e))
            st.caption("Start backend: `python -m uvicorn api.main:app`")

        try:
            docs = api_client.list_docs(base)
        except RuntimeError as e:
            st.warning(str(e))
            docs = []
        by_id = docs_by_id(docs)

        st.divider()
        st.markdown("**Documents**")
        with st.expander("📤 Upload (POST /ingest)"):
            ups = st.file_uploader("PDF or TXT", type=["pdf", "txt"],
                                   accept_multiple_files=True)
            dtype = st.selectbox("doc_type", DOC_TYPES, index=2)
            if st.button("Ingest", disabled=not ups):
                ok, fail = 0, []
                with st.spinner("Ingesting…"):
                    for f in ups or []:
                        try:
                            res = api_client.post_ingest(f.name, f.getvalue(), dtype, base=base)
                            if not isinstance(res, dict) or "doc" not in res or "num_chunks" not in res:
                                fail.append(f"{f.name}: bad ingest response")
                            else:
                                ok += 1
                                st.caption(f"✓ `{res['doc'].get('doc_id', f.name)}` ({res['num_chunks']} chunks)")
                        except RuntimeError as e:
                            fail.append(f"{f.name}: {e}")
                if ok:
                    st.success(f"Ingested {ok} file(s)")
                for m in fail:
                    st.error(m)
                st.rerun()

        for d in docs:
            extra = f" · {d.citation}" if d.citation else ""
            st.caption(f"`{d.doc_id}` — {d.title}{extra}")

        st.divider()
        known = [d.doc_id for d in docs]
        current_case_set = [c for c in st.session_state.get("case_set", []) if c in known]
        
        st.multiselect("Doc types (empty = all)", DOC_TYPES, default=st.session_state.get("doc_types_filter", []), key="doc_types_filter")
        st.multiselect("Case set filter (empty = all)", known, default=current_case_set, key="case_set")
        
        c1, c2 = st.columns(2)
        if c1.button("Clear filters", use_container_width=True):
            st.session_state["case_set"] = []
            st.session_state["doc_types_filter"] = []
            st.rerun()
        top_k = st.number_input("top_k", 1, 10, 4, step=1)
        st.session_state["top_k"] = int(top_k)

    return by_id, {"docs": docs}


# ─── Source dialog ────────────────────────────────────────────────────────────

@st.dialog("Source Evidence", width="large")
def _source_dialog(answer: Answer, by_id: dict, claim_id: str) -> None:
    """Full-screen dialog showing the claim's chunk evidence."""
    claim = next((c for c in answer.claims if c.claim_id == claim_id), None)
    if claim is None:
        st.warning(f"Claim `{claim_id}` not found in this answer.")
        return

    # Claim header
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown(
            f"**[{claim.claim_id}]** {status_badge_html(claim.status)}",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            copy_button_html(claim.text, "📋"),
            unsafe_allow_html=True,
        )

    st.markdown(claim.text)

    if claim.verifier_note:
        st.caption(f"Verifier: {claim.verifier_note}")

    # Verified quote
    st.markdown("**Verified quote**")
    st.markdown(
        f'<blockquote style="border-left:3px solid #16A34A;margin:0;'
        f'padding:8px 14px;background:#F0FDF4;border-radius:0 6px 6px 0;'
        f'color:#166534;font-style:italic;font-size:0.88rem">'
        f'"{claim.quote}"</blockquote>'
        + "<br>" + copy_button_html(claim.quote, "📋 Copy quote"),
        unsafe_allow_html=True,
    )

    # Chunk(s)
    for chunk_id in claim.chunk_ids:
        st.divider()
        try:
            chunk = _get_chunk(chunk_id)
            doc = by_id.get(chunk.doc_id)
            title = doc.title if doc else chunk.doc_id
            page_str = f" · p. {chunk.page}" if chunk.page else ""

            col_a, col_b = st.columns([5, 2])
            col_a.markdown(f"**{title}**{page_str}")
            if chunk.section_label:
                col_a.caption(chunk.section_label)
            if doc and doc.source_url:
                col_b.markdown(f"[🔗 Open source]({doc.source_url})")
            else:
                col_b.caption("Local doc")

            st.markdown(
                f'<div class="chunk-block">'
                f"{highlight_quote(chunk.text, claim.quote)}"
                f"</div>",
                unsafe_allow_html=True,
            )
        except RuntimeError:
            doc = by_id.get(doc_id_of_chunk(chunk_id))
            st.caption(f"📄 {source_label(chunk_id, by_id)}")
            if doc and doc.source_url:
                st.markdown(f"[🔗 Open source]({doc.source_url})")
            else:
                st.caption("Local doc — no external link.")
            st.markdown(
                f'<blockquote style="border-left:3px solid #16A34A;margin:0;'
                f'padding:8px 14px;background:#F0FDF4;border-radius:0 6px 6px 0;'
                f'color:#166534;font-style:italic;font-size:0.88rem">'
                f'"{claim.quote}"</blockquote>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"⚠️ Full chunk unavailable (GET /sources/{chunk_id} not on this backend)"
                " — showing the verified quote only."
            )


# ─── Verifier bar ─────────────────────────────────────────────────────────────

def _verifier_bar(answer: Answer) -> None:
    summary = verifier_summary(answer)
    st.markdown(verifier_bar_html(summary), unsafe_allow_html=True)
    if summary["dropped_reasons"]:
        with st.expander(f"Dropped claims — {summary['dropped_n']} total"):
            for r in summary["dropped_reasons"]:
                st.caption(r)
            st.caption(f"Source: {summary['reasons_source']}.")


# ─── Chip row ─────────────────────────────────────────────────────────────────

def _chip_row(answer: Answer, by_id: dict, workflow: str, key_prefix: str) -> None:
    """Render a row of [cN] buttons; clicking opens the source dialog."""
    chips = claim_markers(answer.text)
    if not chips:
        return
    st.caption("Click a citation chip to inspect its source:")
    cols = st.columns(min(len(chips), 8))
    for i, cid in enumerate(chips):
        if cols[i % len(cols)].button(
            f"[{cid}]",
            key=f"{key_prefix}-{cid}-{i}",
            help=f"Open source for claim {cid}",
        ):
            _source_dialog(answer, by_id, cid)


# ─── Result renderer ──────────────────────────────────────────────────────────

def _render_result(answer: Answer, by_id: dict, workflow: str, key_sfx: str = "") -> None:
    """Render one Answer with all its components."""

    # ── Refused ────────────────────────────────────────────────────────────
    if answer.refused:
        st.error(f"**Refused** — {answer.text}", icon="⛔")
        if answer.refusal_reason:
            st.markdown(f"**Reason:** {answer.refusal_reason}")
        _verifier_bar(answer)
        bad = dropped_claims(answer)
        if bad:
            with st.expander(f"Dropped claims audit ({len(bad)})"):
                for c in bad:
                    st.caption(f"`{c.claim_id}` [{c.status}] {c.text}")
        if answer.trace:
            with st.expander("Trace (debug)"):
                st.json(answer.trace)
        return

    # ── Warnings ───────────────────────────────────────────────────────────
    if answer.missing_info:
        # Separate list_intent warning from actual missing info
        list_intent_items = [m for m in answer.missing_info if m.field == "exhaustive coverage"]
        real_missing = [m for m in answer.missing_info if m.field != "exhaustive coverage"]
        
        if real_missing:
            st.warning("Missing information needed for a complete answer", icon="⚠️")
            for m in real_missing:
                searched = ", ".join(f"`{d}`" for d in m.searched_in) or "_nothing searched_"
                st.markdown(f"- **{m.field}** — {m.why_needed} (searched: {searched})")
                
        if list_intent_items:
            for m in list_intent_items:
                st.info(f"**List View:** {m.why_needed}", icon="ℹ️")

    if answer.contradictions:
        st.error("Contradictions found between sources", icon="🚨")
        for k in answer.contradictions:
            with st.container(border=True):
                st.markdown(f"**{k.description}**")
                fetched: dict = {}
                for cid in (k.claim_a, k.claim_b):
                    try:
                        fetched[cid] = _get_chunk(cid)
                    except RuntimeError:
                        fetched[cid] = None
                vm = contradiction_view_model(k, fetched)
                if vm["text_a"] is None or vm["text_b"] is None:
                    st.caption(f"`{k.claim_a}` vs `{k.claim_b}` — chunk fetch unavailable")
                else:
                    ha, hb = diff_sides(str(vm["text_a"]), str(vm["text_b"]))
                    la, lb = st.columns(2)
                    with la:
                        st.caption(f"`{k.claim_a}`")
                        st.markdown(f'<div class="chunk-block">{ha}</div>',
                                    unsafe_allow_html=True)
                    with lb:
                        st.caption(f"`{k.claim_b}`")
                        st.markdown(f'<div class="chunk-block">{hb}</div>',
                                    unsafe_allow_html=True)
                    st.caption("Highlighted words differ; plain words are identical.")

    # ── Fallbacks & Protections ────────────────────────────────────────────
    if isinstance(answer.trace, dict):
        backend = answer.trace.get("backend")
        fallbacks = answer.trace.get("fallbacks")
        if backend or fallbacks:
            bits = []
            if backend:
                bits.append(f"Backend: `{backend}`")
            if fallbacks:
                f_str = ", ".join(fallbacks) if isinstance(fallbacks, list) else str(fallbacks)
                bits.append(f"Protections/Fallbacks: {f_str}")
            st.info(" · ".join(bits), icon="🛡️")

    # ── Verifier bar ───────────────────────────────────────────────────────
    _verifier_bar(answer)

    # ── Draft workflow ─────────────────────────────────────────────────────
    if workflow == "draft":
        _render_precheck(answer)
        provided: dict[str, str] = {}
        if answer.missing_info:
            defaults = fx.demo_provided_values(answer) if _fixtures_on() else None
            provided = _render_missing_panel(answer, workflow, defaults)
            if st.button("Re-draft with provided values",
                         key=f"redraft-{workflow}{key_sfx}"):
                vals = {k: v for k, v in provided.items() if v}
                if _fixtures_on():
                    st.rerun()
                try:
                    with st.spinner("Re-drafting…"):
                        ans2 = api_client.post_answer(
                            st.session_state.get(f"q-{workflow}", ""),
                            workflow="draft",  # type: ignore[arg-type]
                            top_k=st.session_state.get("top_k", 4),
                            doc_ids=st.session_state.get("case_set") or None,
                            doc_types=st.session_state.get("doc_types_filter") or None,
                            provided_values=vals or None,
                            draft_type=st.session_state.get("template-draft"),
                            base=_base(),
                        )
                    st.session_state.setdefault("answers", {})[workflow] = ans2.model_dump()
                    st.session_state.pop(f"redrafted-{workflow}", None)
                    st.rerun()
                except (RuntimeError, ValueError, OSError) as e:
                    st.error(str(e), icon="⛔")
        if st.session_state.get(f"redrafted-{workflow}") and not _fixtures_on():
            st.caption(
                "⚠️ Backend `AskIn` has no `provided_values` field — "
                "values were sent but ignored. Echoed as your input, not facts."
            )
        _render_draft_view(answer, by_id, workflow, provided, key_sfx)

    # ── Answer text ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Answer**")

    # Build answer text, bold [cN] markers
    parts = []
    for seg, cid in split_text_markers(answer.text):
        if cid is None:
            parts.append(seg)
        else:
            parts.append(f" **[{cid}]**")
    answer_prose = "".join(parts)

    # Render as markdown (handles lists, newlines, bold naturally)
    st.markdown(answer_prose)
    st.markdown(
        copy_button_html(answer.text, "📋 Copy answer"),
        unsafe_allow_html=True,
    )

    # Chip row
    _chip_row(answer, by_id, workflow, f"chip-{workflow}{key_sfx}")

    # ── Claims table ───────────────────────────────────────────────────────
    st.markdown("---")
    good = verified_claims(answer)
    st.markdown(
        f"**Claims** — "
        f"{len(good)} verified / {len(answer.claims)} total"
    )
    rows = [
        {
            "ID": c.claim_id,
            "Status": status_badge(c.status),
            "Claim": c.text,
            "Quote": c.quote,
            "Chunks": ", ".join(c.chunk_ids),
        }
        for c in answer.claims
    ]
    st.dataframe(rows, hide_index=True, **_DATAFRAME_KWARGS)

    # ── Citations ──────────────────────────────────────────────────────────
    if answer.citations:
        st.markdown("**Citations**")
        for cite in answer.citations:
            st.markdown(f"- {citation_to_markdown(cite, by_id)}")

    # ── Trace ──────────────────────────────────────────────────────────────
    if answer.trace:
        with st.expander("Trace (debug)"):
            st.json(answer.trace)


# ─── Draft sub-renderers ──────────────────────────────────────────────────────

def _render_precheck(answer: Answer) -> None:
    try:
        template = load_template(st.session_state.get("template-draft", TEMPLATE_IDS[0]))
    except ValueError as e:
        st.error(str(e))
        return
    summary = precheck_summary(answer, template)
    total, sourced = summary["total"], summary["sourced_n"]
    pct = int(sourced / total * 100) if total else 0

    with st.container(border=True):
        st.markdown(f"**Draft Readiness** — `{summary['template_id']}`")
        st.progress(pct / 100, text=f"{sourced} of {total} required fields sourced ({pct}%)")
        if summary["unconfirmed"]:
            st.caption("⚠️ Backend returned no missing-info list — counts are unconfirmed.")
        st.markdown(confidence_text(answer))
        for row in summary["rows"]:
            icon = "✅" if row["status"] in ("sourced", "user_provided") else "⚠️"
            detail = f": {row['why_needed']}" if row["why_needed"] else ""
            searched = (
                ", ".join(f"`{d}`" for d in row["searched_in"])
                if row["searched_in"]
                else ""
            )
            line = f"{icon} **{row['name']}** — {row['status']}{detail}"
            if searched:
                line += f" (searched: {searched})"
            st.markdown(f"- {line}")


def _render_missing_panel(
    answer: Answer, workflow: str, defaults: dict[str, str] | None = None
) -> dict[str, str]:
    real_missing = [m for m in answer.missing_info if m.field != "exhaustive coverage"]
    if not real_missing:
        return {}

    with st.container(border=True):
        st.markdown("**Missing information — supply values**")
        st.caption(
            "Values entered here are user input, never sourced facts. "
            "Sent as `provided_values` (forward-compatible — backend ignores them yet)."
        )
        for m in real_missing:
            st.text_input(
                m.field,
                key=f"pv-{workflow}-{m.field}",
                help=m.why_needed,
                value=(defaults or {}).get(m.field, ""),
            )
            searched = ", ".join(f"`{d}`" for d in m.searched_in) or "_nothing searched_"
            st.caption(f"{m.why_needed} (searched: {searched})")
    return {
        m.field: (st.session_state.get(f"pv-{workflow}-{m.field}", "") or "").strip()
        for m in real_missing
    }


def _render_draft_view(
    answer: Answer, by_id: dict, workflow: str,
    provided: dict[str, str], key_sfx: str = ""
) -> None:
    with st.container(border=True):
        st.markdown("**Draft**")
        st.markdown(draft_html(answer), unsafe_allow_html=True)

        chips = claim_markers(answer.text)
        if chips:
            st.caption("Click a chip to open source evidence:")
            cols = st.columns(min(len(chips), 8))
            for i, cid in enumerate(chips):
                if cols[i % len(cols)].button(
                    f"[{cid}]", key=f"dchip-{workflow}{key_sfx}-{cid}-{i}"
                ):
                    _source_dialog(answer, by_id, cid)

        need = still_needed_html(answer, provided)
        if need:
            st.markdown("**Still needed:**")
            st.markdown(need, unsafe_allow_html=True)
            st.caption("Red = unsourced placeholder · amber = your input, not a fact.")

        try:
            blob = export_draft_docx(
                answer,
                (st.session_state.get("questions") or {}).get(workflow, ""),
                provided,
                by_id,
            )
        except Exception as e:
            st.error(f"DOCX export failed: {e} (pip install -r ui/requirements.txt)")
            return
        template_id = st.session_state.get("template-draft", TEMPLATE_IDS[0])
        st.download_button(
            "⬇️ Export DOCX",
            data=blob,
            file_name=f"{template_id}_draft.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=f"export-{workflow}{key_sfx}",
        )


# ─── Chat history thread ──────────────────────────────────────────────────────

def _render_thread(workflow: str, by_id: dict) -> None:
    """Render all past turns for chat/research as an alternating Q&A thread."""
    history = _history(workflow)
    if not history:
        return

    for idx, turn in enumerate(history):
        # User question — right-aligned bubble via columns trick
        _, qcol = st.columns([1, 4])
        with qcol:
            with st.container(border=True):
                st.caption("You")
                st.markdown(turn["q"])

        # Assistant answer
        with st.container(border=True):
            st.caption("Legal Assistant")
            try:
                _render_result(Answer(**turn["a"]), by_id, workflow, key_sfx=f"-h{idx}")
            except ValidationError as e:
                st.error(f"Saved answer failed validation: {e}", icon="⛔")

        st.write("")  # breathing room

    if st.button("🗑️ Clear conversation", key=f"clear-{workflow}"):
        _clear_history(workflow)
        st.rerun()

    st.divider()


# ─── Ask tab ──────────────────────────────────────────────────────────────────

def _ask_tab(workflow: str, by_id: dict) -> None:
    # History thread (chat & research only)
    if workflow in ("chat", "research"):
        _render_thread(workflow, by_id)
    else:
        # Draft / Review: show the last answer above the form
        saved = (st.session_state.get("answers") or {}).get(workflow)
        if saved:
            asked = (st.session_state.get("questions") or {}).get(workflow, "")
            if asked:
                _, qcol = st.columns([1, 4])
                with qcol:
                    with st.container(border=True):
                        st.caption("You")
                        st.markdown(asked)
            with st.container(border=True):
                st.caption("Legal Assistant")
                try:
                    _render_result(Answer(**saved), by_id, workflow)
                except ValidationError as e:
                    st.error(f"Saved answer failed validation: {e}", icon="⛔")
                    if st.button("Discard saved answer", key=f"discard-{workflow}"):
                        st.session_state.get("answers", {}).pop(workflow, None)
                        st.rerun()
            st.divider()

    # ── Template picker (draft only) ───────────────────────────────────────
    if workflow == "draft":
        st.selectbox("Template", list(TEMPLATE_IDS), key="template-draft")

    # ── Question input ─────────────────────────────────────────────────────
    st.text_area(
        "Your question",
        key=f"q-{workflow}",
        height=80,
        placeholder=PRESETS[workflow],
        label_visibility="collapsed",
    )

    c1, c2, c3 = st.columns([2, 2, 6])

    if c1.button("Ask", key=f"ask-{workflow}", type="primary"):
        q = st.session_state.get(f"q-{workflow}", "").strip()
        if not q:
            st.warning("Enter a question first.")
            return
        try:
            if _fixtures_on():
                ans = fx.load_answer(fx.WORKFLOW_FIXTURE[workflow])
                for k in [k for k in st.session_state if k.startswith(f"pv-{workflow}-")]:
                    del st.session_state[k]
            else:
                with st.spinner("Retrieving → claiming → verifying…"):
                    ans = api_client.post_answer(
                        q, workflow=workflow,  # type: ignore[arg-type]
                        top_k=st.session_state.get("top_k", 4),
                        doc_ids=st.session_state.get("case_set") or None,
                        doc_types=st.session_state.get("doc_types_filter") or None,
                        draft_type=st.session_state.get("template-draft") if workflow == "draft" else None,
                        base=_base(),
                    )
            ans_dict = ans.model_dump()
            if workflow in ("chat", "research"):
                _push(workflow, q, ans_dict)
            else:
                st.session_state.setdefault("answers", {})[workflow] = ans_dict
                st.session_state.setdefault("questions", {})[workflow] = q
            st.session_state.pop(f"redrafted-{workflow}", None)
            st.rerun()
        except (RuntimeError, ValueError, OSError) as e:
            st.error(str(e), icon="⛔")

    if workflow == "draft" and c2.button("Run precheck", key="precheck-draft"):
        q = st.session_state.get("q-draft", "").strip()
        if not q:
            st.warning("Enter a question first.")
        else:
            try:
                if _fixtures_on():
                    ans = fx.load_answer("precheck")
                    for k in [k for k in st.session_state if k.startswith("pv-draft-")]:
                        del st.session_state[k]
                else:
                    with st.spinner("Prechecking draft readiness…"):
                        ans = api_client.post_answer(
                            q, workflow="draft",
                            top_k=st.session_state.get("top_k", 4),
                            doc_ids=st.session_state.get("case_set") or None,
                            doc_types=st.session_state.get("doc_types_filter") or None,
                            precheck=True,
                            draft_type=st.session_state.get("template-draft"),
                            base=_base(),
                        )
                st.session_state.setdefault("answers", {})["draft"] = ans.model_dump()
                st.session_state.setdefault("questions", {})["draft"] = q
                st.session_state.pop("redrafted-draft", None)
                st.rerun()
            except (RuntimeError, ValueError, OSError) as e:
                st.error(str(e), icon="⛔")

    c3.button("Fill example", key=f"preset-{workflow}",
              on_click=_fill_example, args=(workflow,))


# ─── Compare Tab ──────────────────────────────────────────────────────────────

def _compare_tab(by_id: dict) -> None:
    import json
    from pathlib import Path

    comp_file = Path("eval/results/compare.jsonl")
    sample_file = Path(__file__).resolve().parent / "fixtures" / "compare_sample.jsonl"
    if comp_file.exists():
        src, label = comp_file, "measured eval results (`eval/results/compare.jsonl`)"
    elif sample_file.exists():
        src, label = sample_file, "hand-built sample (`ui/fixtures/compare_sample.jsonl`) — illustrative, not measured"
    else:
        st.info("No `eval/results/compare.jsonl` found. Run the eval suite to generate baseline comparisons.", icon="ℹ️")
        return

    try:
        rows = [json.loads(line) for line in src.read_text("utf-8").splitlines() if line.strip()]
    except Exception as e:
        st.error(f"Failed to read compare file: {e}")
        return
    st.caption(f"Source: {label}")
        
    if not rows:
        st.info("Compare file is empty.")
        return
        
    qids = [r.get("qid", f"Query {i}") for i, r in enumerate(rows)]
    sel = st.selectbox("Select query to compare", qids)
    idx = qids.index(sel)
    row = rows[idx]
    
    st.markdown(f"**Question:** {row.get('question', '')}")
    st.caption(f"**Mode:** `{row.get('mode', 'unknown')}`")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Baseline (No verify)")
        base = row.get("baseline", {})
        with st.container(border=True):
            st.markdown(base.get("text", ""))
        
        unsupported = row.get("baseline_unsupported", [])
        if unsupported:
            with st.expander(f"Fabricated / Unsupported claims ({len(unsupported)})", expanded=True):
                for u in unsupported:
                    st.error(u, icon="❌")
                    
    with c2:
        st.markdown("### Ours (Grounded & Verified)")
        try:
            ans_obj = Answer(**row.get("ours", {}))
            with st.container(border=True):
                _render_result(ans_obj, by_id, "compare")
        except Exception as e:
            st.error(f"Failed to render our answer: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Grounded Legal Assistant",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    st.title("⚖️ Grounded Legal Assistant")
    st.caption(
        "Every sentence is a claim whose key facts and quote are checked against the source, with the quote shown beside it."
    )

    by_id, _ = _sidebar()

    tabs = st.tabs(TAB_LABELS)
    for tab, wf in zip(tabs, WORKFLOWS):
        with tab:
            if wf == "compare":
                _compare_tab(by_id)
            else:
                _ask_tab(wf, by_id)


if __name__ == "__main__":
    main()
