"""
Trading Analytics Terminal — Module 6: Edge Journal
PRO password-gated preview. Full build coming soon.
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
    "amber":  "#f0b429",
    "teal":   "#f0b429",   # amber accent throughout Journal
    "red":    "#f05262",
}

_FEATURES = [
    ("📝", "Trade Log",         "Enter and save every trade — symbol, direction, entry, exit, size, and personal notes."),
    ("📊", "Performance Stats", "Full analytics: win rate, expectancy, profit factor, setup breakdown, and CSV export for AI analysis."),
    ("📈", "Equity Curve",      "Visual drawdown tracker and equity curve over time — see exactly when your edge is working."),
    ("🏷️", "Setup Tagging",     "Tag each trade by setup type and session to find where your edge actually lives."),
    ("👤", "Trader Profile",    "Personal edge score over time, strengths, weaknesses — your trading identity in data."),
]


def _inject_css():
    st.markdown(
        f"<style>"
        f"html,body,[data-testid='stAppViewContainer'],"
        f"[data-testid='stHeader'],[data-testid='stToolbar'],"
        f"[data-testid='stDecoration']{{background-color:{C['bg']} !important;}}"
        f"section[data-testid='stSidebar']{{display:none !important;}}"
        f"</style>",
        unsafe_allow_html=True,
    )


def _render_gate():
    """PRO password gate — same pattern as Module 3, amber-themed for Journal."""
    _card   = C["card"]
    _muted  = C["muted"]
    _text   = C["text"]
    _amber  = C["amber"]
    _red    = C["red"]

    # Gate CSS — no HTML comments, f-string chain only
    st.markdown(
        f"<style>"
        f"[data-testid='stTextInput'] input {{"
        f"  background:#1c1c1c !important;"
        f"  border:1px solid rgba(240,180,41,0.28) !important;"
        f"  color:{_text} !important;"
        f"  font-family:monospace !important;"
        f"  border-radius:8px !important;"
        f"  font-size:13px !important;"
        f"}}"
        f"[data-testid='stTextInput'] input::placeholder {{"
        f"  color:#555 !important; letter-spacing:1px !important;"
        f"}}"
        f"[data-testid='stTextInput'] input:focus {{"
        f"  border-color:rgba(240,180,41,0.65) !important;"
        f"  box-shadow:0 0 0 3px rgba(240,180,41,0.10) !important;"
        f"}}"
        f"button[kind='secondary'] {{"
        f"  background:rgba(240,180,41,0.11) !important;"
        f"  border:1px solid rgba(240,180,41,0.45) !important;"
        f"  color:{_amber} !important;"
        f"  font-family:monospace !important; font-weight:700 !important;"
        f"  font-size:11px !important; letter-spacing:3px !important;"
        f"  border-radius:8px !important;"
        f"  transition:all 0.22s ease !important;"
        f"}}"
        f"button[kind='secondary']:hover {{"
        f"  background:rgba(240,180,41,0.20) !important;"
        f"  border-color:rgba(240,180,41,0.75) !important;"
        f"  box-shadow:0 0 18px rgba(240,180,41,0.18) !important;"
        f"}}"
        f"</style>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:9vh;'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        # Amber module identity bar
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;"
            f"background:rgba(240,180,41,0.06);"
            f"border:1px solid rgba(240,180,41,0.20);"
            f"border-bottom:none;border-radius:10px 10px 0 0;padding:10px 20px;'>"
            f"<div style='width:5px;height:5px;border-radius:50%;background:{_amber};"
            f"box-shadow:0 0 7px rgba(240,180,41,0.85);flex-shrink:0;'></div>"
            f"<span style='font-size:9px;color:{_amber};font-family:monospace;"
            f"letter-spacing:2.5px;text-transform:uppercase;'>Module 6</span>"
            f"<div style='flex:1;height:1px;background:rgba(240,180,41,0.12);'></div>"
            f"<span style='font-size:9px;color:{_muted};font-family:monospace;"
            f"letter-spacing:1.5px;text-transform:uppercase;'>Edge Journal</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        # Main PRO card — open bottom
        st.markdown(
            f"<div style='background:{_card};"
            f"border:1px solid rgba(240,180,41,0.22);border-top:none;border-bottom:none;"
            f"padding:38px 40px 28px;"
            f"box-shadow:0 0 50px rgba(240,180,41,0.05),0 4px 32px rgba(0,0,0,0.3);'>"
            # PRO badge
            f"<div style='text-align:center;margin-bottom:22px;'>"
            f"<span style='background:{_amber};color:#0a0c10;font-size:9px;"
            f"font-family:monospace;font-weight:800;letter-spacing:3px;"
            f"padding:4px 14px;border-radius:20px;text-transform:uppercase;'>PRO</span>"
            f"</div>"
            # Lock icon
            f"<div style='text-align:center;font-size:34px;line-height:1;margin-bottom:18px;'>🔒</div>"
            # Title
            f"<div style='text-align:center;font-size:21px;font-weight:800;color:{_text};"
            f"font-family:monospace;letter-spacing:-0.5px;margin-bottom:10px;'>"
            f"Edge Journal</div>"
            # Description
            f"<div style='text-align:center;font-size:11px;color:{_muted};"
            f"font-family:monospace;line-height:1.85;margin-bottom:26px;'>"
            f"Trade log &nbsp;·&nbsp; Performance stats &nbsp;·&nbsp; Equity curve<br>"
            f"Setup tagging &nbsp;·&nbsp; Trader profile</div>"
            # Divider
            f"<div style='height:1px;"
            f"background:linear-gradient(90deg,transparent,rgba(240,180,41,0.22),transparent);"
            f"margin-bottom:22px;'></div>"
            # Label
            f"<div style='text-align:center;font-size:9px;color:#555;font-family:monospace;"
            f"letter-spacing:2px;text-transform:uppercase;margin-bottom:14px;'>"
            f"Access code required</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        # Input
        pwd = st.text_input("", type="password", placeholder="Enter access code ···",
                            label_visibility="collapsed", key="j_pwd_input")
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        # Unlock button
        if st.button("UNLOCK", use_container_width=True, key="j_unlock_btn"):
            if pwd == "12345":
                st.session_state["journal_auth"] = True
                st.rerun()
            else:
                st.markdown(
                    f"<p style='color:{_red};font-family:monospace;font-size:11px;"
                    "text-align:center;margin-top:10px;'>Incorrect access code.</p>",
                    unsafe_allow_html=True,
                )
        # Bottom card cap
        st.markdown(
            f"<div style='background:{_card};"
            f"border:1px solid rgba(240,180,41,0.22);border-top:none;"
            f"border-radius:0 0 12px 12px;height:28px;"
            f"box-shadow:0 6px 32px rgba(0,0,0,0.28);'></div>",
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


def _render_preview():
    """Feature preview shown after authentication."""
    _amber = C["amber"]
    _text  = C["text"]
    _muted = C["muted"]
    _card  = C["card"]

    # Back button + title
    col_back, col_title, _ = st.columns([2, 6, 2])
    with col_back:
        if st.button("← Back to Hub", key="j_back"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:10px;color:{_amber};font-family:monospace;"
            f"letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;'>Edge Journal</div>"
            f"<div style='font-size:26px;font-weight:800;color:{_text};"
            f"font-family:monospace;letter-spacing:-1px;line-height:1.1;'>"
            f"Track. Analyse. Improve.</div>"
            f"<div style='width:48px;height:2px;background:{_amber};"
            f"margin:14px auto 0;border-radius:1px;'></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)

    _, col_c, _ = st.columns([1, 3, 1])
    with col_c:
        # Status banner
        st.markdown(
            f"<div style='text-align:center;margin-bottom:28px;'>"
            f"<span style='background:rgba(240,180,41,0.08);"
            f"border:1px solid rgba(240,180,41,0.25);border-radius:8px;padding:8px 20px;"
            f"font-size:11px;font-family:monospace;color:#888;letter-spacing:1px;'>"
            f"📓 &nbsp; Full build coming soon &nbsp;·&nbsp; "
            f"<span style='color:{_amber};font-weight:700;'>In Development</span>"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        # Feature rows — build without HTML comments
        rows_html = ""
        for icon, title, desc in _FEATURES:
            rows_html += (
                f"<div style='display:flex;align-items:flex-start;gap:16px;"
                f"padding:16px 0;border-bottom:1px solid {C['border']};'>"
                f"<span style='font-size:22px;margin-top:2px;flex-shrink:0;'>{icon}</span>"
                f"<div>"
                f"<div style='font-size:13px;font-weight:700;color:{_text};"
                f"font-family:monospace;letter-spacing:0.5px;margin-bottom:4px;'>{title}</div>"
                f"<div style='font-size:11px;color:{_muted};font-family:sans-serif;"
                f"line-height:1.6;'>{desc}</div>"
                f"</div></div>"
            )

        st.markdown(
            f"<div style='background:{_card};border:1px solid rgba(240,180,41,0.18);"
            f"border-radius:16px;padding:40px 44px 36px;"
            f"box-shadow:0 0 40px rgba(240,180,41,0.04);'>"
            f"<div style='text-align:center;margin-bottom:32px;'>"
            f"<span style='background:{_amber};color:#0a0c10;"
            f"font-size:10px;font-family:monospace;font-weight:800;"
            f"letter-spacing:2.5px;padding:5px 16px;border-radius:20px;"
            f"text-transform:uppercase;'>PRO</span>"
            f"<div style='font-size:48px;margin-top:18px;line-height:1;'>📓</div>"
            f"<div style='font-size:13px;color:{_muted};font-family:sans-serif;"
            f"line-height:1.8;max-width:420px;margin:16px auto 0;'>"
            f"A structured journal is being built here — log every trade, "
            f"track your edge over time, and let the data show you where you "
            f"actually make money.</div>"
            f"</div>"
            f"<div style='max-width:460px;margin:0 auto;'>{rows_html}</div>"
            f"<div style='text-align:center;font-size:10px;color:{_muted};"
            f"font-family:monospace;letter-spacing:1.5px;"
            f"border-top:1px solid {C['border']};padding-top:20px;margin-top:8px;"
            f"text-transform:uppercase;'>"
            f"Status &nbsp;·&nbsp; "
            f"<span style='color:{_amber};font-weight:700;'>In Development</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )


def main():
    st.set_page_config(
        page_title="Edge Journal — EdgeLab",
        page_icon="📓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()

    # Password gate
    if not st.session_state.get("journal_auth", False):
        _render_gate()
        _render_footer()
        return

    # Authenticated — show feature preview
    _render_preview()
    _render_footer()


main()
