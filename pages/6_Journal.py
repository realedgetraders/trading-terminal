"""
Trading Analytics Terminal — Module 6: Edge Journal
Password-gated PRO module preview. Full build coming soon.
"""

import streamlit as st

# ── Colour palette — amber/gold accent ──────────────────────────────────────
C = {
    "bg":     "#0d0d0d",
    "card":   "#141414",
    "border": "#252525",
    "panel":  "#111111",
    "dim":    "#171717",
    "text":   "#e8e8e8",
    "muted":  "#666666",
    "amber":  "#f0b429",
    "gold":   "#ffd166",
    "teal":   "#f0b429",   # amber — Back button (journal accent)
}

_PASSWORD = "12345"

_FEATURES = [
    ("📝", "Trade Log",          "Enter and save every trade — symbol, direction, entry, exit, size, and personal notes."),
    ("📊", "Performance Stats",  "Full analytics: win rate, expectancy, profit factor, setup breakdown, and CSV export for AI analysis."),
    ("📈", "Equity Curve",       "Visual drawdown tracker and equity curve over time — see exactly when your edge is working."),
    ("🏷️", "Setup Tagging",      "Tag each trade by setup type and session to find where your edge actually lives."),
    ("👤", "Trader Profile",     "Personal edge score over time, strengths, weaknesses — your trading identity in data."),
]


def main():
    st.set_page_config(
        page_title="Edge Journal — EdgeLab",
        page_icon="📓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(f"""
    <style>
      html, body, [data-testid="stAppViewContainer"],
      [data-testid="stHeader"], [data-testid="stToolbar"],
      [data-testid="stDecoration"] {{
          background-color:{C['bg']} !important;
      }}
      section[data-testid="stSidebar"] {{ display:none !important; }}
      .stMainBlockContainer {{
          padding-top:3rem !important; padding-bottom:3rem !important;
      }}
      button[kind="secondary"] {{
          background:{C['dim']} !important; color:{C['muted']} !important;
          border:1px solid {C['border']} !important;
          font-family:monospace !important; font-weight:600 !important;
          border-radius:8px !important;
          transition:border-color 0.22s ease,color 0.22s ease,box-shadow 0.22s ease !important;
      }}
      button[kind="secondary"]:hover {{
          border-color:{C['amber']}70 !important; color:{C['amber']} !important;
          box-shadow:0 0 12px rgba(240,180,41,0.14) !important;
      }}
      [data-testid="stTextInput"] input {{
          background:{C['card']} !important;
          border:1px solid {C['border']} !important;
          color:{C['text']} !important;
          font-family:monospace !important;
          border-radius:8px !important;
      }}
      [data-testid="stTextInput"] input::placeholder {{
          color:{C['muted']} !important;
      }}
      p, span, label {{ color:{C['text']}; }}
    </style>
    """, unsafe_allow_html=True)

    # ── Password gate ──────────────────────────────────────────────────────────
    if not st.session_state.get("journal_auth"):
        st.markdown("<div style='height:12vh;'></div>", unsafe_allow_html=True)
        _, col_c, _ = st.columns([3, 2, 3])
        with col_c:
            st.markdown(
                f"<div style='text-align:center;margin-bottom:22px;'>"
                f"<span style='background:{C['amber']};color:#0a0c10;font-size:9px;"
                f"font-weight:800;font-family:monospace;letter-spacing:2px;"
                f"padding:3px 12px;border-radius:12px;'>PRO ACCESS</span>"
                f"<div style='font-size:22px;font-weight:800;color:{C['text']};"
                f"font-family:monospace;letter-spacing:-0.5px;margin-top:14px;'>"
                f"Edge Journal</div>"
                f"<div style='font-size:11px;color:{C['muted']};font-family:monospace;"
                f"margin-top:5px;'>Enter password to continue</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            pw = st.text_input(
                "Password",
                type="password",
                placeholder="Enter password…",
                label_visibility="collapsed",
                key="journal_pw",
            )
            if st.button("Unlock →", use_container_width=True, key="journal_unlock"):
                if pw == _PASSWORD:
                    st.session_state["journal_auth"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        return

    # ── Title row ──────────────────────────────────────────────────────────────
    col_back, col_title, _ = st.columns([2, 6, 2])
    with col_back:
        if st.button("← Back to Hub"):
            st.switch_page("app.py")
    with col_title:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:11px;color:{C['amber']};font-family:monospace;"
            f"letter-spacing:3px;text-transform:uppercase;margin-bottom:10px;'>"
            f"Edge Journal</div>"
            f"<div style='font-size:30px;font-weight:800;color:{C['text']};"
            f"font-family:monospace;letter-spacing:-1px;line-height:1.1;'>"
            f"Track. Analyse. Improve.</div>"
            f"<div style='width:48px;height:2px;background:{C['amber']};"
            f"margin:14px auto 0;border-radius:1px;'></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)

    # ── Feature cards ──────────────────────────────────────────────────────────
    _, col_c, _ = st.columns([1, 3, 1])
    with col_c:
        # Status banner
        st.markdown(
            f"<div style='text-align:center;margin-bottom:28px;'>"
            f"<span style='background:rgba(240,180,41,0.08);border:1px solid rgba(240,180,41,0.25);"
            f"border-radius:8px;padding:8px 20px;"
            f"font-size:11px;font-family:monospace;color:#888888;letter-spacing:1px;'>"
            f"🔒 &nbsp; Authentication required &nbsp;·&nbsp; "
            f"<span style='color:{C[\"amber\"]};font-weight:700;'>In Development</span>"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        # Feature list rows
        feature_rows = ""
        for icon, title, desc in _FEATURES:
            feature_rows += f"""
<div style='display:flex;align-items:flex-start;gap:16px;
            padding:16px 0;border-bottom:1px solid {C['border']};'>
  <span style='font-size:22px;margin-top:2px;flex-shrink:0;'>{icon}</span>
  <div>
    <div style='font-size:13px;font-weight:700;color:{C['text']};
                font-family:monospace;letter-spacing:0.5px;margin-bottom:4px;'>{title}</div>
    <div style='font-size:11px;color:{C['muted']};font-family:sans-serif;
                line-height:1.6;'>{desc}</div>
  </div>
</div>"""

        st.markdown(
            f"""
<div style="background:{C['card']};border:1px solid {C['amber']}30;
            border-radius:16px;padding:40px 44px 36px;
            box-shadow:0 0 40px {C['amber']}06;">

  <!-- PRO badge + icon -->
  <div style="text-align:center;margin-bottom:32px;">
    <span style="background:{C['amber']};color:#0a0c10;
                 font-size:10px;font-family:monospace;font-weight:800;
                 letter-spacing:2.5px;padding:5px 16px;border-radius:20px;
                 text-transform:uppercase;">PRO</span>
    <div style="font-size:48px;margin-top:18px;line-height:1;">📓</div>
    <div style="font-size:13px;color:{C['muted']};font-family:sans-serif;
                line-height:1.8;max-width:420px;margin:16px auto 0;">
      A structured journal is being built here — log every trade,
      track your edge over time, and let the data show you where you
      actually make money.
    </div>
  </div>

  <!-- Feature list -->
  <div style="max-width:460px;margin:0 auto;">
    {feature_rows}
  </div>

  <!-- Status footer -->
  <div style="text-align:center;font-size:10px;color:{C['muted']};
              font-family:monospace;letter-spacing:1.5px;
              border-top:1px solid {C['border']};
              padding-top:20px;margin-top:8px;text-transform:uppercase;">
    Status &nbsp;·&nbsp;
    <span style="color:{C['amber']};font-weight:700;">In Development</span>
  </div>

</div>
            """,
            unsafe_allow_html=True,
        )

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='margin-top:48px;padding-top:16px;"
        f"border-top:1px solid {C['border']};text-align:center;"
        f"font-size:11px;color:{C['muted']};font-family:monospace;'>"
        f"Built by @realedgetraders"
        f"</div>",
        unsafe_allow_html=True,
    )


main()
