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

    # -------------------------------------------------
    # Lade-Hinweis + Fortschrittsbalken (Retro-Style)
    # -------------------------------------------------
    # eigener Platzhalter-Container für Hinweis + Balken
    loader = st.empty()

    with loader.container():
        st.markdown(
            """
            <div class="loading-box">
              <div class="loading-box-title">
                AGI &amp; AI Daten werden geladen …
              </div>
              <div class="loading-box-sub">
                Dieses Dashboard verknüpft sehr viele Markt- und Bewertungsdaten.
                Der erste Start kann bis zu <b>120 Sekunden</b> dauern – das ist vollkommen normal.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Fortschrittsbalken innerhalb des gleichen Containers
        progress = st.progress(0)

    # Titel mit Rocket-Icon in Retro-Teal
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.6rem;">
          {icon_html(
                "price_change_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=44,
                variant="teal",
          )}
          <h1 style="margin-bottom:0;">AGI &amp; AI Trading Dashboard</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Konfiguration laden
    cfg = load_config()
    thresholds = cfg.get("thresholds", {"run_up_pct": 30, "dip_pct": -30})
    progress.progress(30)

    # Native Streamlit-Tabs (bleiben innerhalb der Seite, ohne Emojis)
    tab_actions, tab_universe, tab_portfolio, tab_trades = st.tabs(
        ["HOME", "AGI/AI RADAR", "PORTFOLIO", "TRADE/JOURNAL"]
    )

    # Tabs rendern – hier passiert der Großteil der Arbeit
    with tab_actions:
        render_actions_tab(cfg, thresholds)
    progress.progress(60)

    with tab_universe:
        render_universe_tab(cfg, thresholds)
    progress.progress(80)

    with tab_portfolio:
        render_portfolio_tab(cfg, thresholds)
    progress.progress(90)

    with tab_trades:
        render_trades_tab(cfg)
    progress.progress(100)

    # Wenn alles gerendert ist → Lade-Hinweis + Balken entfernen
    loader.empty()


if __name__ == "__main__":
    main()