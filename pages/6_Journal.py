"""
Trading Analytics Terminal — Module 6: Edge Journal
Personal trade journal with performance analytics — coming soon.
"""

import streamlit as st

# ── Colour palette — amber/gold accent instead of teal ───────────────────────
C = {
    "bg":     "#0d0d0d",
    "card":   "#141414",
    "border": "#252525",
    "dim":    "#171717",
    "text":   "#e8e8e8",
    "muted":  "#666666",
    "amber":  "#f0b429",   # primary accent
    "gold":   "#ffd166",   # highlight
    "teal":   "#e63946",   # kept only for Back button
}

_FEATURES = [
    "Trade logging with setup tagging",
    "Win rate · expectancy · profit factor",
    "Setup & session performance breakdown",
    "Equity curve and drawdown tracker",
    "Personal edge score over time",
]


def main():
    st.set_page_config(
        page_title="Edge Journal · Trading Terminal",
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
      }}
      button[kind="secondary"]:hover {{
          border-color:{C['amber']} !important; color:{C['amber']} !important;
      }}
      p, span, label {{ color:{C['text']}; }}
    </style>
    """, unsafe_allow_html=True)

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

    st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)

    # ── Coming Soon card ───────────────────────────────────────────────────────
    _, col_c, _ = st.columns([1, 2, 1])
    with col_c:
        feature_rows = "".join([
            f"<div style='display:flex;align-items:center;gap:12px;"
            f"padding:9px 0;border-bottom:1px solid {C['border']};'>"
            f"<span style='color:{C['amber']};font-family:monospace;font-size:13px;'>→</span>"
            f"<span style='font-size:12px;color:{C['muted']};font-family:monospace;'>{f}</span>"
            f"</div>"
            for f in _FEATURES
        ])

        st.markdown(
            f"""
            <div style="background:{C['card']};border:1px solid {C['amber']}38;
                        border-radius:16px;padding:44px 44px 36px;text-align:center;
                        box-shadow:0 0 40px {C['amber']}08;">

              <!-- PRO badge -->
              <div style="margin-bottom:28px;">
                <span style="background:{C['amber']};color:#0a0c10;
                             font-size:10px;font-family:monospace;font-weight:800;
                             letter-spacing:2.5px;padding:5px 16px;border-radius:20px;
                             text-transform:uppercase;">PRO</span>
              </div>

              <!-- Icon -->
              <div style="font-size:52px;margin-bottom:18px;line-height:1;">📓</div>

              <!-- Title -->
              <div style="font-size:22px;font-weight:800;color:{C['text']};
                          font-family:monospace;letter-spacing:-0.5px;margin-bottom:12px;">
                Trade Journal
              </div>

              <!-- Description -->
              <div style="font-size:13px;color:{C['muted']};font-family:sans-serif;
                          line-height:1.8;max-width:400px;margin:0 auto 32px;">
                A structured journal is being built here — log every trade,
                track your edge over time, and let the data show you where you
                actually make money. Requires account authentication.
              </div>

              <!-- Feature list -->
              <div style="max-width:320px;margin:0 auto 36px;text-align:left;">
                {feature_rows}
              </div>

              <!-- Status footer -->
              <div style="font-size:10px;color:{C['muted']};font-family:monospace;
                          letter-spacing:1.5px;border-top:1px solid {C['border']};
                          padding-top:20px;text-transform:uppercase;">
                Status &nbsp;·&nbsp;
                <span style="color:{C['amber']};font-weight:700;">In Development</span>
                &nbsp;&nbsp;·&nbsp;&nbsp; Authentication Required
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


if __name__ == "__main__":
    main()
