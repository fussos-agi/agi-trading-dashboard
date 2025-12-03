import streamlit as st

from config_utils import load_config
from styles import STYLES
from icons import icon_html
from ui_tabs import (
    render_actions_tab,
    render_universe_tab,
    render_portfolio_tab,
    render_trades_tab,
)


def main():
    st.set_page_config(
        page_title="AGI & AI Trading Dashboard",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    # Styles laden
    st.markdown(STYLES, unsafe_allow_html=True)

    # Titel mit Rocket-Icon in Retro-Teal
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.6rem;">
          {icon_html(
                "rocket_launch_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=34,
                variant="teal"
          )}
          <h1 style="margin-bottom:0;">AGI &amp; AI Trading Dashboard</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cfg = load_config()
    thresholds = cfg.get("thresholds", {"run_up_pct": 30, "dip_pct": -30})

    tab_actions, tab_universe, tab_portfolio, tab_trades = st.tabs(
        ["⚙️ Aktionen", "🧠 AI Universe Radar", "📊 Portfolio", "📝 Trade eintragen"]
    )

    with tab_actions:
        render_actions_tab(cfg, thresholds)

    with tab_universe:
        render_universe_tab(cfg, thresholds)

    with tab_portfolio:
        render_portfolio_tab(cfg, thresholds)

    with tab_trades:
        render_trades_tab(cfg)


if __name__ == "__main__":
    main()