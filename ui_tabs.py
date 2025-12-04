from datetime import datetime

import streamlit as st
import pandas as pd
import altair as alt  # für schönere Charts

from config_utils import load_ai_universe, save_config, find_portfolio_entry
from analysis_core import (
    build_portfolio_overview,
    analyze_ticker,
    score_watchlist_candidate,
    score_dual_candidate,
    decide_portfolio_action,
    compute_macro_context,
)
from icons import icon_html


# ---------------------------------------------------------------
# Reversal-Erkennung (gemeinsamer Helper)
# ---------------------------------------------------------------

def is_reversal_candidate(analysis, thresholds):
    """
    Erkennt Kandidaten mit:
    - starkem DIP in den letzten ~20 Tagen
    - klarer Gegenbewegung in den letzten 3 Tagen
    - sinnvollem 52W-Drawdown (nicht am Hoch, nicht komplett tot)
    - idealerweise Wellenstruktur / Re-Entry-Signal
    """
    dd = analysis.get("drawdown_52w")
    ch20 = analysis.get("change_20d_pct")
    ch3 = analysis.get("change_3d_pct")
    wave = (analysis.get("wave") or "")
    trend = (analysis.get("trend") or "")

    # Wenn zentrale Daten fehlen → kein Reversal
    if dd is None or ch20 is None or ch3 is None:
        return False

    dip_th = (thresholds or {}).get("dip_pct", -30)

    # 1) Starker DIP über 20 Tage (z. B. <= ~70 % des DIP-Thresholds)
    deep_dip = ch20 <= dip_th * 0.7  # bei -30 → etwa -21 %

    # 2) Klare Gegenbewegung in 3 Tagen (mind. +5 %)
    fresh_turn = ch3 >= 5.0

    # 3) Sinnvoller Drawdown: deutlich unter Hoch, aber nicht komplett -90 %
    in_drawdown = (dd <= -20.0) and (dd >= -80.0)

    # 4) Wave-Unterstützung
    has_wave_support = (
        "Re-Entry-Zone" in wave
        or ("neutral" in wave and analysis.get("is_wave"))
    )

    # 5) Trend darf ruhig noch Aufwärtstrend sein – wir spielen die frühe Drehung
    not_hyper_bull = not trend.startswith("Aufwärtstrend")

    return deep_dip and fresh_turn and in_drawdown and has_wave_support and not_hyper_bull


# ---------------------------------------------------------------
# TAB: Aktionen
# ---------------------------------------------------------------

def render_actions_tab(cfg, thresholds):
    # Makro nur einmal berechnen
    macro = compute_macro_context()

    portfolio, analyses_portfolio, rows_portfolio, gesamt_wert, gesamt_einsatz = build_portfolio_overview(cfg, thresholds)

    # -----------------------------------------------------------
    # Portfolio-Aktionen (Karten)
    # -----------------------------------------------------------
    if not portfolio:
        st.info("Noch keine Portfolio-Analysen verfügbar. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
    else:
        action_rows = []

        for ticker, (analysis, total_shares) in analyses_portfolio.items():
            action, reason = decide_portfolio_action(analysis, total_shares)

            ek = next((r["Einstand (EK)"] for r in rows_portfolio if r["Ticker"] == ticker), None)

            action_rows.append({
                "Name": analysis["name"],
                "Ticker": ticker,
                "Stücke": total_shares,
                "Einstand (EK)": ek,
                "Aktueller Kurs": round(analysis["price"], 2) if analysis["price"] else None,
                "P/L %": round(analysis["pl_pct"], 1) if analysis["pl_pct"] is not None else None,
                "Trend": analysis["trend"],
                "Wave-Signal": analysis["wave"],
                "Aktion": action,
                "Begründung": reason,
                "Targets": analysis.get("targets") or [],
                "NextTarget": analysis.get("next_target"),
                "analysis": analysis,
                "total_shares": total_shares,
            })

        # --------------------------------------------------------
        # Reversal-Fokus im Depot (Karten)
        # --------------------------------------------------------
        reversal_candidates = []
        for row in action_rows:
            analysis = row["analysis"]
            if (
                analysis.get("price") is not None
                and analysis.get("price") > 0
                and analysis.get("is_viable", True)
                and is_reversal_candidate(analysis, thresholds)
            ):
                sts, las = score_dual_candidate(analysis, thresholds, macro)
                reversal_candidates.append((sts, las, row))

        if reversal_candidates:
            reversal_candidates.sort(key=lambda x: x[0], reverse=True)
            top_rev = reversal_candidates[:3]

            st.markdown(
                icon_html(
                    "e911_emergency_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="teal",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Reversal-Fokus im Depot</span>",
                unsafe_allow_html=True,
            )

            cols = st.columns(len(top_rev))
            for col, (sts, las, row) in zip(cols, top_rev):
                with col:
                    pl = row["P/L %"]
                    if pl is None:
                        badge_class = "badge-neutral"
                        pl_text = "n/a"
                    elif pl >= 0:
                        badge_class = "badge-profit"
                        pl_text = f"+{pl:.1f} %"
                    else:
                        badge_class = "badge-loss"
                        pl_text = f"{pl:.1f} %"

                    header_icon = icon_html(
                        "cognition_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                        size=16,
                        variant="teal",
                    )
                    st.markdown(
                        f"""
                        <div class="stock-card">
                          <div class="stock-card-header">
                            {header_icon} {row['Name']} ({row['Ticker']})
                          </div>
                          <div class="stock-card-sub">
                            <span class="badge-pill {badge_class}">{pl_text}</span>
                            &nbsp;· STS {sts} · LAS {las}
                          </div>
                          <div class="stock-card-row"><b>Kurs:</b> {row['Aktueller Kurs']}</div>
                          <div class="stock-card-row"><b>Wave-Signal:</b> {row['Wave-Signal']}</div>
                          <div class="stock-card-row"><b>Trend:</b> {row['Trend']}</div>
                          <div class="stock-card-row"><b>Stücke:</b> {row['Stücke']}</div>
                          <div class="stock-card-row"><b>Einstand:</b> {row['Einstand (EK)']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        # --------------------------------------------------------
        # Alle aktuellen Signale im Depot – Karten
        # --------------------------------------------------------
        st.markdown(
            icon_html(
                "cognition_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=18,
                variant="mustard",
            )
            + "<span style='font-size:1.0rem;font-weight:600;'>Aktuelle Signale im Depot</span>",
            unsafe_allow_html=True,
        )

        for row in action_rows:
            pl = row["P/L %"]
            if pl is None:
                badge_class = "badge-neutral"
                pl_text = "n/a"
            elif pl >= 0:
                badge_class = "badge-profit"
                pl_text = f"+{pl:.1f} %"
            else:
                badge_class = "badge-loss"
                pl_text = f"{pl:.1f} %"

            targets = row.get("Targets") or []
            if targets:
                ladder_str = " · ".join([f"{i+1}: {t:.2f}" for i, t in enumerate(targets)])
            else:
                ladder_str = "—"
            next_target = row.get("NextTarget")
            next_target_txt = f"{next_target:.2f}" if next_target else "—"

            st.markdown(
                f"""
                <div class="stock-card">
                  <div class="stock-card-header">
                    {row['Name']} ({row['Ticker']})
                  </div>
                  <div class="stock-card-sub">
                    <span class="badge-pill {badge_class}">{pl_text}</span>
                    &nbsp;· Trend: {row['Trend']}
                  </div>
                  <div class="stock-card-row"><b>Stücke:</b> {row['Stücke']}</div>
                  <div class="stock-card-row"><b>EK / Kurs:</b> {row['Einstand (EK)']} → {row['Aktueller Kurs']}</div>
                  <div class="stock-card-row"><b>Wave-Signal:</b> {row['Wave-Signal']}</div>
                  <div class="stock-card-row"><b>Ladder-Ziele:</b> {ladder_str}</div>
                  <div class="stock-card-row"><b>Nächstes Ladder-Ziel:</b> {next_target_txt}</div>
                  <div class="stock-card-row"><b>Empfehlung:</b> {row['Aktion']}</div>
                  <div class="stock-card-row"><b>Begründung:</b> {row['Begründung']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Schwerpunkt-Aktion (erste Nicht-HOLD)
        st.markdown("---")
        st.markdown(
            icon_html(
                "cognition_2_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=20,
                variant="burnt",
            )
            + "<span style='font-size:1.05rem;font-weight:600;'>Heutige Schwerpunkt-Aktion</span>",
            unsafe_allow_html=True,
        )

        for row in action_rows:
            if row["Aktion"] != "HOLD":
                nxt = row.get("NextTarget")
                nxt_txt = f"{nxt:.2f}" if nxt else "—"
                st.markdown(
                    f"- **{row['Name']} ({row['Ticker']})** – Aktion **{row['Aktion']}**, "
                    f"P/L {row['P/L %']} %, nächstes Ziel: **{nxt_txt}**."
                )
                reason_icon = icon_html(
                    "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=14,
                    variant="teal",
                )
                st.markdown(f"{reason_icon} {row['Begründung']}", unsafe_allow_html=True)
                break
        else:
            st.info("Aktuell keine dringenden Aktionen – alle Positionen auf HOLD.")

    # -----------------------------------------------------------
    # Reversal-Fokus (Universe) + Monatskauf – Top 3 Kaufideen
    # -----------------------------------------------------------
    st.markdown("---")

    universe = load_ai_universe().get("ai_universe", [])
    if not universe:
        st.info("Keine AI-Universe-Daten gefunden. Bitte ai_universe.json prüfen.")
    else:
        scored = []
        universe_reversals = []

        for entry in universe:
            analysis = analyze_ticker(
                name=entry["name"],
                ticker=entry["ticker"],
                thresholds=thresholds,
            )

            # Aktien ohne handelbaren Kurs oder Zombie ignorieren
            if (
                analysis["price"] is None
                or analysis["price"] <= 0
                or not analysis.get("is_viable", True)
            ):
                continue

            sts, las = score_dual_candidate(analysis, thresholds, macro)
            scored.append((sts, las, analysis, entry))

            if is_reversal_candidate(analysis, thresholds):
                universe_reversals.append((sts, las, analysis, entry))

        # Reversal-Kandidaten aus dem Universe – Karten, über den Top 3
        if universe_reversals:
            universe_reversals.sort(key=lambda x: x[0], reverse=True)
            rev_top = universe_reversals[:6]

            st.markdown(
                icon_html(
                    "rocket_launch_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="rust",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Reversal-Fokus – mögliche Trendwende-Kandidaten</span>",
                unsafe_allow_html=True,
            )

            # 2 oder 3 Karten pro Reihe
            n_cols = 3 if len(rev_top) >= 3 else len(rev_top)
            cols = st.columns(n_cols)
            for idx, (sts, las, analysis, entry) in enumerate(rev_top):
                col = cols[idx % n_cols]
                with col:
                    st.markdown(
                        f"""
                        <div class="stock-card">
                          <div class="stock-card-header">
                            {analysis['name']} ({analysis['ticker']})
                          </div>
                          <div class="stock-card-sub">
                            <span class="badge-pill badge-profit">STS {sts}</span>
                            &nbsp;· LAS {las}
                          </div>
                          <div class="stock-card-row"><b>Kurs:</b> {round(analysis['price'], 2) if analysis['price'] else 'n/a'}</div>
                          <div class="stock-card-row"><b>52W-Stage:</b> {analysis['stage_52w']}</div>
                          <div class="stock-card-row"><b>Wave-Signal:</b> {analysis['wave']}</div>
                          <div class="stock-card-row"><b>Trend:</b> {analysis['trend']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        # Top 3 Kaufideen – Karten statt Tabelle
        scored.sort(key=lambda x: x[0], reverse=True)
        top3 = scored[:3]

        if top3:
            st.markdown(
                icon_html(
                    "social_leaderboard_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="mustard",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Top 3 Kaufideen</span>",
                unsafe_allow_html=True,
            )

            cols = st.columns(len(top3))
            for col, (sts, las, analysis, entry) in zip(cols, top3):
                with col:
                    st.markdown(
                        f"""
                        <div class="stock-card">
                          <div class="stock-card-header">
                            {analysis['name']} ({analysis['ticker']})
                          </div>
                          <div class="stock-card-sub">
                            <span class="badge-pill badge-profit">STS {sts}</span>
                            &nbsp;· LAS {las}
                          </div>
                          <div class="stock-card-row"><b>Kategorie:</b> {entry.get('category', '')}</div>
                          <div class="stock-card-row"><b>AI-Exposure:</b> {entry.get('exposure', '')}/10</div>
                          <div class="stock-card-row"><b>Kurs:</b> {round(analysis['price'], 2) if analysis['price'] else 'n/a'}</div>
                          <div class="stock-card-row"><b>Trend:</b> {analysis['trend']}</div>
                          <div class="stock-card-row"><b>Momentum 20d:</b> {analysis['momentum_20d']}</div>
                          <div class="stock-card-row"><b>52W-Stage:</b> {analysis['stage_52w']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # Detail-Reports für alle Top 3 – in Expandern
            st.markdown("---")
            st.markdown(
                icon_html(
                    "social_leaderboard_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="teal",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Detail-Reports – Top 3 Kaufideen</span>",
                unsafe_allow_html=True,
            )

            macro_state = macro.get("regime", "unknown")

            for rank, (sts, las, best_analysis, best_entry) in enumerate(top3, start=1):
                with st.expander(
                    f"{rank}. {best_analysis['name']} ({best_analysis['ticker']}) – STS {sts}, LAS {las}",
                    expanded=(rank == 1),
                ):
                    col_l, col_r = st.columns(2)
                    with col_l:
                        st.markdown("**Technische Lage**")
                        st.markdown(
                            f"- Kurs: **{round(best_analysis['price'], 2) if best_analysis['price'] else 'n/a'}**"
                        )
                        st.markdown(f"- Trend: {best_analysis['trend']}")
                        st.markdown(f"- Momentum 20d: {best_analysis['momentum_20d']}")
                        st.markdown(f"- 52W-Stage: {best_analysis['stage_52w']}")
                        st.markdown(f"- Wave-Signal: {best_analysis['wave']}")
                        tp = best_analysis.get("wave_tp_level")
                        re = best_analysis.get("wave_reentry_level")
                        if tp:
                            st.markdown(f"- Geschätztes TP-Level: **{tp:.2f}**")
                        if re:
                            st.markdown(f"- Geschätztes Re-Entry-Level: **{re:.2f}**")
                        dte = best_analysis.get("days_to_earnings")
                        if dte is not None:
                            st.markdown(f"- Tage bis Earnings: **{dte}**")

                    with col_r:
                        st.markdown("**Story & Begründung**")
                        st.markdown(
                            f"- Kategorie: **{best_entry.get('category', 'n/a')}**, "
                            f"AI-Exposure: **{best_entry.get('exposure', 'n/a')}/10**"
                        )
                        st.markdown(f"- STS: **{sts}** → kurzfristige Trading-Attraktivität")
                        st.markdown(f"- LAS: **{las}** → langfristige AGI-Attraktivität")

                        fund = best_analysis.get("fundamentals") or {}
                        if fund.get("rev_growth_1y") is not None:
                            st.markdown(f"- Umsatzwachstum 1Y: **{fund['rev_growth_1y']:.1f}%**")
                        if fund.get("net_margin") is not None:
                            st.markdown(f"- Nettomarge: **{fund['net_margin']:.1f}%**")
                        if fund.get("debt_to_assets") is not None:
                            st.markdown(f"- Debt/Assets: **{fund['debt_to_assets']:.2f}**")

                        if "Re-Entry-Zone" in best_analysis["wave"]:
                            st.markdown("- Befindet sich in/nahe einer **Re-Entry-Zone** – gute Basis für Wellentrading.")
                        if "starke Korrektur" in best_analysis["stage_52w"]:
                            st.markdown("- Kurs in **starker Korrektur** – interessant für gestaffelte Käufe.")
                        if "DIP" in best_analysis["momentum_20d"]:
                            st.markdown("- Kurzfristig als **DIP** klassifiziert – Markt hat zuletzt stark abverkauft.")
                        if best_analysis["is_wave"]:
                            st.markdown(
                                "- Aktie erfüllt Kriterien einer **Wellenaktie** "
                                "(hohe Range, viele MA50-Crossings)."
                            )

                        st.markdown(f"- Makro-Regime (S&P): **{macro_state}**")
                        st.markdown(
                            "- Gesamteinschätzung: Kandidat für aggressiven Einstieg (STS) und gleichzeitig "
                            "attraktiv für langfristigen AGI-Aufbau (LAS)."
                        )


# ---------------------------------------------------------------
# TAB: AI Universe Radar
# ---------------------------------------------------------------

def render_universe_tab(cfg, thresholds):
    macro = compute_macro_context()

    st.markdown(
        icon_html(
            "list_alt_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=24,
            variant="teal",
        )
        + "<span style='font-size:1.05rem;font-weight:600;'>Globales AI/AGI Universe Radar</span>",
        unsafe_allow_html=True,
    )

    # Score-Interpretation
    st.markdown(
        """
**Score-Interpretation**

**STS (Short-Term Score – Trading / schnelle Gewinne)**  
- 0–30 → ignorieren / nur beobachten  
- 30–50 → „Watchlist“, es formt sich etwas, aber noch kein klarer Entry  
- 50–65 → opportunistischer Kauf möglich (guter DIP oder Re-Entry-Zone, aber noch nicht extrem)  
- >65 → Top-Trading-Kandidat (starker DIP, ordentliche Wellen-Struktur)

**LAS (Long-Term AGI Score – langfristig einsammeln)**  
- 0–40 → kein spannender Langfrist-Case (zu teuer oder zu wenig AGI-Fokus)  
- 40–60 → solide, kann man mitnehmen, wenn man sowieso diversifiziert  
- >60 → AGI-Kernkandidat: tiefer 52W-Drawdown + klarer AGI-Bonus → ideal zum langsam Einsammeln
        """
    )

    # Makro-Hinweis
    macro_state = macro.get("regime", "unknown")
    dd_spy = macro.get("dd_spy")
    if dd_spy is not None:
        st.markdown(f"> **Aktuelles Makro-Regime:** {macro_state} (S&P Drawdown ca. {dd_spy:.1f}%)")
    else:
        st.markdown(f"> **Aktuelles Makro-Regime:** {macro_state}")

    universe = load_ai_universe().get("ai_universe", [])
    if not universe:
        st.warning("Keine AI-Universe-Daten gefunden. Bitte ai_universe.json prüfen.")
    else:
        rows = []
        for entry in universe:
            analysis = analyze_ticker(
                name=entry["name"],
                ticker=entry["ticker"],
                thresholds=thresholds,
            )

            # Aktien ohne handelbaren Kurs ODER „Zombie“-Flag ignorieren
            if (
                analysis["price"] is None
                or analysis["price"] <= 0
                or not analysis.get("is_viable", True)
            ):
                continue

            sts, las = score_dual_candidate(analysis, thresholds, macro)

            # Ampel-Logik:
            # Grün = klar kaufbar (STS ≥ 65 oder LAS ≥ 60)
            # Gelb = Watchlist / opportunistischer Kauf (STS 50–65 oder LAS 50–60)
            # Rot = kein Kauf / nur beobachten
            green_icon = icon_html(
                "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=16,
                variant="teal",
            )
            yellow_icon = icon_html(
                "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=16,
                variant="mustard",
            )
            red_icon = icon_html(
                "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=16,
                variant="rust",
            )

            if sts >= 65 or las >= 60:
                ampel = f"{green_icon} Kauf-Zone"
            elif sts >= 50 or las >= 50:
                ampel = f"{yellow_icon} Watchlist / opportunistisch"
            else:
                ampel = f"{red_icon} Kein Kauf / nur beobachten"

            fund = analysis.get("fundamentals") or {}
            reversal_flag = is_reversal_candidate(analysis, thresholds)

            rows.append({
                "Name": analysis["name"],
                "Ticker": analysis["ticker"],
                "Kategorie": entry.get("category", ""),
                "AI-Exposure (1–10)": entry.get("exposure", ""),
                "STS (Short-Term)": sts,
                "LAS (Long-Term AGI)": las,
                "Ampel": ampel,
                "Setup": (
                    icon_html(
                        "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                        size=14,
                        variant="burnt",
                    )
                    + " Reversal"
                ) if reversal_flag else "—",
                "Kurs": round(analysis["price"], 2) if analysis["price"] else None,
                "Trend": analysis["trend"],
                "Momentum 20d": analysis["momentum_20d"],
                "52W-Stage": analysis["stage_52w"],
                "Wellen-Aktie?": (
                    icon_html(
                        "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                        size=14,
                        variant="teal",
                    )
                    if analysis["is_wave"]
                    else icon_html(
                        "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                        size=14,
                        variant="rust",
                    )
                ),
                "Ø Tagesrange %": round(analysis["avg_range_pct"], 1) if analysis["avg_range_pct"] else None,
                "Ø Volumen 20d": round(analysis.get("avg_volume_20d"), 0) if analysis.get("avg_volume_20d") else None,
                "Rev-Growth 1Y %": round(fund["rev_growth_1y"], 1) if fund.get("rev_growth_1y") is not None else None,
                "Net Margin %": round(fund["net_margin"], 1) if fund.get("net_margin") is not None else None,
                "Debt/Assets": round(fund["debt_to_assets"], 2) if fund.get("debt_to_assets") is not None else None,
                "Tage bis Earnings": analysis.get("days_to_earnings"),
                "Quality-Check": analysis.get("quality_note") or "ok",
                "Wave-Signal": analysis["wave"],
                "TP-Level": round(analysis["wave_tp_level"], 2) if analysis.get("wave_tp_level") else None,
                "Re-Entry-Level": round(analysis["wave_reentry_level"], 2) if analysis.get("wave_reentry_level") else None,
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("STS (Short-Term)", ascending=False)

        st.dataframe(df, use_container_width=True)


# ---------------------------------------------------------------
# TAB: Portfolio
# ---------------------------------------------------------------

def render_portfolio_tab(cfg, thresholds):
    st.markdown(
        icon_html(
            "account_balance_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=24,
            variant="mustard",
        )
        + "<span style='font-size:1.05rem;font-weight:600;'>Dein aktuelles Portfolio</span>",
        unsafe_allow_html=True,
    )

    portfolio, analyses_portfolio, rows, gesamt_wert, gesamt_einsatz = build_portfolio_overview(cfg, thresholds)

    if not portfolio:
        st.info("Noch keine Positionen im Portfolio. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "Gesamtwert Portfolio",
                f"{gesamt_wert:,.0f} {cfg.get('currency', 'EUR')}"
            )
        with col2:
            if gesamt_einsatz > 0:
                pl_gesamt = (gesamt_wert - gesamt_einsatz) / gesamt_einsatz * 100
                st.metric("Gesamt P/L %", f"{pl_gesamt:+.1f} %")
            else:
                st.metric("Gesamt P/L %", "n/a")

        st.markdown(
            icon_html(
                "account_balance_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                size=18,
                variant="mustard",
            )
            + "<span style='font-size:1.0rem;font-weight:600;'>Aktuelle Aktien im Depot</span>",
            unsafe_allow_html=True,
        )

        for r in rows:
            pl = r["P/L %"]
            if pl is None:
                badge_class = "badge-neutral"
                pl_text = "n/a"
            elif pl >= 0:
                badge_class = "badge-profit"
                pl_text = f"+{pl:.1f} %"
            else:
                badge_class = "badge-loss"
                pl_text = f"{pl:.1f} %"

            st.markdown(
                f"""
                <div class="stock-card">
                  <div class="stock-card-header">
                    {r['Name']} ({r['Ticker']})
                  </div>
                  <div class="stock-card-sub">
                    <span class="badge-pill {badge_class}">{pl_text}</span>
                    &nbsp;· Trend: {r['Trend']}
                  </div>
                  <div class="stock-card-row"><b>Stücke:</b> {r['Stücke']}</div>
                  <div class="stock-card-row"><b>Einstand / Kurs:</b> {r['Einstand (EK)']} → {r['Kurs']}</div>
                  <div class="stock-card-row"><b>Wave:</b> {r['Wave']}</div>
                  <div class="stock-card-row"><b>Signal:</b> {r['Signal']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Kursverlauf – schöner Chart mit Altair
        tickers = [p["ticker"] for p in portfolio]
        choice = st.selectbox("Kursverlauf anzeigen für:", options=tickers)
        sel = next(p for p in portfolio if p["ticker"] == choice)
        sel_analysis = analyze_ticker(
            name=sel["name"],
            ticker=sel["ticker"],
            thresholds=thresholds,
        )
        st.write(f"Preisverlauf 1 Jahr – {sel_analysis['name']} ({sel_analysis['ticker']})")
        if sel_analysis["history"] is not None:
            hist = sel_analysis["history"].reset_index()
            hist = hist[["Date", "Close"]].rename(columns={"Date": "Datum", "Close": "Kurs"})
            chart = (
                alt.Chart(hist)
                .mark_area(opacity=0.4)
                .encode(
                    x="Datum:T",
                    y="Kurs:Q",
                    tooltip=["Datum:T", "Kurs:Q"],
                )
                .interactive()
            )
            st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------------
# TAB: Trade eintragen
# ---------------------------------------------------------------

def render_trades_tab(cfg):
    st.markdown(
        icon_html(
            "edit_document_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=24,
            variant="teal",
        )
        + "<span style='font-size:1.05rem;font-weight:600;'>Neuen Trade eintragen</span>",
        unsafe_allow_html=True,
    )

    with st.form("trade_form"):
        ticker = st.text_input("Ticker (z.B. BBAI)").upper().strip()
        name = st.text_input("Name (z.B. BigBear.ai)")

        trade_type = st.selectbox("Art des Trades", options=["Kauf", "Verkauf"])

        shares = st.number_input("Anzahl Aktien", step=1.0, value=0.0)
        price = st.number_input("Preis pro Aktie", step=0.01, value=0.0)
        date_str = st.text_input("Datum (YYYY-MM-DD, leer = heute)", value="")
        targets_str = st.text_input(
            "Zielkurse (optional, Komma-getrennt – leer = automatische Ladder aus Wave-Logik)"
        )
        submitted = st.form_submit_button("Trade speichern")

    if submitted:
        if not ticker or shares == 0 or price <= 0:
            st.error("Bitte mindestens Ticker, Stückzahl (≠ 0) und Preis > 0 angeben.")
        else:
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            else:
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    st.error("Datum ungültig, bitte im Format YYYY-MM-DD.")
                    return

            signed_shares = shares if trade_type == "Kauf" else -shares

            pos = find_portfolio_entry(cfg, ticker)
            if pos is None:
                if not name:
                    name = ticker

                if targets_str:
                    targets = [float(x) for x in targets_str.split(",")]
                else:
                    targets = []

                pos = {
                    "name": name,
                    "ticker": ticker,
                    "targets": targets,
                    "trades": [],
                }
                cfg.setdefault("portfolio", []).append(pos)
            else:
                if targets_str:
                    pos["targets"] = [float(x) for x in targets_str.split(",")]

            trade = {"date": date_str, "shares": signed_shares, "price": price}
            pos.setdefault("trades", []).append(trade)

            journal = cfg.setdefault("journal", [])
            next_id = max((j.get("id", 0) for j in journal), default=0) + 1
            journal.append({
                "id": next_id,
                "ticker": ticker,
                "name": name or ticker,
                "type": trade_type,
                "shares": shares,
                "price": price,
                "date": date_str,
            })

            save_config(cfg)
            st.success(f"Trade gespeichert: {trade_type} {shares} x {ticker} @ {price} am {date_str}")

    # Trade-Journal
    st.markdown("---")
    st.markdown(
        icon_html(
            "menu_book_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=18,
            variant="burnt",
        )
        + "<span style='font-size:1.0rem;font-weight:600;'>Trade-Journal / Kontoauszug</span>",
        unsafe_allow_html=True,
    )

    journal = cfg.get("journal", [])
    if not journal:
        st.info("Noch keine Trades im Journal.")
    else:
        df_j = pd.DataFrame(journal).sort_values("id", ascending=False)
        st.dataframe(df_j, use_container_width=True, height=260)
