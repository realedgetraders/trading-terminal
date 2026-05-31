"""
Trading Analytics Terminal — Module 7: Valuation Tool
Work-in-progress placeholder. Engine/logic to follow.
"""

import streamlit as st

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "bg":     "#0d0d0d",
    "card":   "#141414",
    "border": "#252525",
    "dim":    "#171717",
    "text":   "#e8e8e8",
    "muted":  "#666666",
    "teal":   "#4f8ef7",
}


def _inject_css():
    st.markdown(
        f"<style>"
        f"@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap');"
        f"*{{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;}}"
        f"[style*='font-family:monospace'],[style*='font-family: monospace']{{font-family:'JetBrains Mono',monospace !important;}}"
        f"[style*='font-family:sans-serif'],[style*='font-family: sans-serif']{{font-family:'Inter',sans-serif !important;}}"
        f"button{{font-family:'JetBrains Mono',monospace !important;}}"
        f"html,body,[data-testid='stAppViewContainer'],"
        f"[data-testid='stHeader'],[data-testid='stToolbar'],"
        f"[data-testid='stDecoration']{{background-color:{C['bg']} !important;}}"
        f"section[data-testid='stSidebar']{{display:none !important;}}"
        f"button[kind='secondary']{{"
        f"background:#161616 !important;color:{C['text']} !important;"
        f"border:1px solid #2e2e2e !important;font-weight:600 !important;"
        f"font-family:monospace !important;"
        f"transition:border-color 0.22s ease,color 0.22s ease,box-shadow 0.22s ease !important;"
        f"}}"
        f"button[kind='secondary']:hover{{"
        f"border-color:{C['teal']}70 !important;color:{C['teal']} !important;"
        f"box-shadow:0 0 12px rgba(79,142,247,0.14) !important;"
        f"}}"
        f"</style>",
        unsafe_allow_html=True,
    )


def _render_footer():
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders</div>",
        unsafe_allow_html=True,
    )


def _render_placeholder():
    _teal  = C["teal"]
    _text  = C["text"]
    _muted = C["muted"]
    _card  = C["card"]

    # Back button + title row
    col_back, col_title, _ = st.columns([2, 6, 2])
    with col_back:
        if st.button("← Back to Hub", key="val_back"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:10px;color:{_teal};font-family:monospace;"
            f"letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;'>"
            f"Module 07 &nbsp;·&nbsp; Valuation Tool</div>"
            f"<div style='font-size:26px;font-weight:800;color:{_text};"
            f"font-family:monospace;letter-spacing:-1px;line-height:1.1;'>"
            f"Valuation Tool</div>"
            f"<div style='width:48px;height:2px;background:{_teal};"
            f"margin:14px auto 0;border-radius:1px;'></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)

    _, col_c, _ = st.columns([1, 3, 1])
    with col_c:
        st.markdown(
            f"<div style='background:{_card};border:1px dashed {C['border']};"
            f"border-radius:16px;padding:48px 44px;text-align:center;'>"
            f"<div style='font-size:48px;line-height:1;margin-bottom:18px;'>⚖️</div>"
            f"<div style='margin-bottom:18px;'>"
            f"<span style='background:rgba(240,180,41,0.08);"
            f"border:1px solid rgba(240,180,41,0.25);border-radius:8px;padding:6px 18px;"
            f"font-size:11px;font-family:monospace;color:#888;letter-spacing:2px;"
            f"text-transform:uppercase;'>🚧 &nbsp; Work in Progress</span>"
            f"</div>"
            f"<div style='font-size:13px;color:{_muted};font-family:sans-serif;"
            f"line-height:1.8;max-width:440px;margin:0 auto;'>"
            f"This module will detect whether the currently selected asset is "
            f"under- or overvalued relative to other assets. The valuation engine "
            f"is still being built — no analysis is available yet.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def main():
    st.set_page_config(
        page_title="Valuation Tool — EdgeLab",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()
    _render_placeholder()
    _render_footer()


main()
