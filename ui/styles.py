"""Minimal CSS injected once on top of Streamlit's own theme.

Rule: only add CSS that Streamlit's config.toml cannot control.
Keep it small. Work with Streamlit's design system, not against it.
"""

# ─── Surgical overrides only ────────────────────────────────────────────────
GLOBAL_CSS = """
<style>
/* Hide Streamlit chrome we don't need */
#MainMenu, footer, [data-testid="stDecoration"] { display: none !important; }

/* ── Typography — single font stack ────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    font-family: "Inter", ui-sans-serif, system-ui, sans-serif !important;
}

/* ── Sidebar ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    border-right: 1px solid #E5E7EB !important;
}

/* ── Status badges (used inline in markdown) ────────────────────────────── */
.badge {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 0.72rem; font-weight: 600;
    padding: 1px 7px; border-radius: 99px;
}
.badge-v  { background: #DCFCE7; color: #166534; }
.badge-u  { background: #FEF3C7; color: #92400E; }
.badge-r  { background: #FEE2E2; color: #991B1B; }
.badge-n  { background: #F3F4F6; color: #6B7280; border: 1px solid #E5E7EB; }

/* ── User-provided chips (amber — never mistaken for sourced facts) ──────── */
.user-provided {
    background: #FEF3C7; color: #92400E;
    border: 1px solid #F59E0B; border-radius: 6px;
    padding: 1px 7px; font-size: 0.82rem;
}
.user-provided-tag {
    background: #92400E; color: #FFF8E6;
    border-radius: 3px; padding: 0 5px;
    margin-right: 4px; font-size: 0.7rem; font-weight: 700;
}

/* ── Missing-info chip (red) ────────────────────────────────────────────── */
.missing-chip {
    background: #FEE2E2; color: #991B1B;
    border: 1px solid #F87171; border-radius: 6px;
    padding: 1px 7px; font-size: 0.82rem; font-weight: 600;
}

/* ── Sourced underline (dotted green) ───────────────────────────────────── */
.sourced {
    text-decoration: underline dotted #16A34A 2px;
    text-underline-offset: 3px; cursor: help;
}

/* ── Chunk text block (monospace, contained) ────────────────────────────── */
.chunk-block {
    font-family: ui-monospace, "Cascadia Code", monospace;
    font-size: 0.8rem; line-height: 1.65;
    background: #F9FAFB; border: 1px solid #E5E7EB;
    border-radius: 8px; padding: 12px 14px;
    white-space: pre-wrap; word-break: break-word;
    color: #111827;
}
mark { background: #FEF08A; border-radius: 2px; padding: 0 1px; }

/* ── Confidence gauge ───────────────────────────────────────────────────── */
.gauge-wrap  { display: flex; align-items: center; gap: 10px; }
.gauge-track { flex: 1; height: 7px; background: #E5E7EB; border-radius: 99px; overflow: hidden; }
.gauge-fill  { height: 100%; border-radius: 99px; }
.gauge-pct   { font-size: 0.8rem; font-weight: 700; min-width: 34px; text-align: right; }

/* ── Clip button ────────────────────────────────────────────────────────── */
.clip-btn {
    cursor: pointer; border: 1px solid #E5E7EB; border-radius: 5px;
    background: transparent; padding: 2px 8px;
    font-size: 0.71rem; font-weight: 500; color: #6B7280;
    transition: border-color .12s, color .12s;
}
.clip-btn:hover { border-color: #1D4ED8; color: #1D4ED8; }
</style>

<script>
function _clip(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        const t = btn.textContent;
        btn.textContent = "✓ Copied";
        btn.style.color = "#16A34A";
        setTimeout(() => { btn.textContent = t; btn.style.color = ""; }, 1800);
    });
}
</script>
"""

# ─── Backward-compat stub (app.py imports this) ─────────────────────────────
CLIPBOARD_JS = ""
