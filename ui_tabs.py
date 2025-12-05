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
# Ladder-Sell-Engine – neue Version (nur 1 Parameter!)
# ---------------------------------------------------------------

LADDER_LEVELS = [0.30, 0.50, 0.75, 1.00, 1.50, 2.00]


def _get_exposure_map():
    uni = load_ai_universe()
    exposure_map = {}
    for entry in uni.get("ai_universe", []):
        ticker = (entry.get("ticker") or "").upper()
        if ticker:
            exposure_map[ticker] = entry.get("exposure")
    return exposure_map


def _core_and_ladder_pct(exposure):
    if exposure is None:
        return 0.0, 1.0
    if exposure >= 9:
        return 0.20, 0.80
    if exposure >= 7:
        return 0.10, 0.90
    return 0.0, 1.0


def compute_ladder_signals(rows):
    """
    Neue Ladder-Engine:
    NUR rows aus build_portfolio_overview notwendig (stabile Datenstruktur).
    """
    exposure_map = _get_exposure_map()
    signals = []

    for r in rows:
        ticker = r.get("Ticker")
        name = r.get("Name")
        shares = r.get("Stücke") or 0
        pl_pct = r.get("P/L %")

        if not ticker or shares <= 0:
            continue
        if pl_pct is None or pl_pct <= 0:
            continue

        exposure = exposure_map.get((ticker or "").upper())
        core_pct, ladder_pct = _core_and_ladder_pct(exposure)

        ladder_shares = int(shares * ladder_pct)
        if ladder_shares <= 0:
            continue

        profit_frac = pl_pct / 100
        reached = sum(1 for lvl in LADDER_LEVELS if profit_frac >= lvl)
        if reached == 0:
            continue

        frac = reached / len(LADDER_LEVELS)
        to_sell = int(ladder_shares * frac)
        if to_sell <= 0:
            continue

        if core_pct >= 0.19:
            core_text = "20 % Core halten (Exposure 9–10)"
        elif core_pct >= 0.09:
            core_text = "10 % Core halten (Exposure 7–8)"
        else:
            core_text = "kein Core – komplette Position über Ladder verwalten"

        signals.append(
            {
                "Name": name,
                "Ticker": ticker,
                "Exposure": exposure,
                "Gewinn %": round(pl_pct, 1),
                "Empfohlen zu verkaufen": to_sell,
                "Rest-Core (ungefähr)": int(shares * core_pct),
                "Ladder-Stufe": f"{reached}/{len(LADDER_LEVELS)}",
                "Hinweis": core_text,
            }
        )

    return signals

# ---------------------------------------------------------------
# Hilfsfunktionen – z.B. Reversal-Logik
# ---------------------------------------------------------------


def is_reversal_candidate(analysis, thresholds):
    """
    Entscheidet, ob eine Aktie ein Reversal-Kandidat ist.

    Kriterien (Beispiel, kannst du jederzeit anpassen):
    - Drawdown >= thresholds["reversal_dd_min"]
    - 52W-Stage in bestimmten Phasen
    - Wave-Signal in Re-Entry-Zone oder starker Korrektur
    """
    dd = analysis.get("dd_52w")
    stage = analysis.get("stage_52w", "")
    wave = analysis.get("wave", "")

    if dd is None:
        return False

    min_dd = thresholds.get("reversal_dd_min", -30)

    if dd <= min_dd and ("Korrektur" in stage or "Re-Entry" in wave or "DIP" in wave):
        return True

    return False


# ---------------------------------------------------------------
# TAB: Aktionen
# ---------------------------------------------------------------


def render_actions_tab(cfg, thresholds):
    # Makro nur einmal berechnen
    macro = compute_macro_context()

    portfolio, analyses_portfolio, rows_portfolio, gesamt_wert, gesamt_einsatz = build_portfolio_overview(
        cfg, thresholds
    )

    # WKN-Mapping aus dem AI-Universe (Ticker -> WKN)
    universe_for_wkn = load_ai_universe().get("ai_universe", [])
    wkn_map = {
        entry["ticker"]: entry.get("wkn", "—")
        for entry in universe_for_wkn
        if entry.get("ticker")
    }

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

            action_rows.append(
                {
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
                }
            )

        # --------------------------------------------------------
        # Reversal-Fokus im Depot (Karten)
        # --------------------------------------------------------
        reversal_candidates = []
        for row in action_rows:
            analysis = row["analysis"]
            sts, las = score_dual_candidate(analysis, thresholds, macro)
            if is_reversal_candidate(analysis, thresholds):
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

                    wkn = wkn_map.get(row["Ticker"], "—")

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
                          <div class="stock-card-row"><b>WKN:</b> {wkn}</div>
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
            wkn = wkn_map.get(row["Ticker"], "—")
            if pl is None:
                badge_class = "badge-neutral"
                pl_text = "n/a"
            elif pl >= 0:
                badge_class = "badge-profit"
                pl_text = f"+{pl:.1f} %"
            else:
                badge_class = "badge-loss"
                pl_text = f"{pl:.1f} %"

            ladder = row.get("Targets") or []
            if ladder:
                ladder_str = " → ".join(f"{t:.2f}" for t in ladder)
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
                  <div class="stock-card-row"><b>WKN:</b> {wkn}</div>
                  <div class="stock-card-row"><b>Stücke:</b> {row['Stücke']}</div>
                  <div class="stock-card-row"><b>Einstand / Kurs:</b> {row['Einstand (EK)']} → {row['Aktueller Kurs']}</div>
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
                wkn = wkn_map.get(row["Ticker"], "—")
                st.markdown(
                    f"- **{row['Name']} ({row['Ticker']})** – Aktion **{row['Aktion']}**, "
                    f"P/L {row['P/L %']} %, nächstes Ziel: **{nxt_txt}**."
                )
                st.markdown(f"- WKN: **{wkn}**")
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

            # Aktien ohne handelbaren Kurs ODER „Zombie“-Flag ignorieren
            if (
                analysis["price"] is None
                or analysis.get("is_zombie")
                or analysis.get("is_untradable")
            ):
                continue

            sts, las = score_dual_candidate(analysis, thresholds, macro)

            # Universe-Reversals sammeln
            if is_reversal_candidate(analysis, thresholds):
                universe_reversals.append((sts, las, analysis, entry))

            scored.append((sts, las, analysis, entry))

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
            n_cols = 3 if len(rev_top) >= 3 else 2
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
                          <div class="stock-card-row"><b>WKN:</b> {entry.get('wkn', '—')}</div>
                          <div class="stock-card-row"><b>Kurs:</b> {round(analysis['price'], 2) if analysis['price'] else 'n/a'}</div>
                          <div class="stock-card-row"><b>52W-Stage:</b> {analysis['stage_52w']}</div>
                          <div class="stock-card-row"><b>Wave-Signal:</b> {analysis['wave']}</div>
                          <div class="stock-card-row"><b>Trend:</b> {analysis['trend']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        # --------------------------------------------------------
        # Top 3 Kaufideen – NUR echte Kaufkandidaten (grüne Ampel)
        # --------------------------------------------------------
        # 1) Zuerst alle potenziellen Kaufkandidaten filtern:
        buy_candidates = [
            (sts, las, analysis, entry)
            for (sts, las, analysis, entry) in scored
            if sts >= 65 or las >= 60
        ]

        # 2) Falls weniger als 3 grüne Kandidaten existieren,
        #    mit den besten Gesamtwerten auffüllen (damit die Sektion nicht leer ist).
        if len(buy_candidates) < 3:
            buy_candidates = scored

        # 3) Nach STS (und LAS als tie-breaker) sortieren
        buy_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top3 = buy_candidates[:3]

        if top3:
            st.markdown(
                icon_html(
                    "social_leaderboard_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="mustard",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Kaufideen</span>",
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
                          <div class="stock-card-row"><b>WKN:</b> {entry.get('wkn', '—')}</div>
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
                    "account_balance_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="teal",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Detail-Reports – Top 3 Kaufideen</span>",
                unsafe_allow_html=True,
            )

            macro_state = macro.get("regime", "unknown")

            for rank, (sts, las, best_analysis, best_entry) in enumerate(top3, start=1):
                with st.expander(
                    f"{rank}. {best_analysis['name']} ({best_analysis['ticker']}) – "
                    f"STS {sts}, LAS {las}"
                ):
                    col_l, col_r = st.columns(2)
                    with col_l:
                        st.markdown("**Technische Lage**")
                        st.markdown(
                            f"- Kurs: **{round(best_analysis['price'], 2) if best_analysis['price'] else 'n/a'}**"
                        )
                        st.markdown(f"- WKN: **{best_entry.get('wkn', '—')}**")
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
                            st.markdown(
                                "- Befindet sich in/nahe einer **Re-Entry-Zone** – gute Basis für Wellentrading."
                            )
                        if "starke Korrektur" in best_analysis["stage_52w"]:
                            st.markdown(
                                "- Kurs in **starker Korrektur** – interessant für gestaffelte Käufe."
                            )
                        if "DIP" in best_analysis["wave"] or "DIP" in best_analysis["stage_52w"]:
                            st.markdown("- **DIP-Charakter** – Chance, einen starken Trend günstiger zu erwischen.")
                        if best_analysis.get("is_wave"):
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
**Wie liest man dieses Radar?**

**STS (Short-Term Score – Trading-Fokus)**  
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
                or analysis.get("is_zombie")
                or analysis.get("is_untradable")
            ):
                continue

            sts, las = score_dual_candidate(analysis, thresholds, macro)

            # Ampel-Logik mit Emojis:
            # Grün = klar kaufbar (STS ≥ 65 oder LAS ≥ 60)
            # Gelb = Watchlist / opportunistischer Kauf (STS 50–65 oder LAS 50–60)
            # Rot = kein Kauf / nur beobachten
            if sts >= 65 or las >= 60:
                ampel = "🟢 Kauf-Zone"
            elif sts >= 50 or las >= 50:
                ampel = "🟡 Watchlist / opportunistisch"
            else:
                ampel = "🔴 Kein Kauf / nur beobachten"

            fund = analysis.get("fundamentals") or {}
            reversal_flag = is_reversal_candidate(analysis, thresholds)

            # dd_52w sicher lesen – kann bei manchen Werten fehlen
            dd_52w = analysis.get("dd_52w")

            rows.append(
                {
                    "Name": analysis["name"],
                    "Ticker": analysis["ticker"],
                    "WKN": entry.get("wkn", "—"),
                    "Kategorie": entry.get("category", ""),
                    "AI-Exposure (1–10)": entry.get("exposure", ""),
                    "STS (Short-Term)": sts,
                    "LAS (Long-Term AGI)": las,
                    "Ampel": ampel,
                    "Setup": "🔁 Reversal" if reversal_flag else "—",
                    "Kurs": round(analysis["price"], 2) if analysis["price"] else None,
                    "Trend": analysis["trend"],
                    "Momentum 20d": analysis["momentum_20d"],
                    "52W-Stage": analysis["stage_52w"],
                    "Drawdown 52W (%)": round(dd_52w, 1) if dd_52w is not None else None,
                    "Umsatzwachstum 1Y (%)": round(fund["rev_growth_1y"], 1)
                    if fund.get("rev_growth_1y") is not None
                    else None,
                    "Nettomarge (%)": round(fund["net_margin"], 1)
                    if fund.get("net_margin") is not None
                    else None,
                    "Debt/Assets": round(fund["debt_to_assets"], 2)
                    if fund.get("debt_to_assets") is not None
                    else None,
                    "Wave-Signal": analysis["wave"],
                    "TP-Level": round(analysis["wave_tp_level"], 2)
                    if analysis.get("wave_tp_level")
                    else None,
                    "Re-Entry-Level": round(analysis["wave_reentry_level"], 2)
                    if analysis.get("wave_reentry_level")
                    else None,
                }
            )

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

    # Portfolio-Übersicht aus der Analyse-Engine holen
    portfolio, analyses_portfolio, rows, gesamt_wert, gesamt_einsatz = build_portfolio_overview(
        cfg, thresholds
    )

    # WKN-Mapping aus dem AI-Universe (Ticker -> WKN)
    universe_for_wkn = load_ai_universe().get("ai_universe", [])
    wkn_map = {
        entry["ticker"]: entry.get("wkn", "—")
        for entry in universe_for_wkn
        if entry.get("ticker")
    }

    if not portfolio:
        st.info("Noch keine Positionen im Portfolio. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
        return

    # Kennzahlen oben
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Gesamt-Einsatz", f"{gesamt_einsatz:,.2f} USD")
    with col2:
        st.metric("Gesamt-Wert", f"{gesamt_wert:,.2f} USD")

    # Kartenansicht der Depot-Positionen
    st.markdown(
        icon_html(
            "account_balance_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=18,
            variant="teal",
        )
        + "<span style='font-size:1.0rem;font-weight:600;'>Aktuelle Aktien im Depot</span>",
        unsafe_allow_html=True,
    )

    for r in rows:
        pl = r["P/L %"]
        wkn = wkn_map.get(r["Ticker"], "—")
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
              <div class="stock-card-row"><b>WKN:</b> {wkn}</div>
              <div class="stock-card-row"><b>Stücke:</b> {r['Stücke']}</div>
              <div class="stock-card-row"><b>Einstand / Kurs:</b> {r['Einstand (EK)']} → {r['Kurs']}</div>
              <div class="stock-card-row"><b>Wave:</b> {r['Wave']}</div>
              <div class="stock-card-row"><b>Signal:</b> {r['Signal']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Kursverlauf – 1-Jahres-Chart für gewählte Position
    tickers = [p["ticker"] for p in portfolio]
    st.markdown("---")
    choice = st.selectbox("Kursverlauf anzeigen für:", options=tickers)
    sel = next(p for p in portfolio if p["ticker"] == choice)
    sel_analysis = analyze_ticker(
        name=sel["name"],
        ticker=sel["ticker"],
        thresholds=thresholds,
    )
    wkn_sel = wkn_map.get(sel["ticker"], "—")
    st.write(
        f"Preisverlauf 1 Jahr – {sel_analysis['name']} ({sel_analysis['ticker']}) – WKN: {wkn_sel}"
    )
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

    # -------------------------------------------------------
    # Ladder-Sell-Engine: heutige Verkaufssignale
    # -------------------------------------------------------
    st.markdown("---")
    st.markdown(
        "<span style='font-size:1.0rem;font-weight:600;'>Ladder-Sell-Engine – heutige Verkaufssignale</span>",
        unsafe_allow_html=True,
    )

    # Neue Version: arbeitet nur mit rows, dadurch robust
    ladder_signals = compute_ladder_signals(rows)

    if not ladder_signals:
        st.info(
            "Aktuell keine Ladder-Verkaufssignale – entweder noch im Aufbau oder (noch) kein Gewinn."
        )
    else:
        df_ladder = pd.DataFrame(ladder_signals)
        st.dataframe(df_ladder, use_container_width=True)



# ---------------------------------------------------------------
# TAB: Trade eintragen
# ---------------------------------------------------------------

def render_trades_tab(cfg):
    # -----------------------------------------------------------
    # Hilfsfunktion: Portfolio vollständig aus dem Journal aufbauen
    # -----------------------------------------------------------
    def _rebuild_portfolio_from_journal(cfg):
        """
        Baut cfg["portfolio"] komplett aus cfg["journal"] neu auf.

        - Journal ist die Quelle der Wahrheit.
        - Kauf = positive Stückzahl, Verkauf = negative Stückzahl.
        - Vorhandene Ladder-Targets pro Ticker bleiben erhalten.
        """
        journal = cfg.get("journal", [])

        # Bisherige Targets sichern, damit sie nicht verloren gehen
        old_targets = {
            (p.get("ticker") or "").upper(): p.get("targets", [])
            for p in cfg.get("portfolio", [])
            if p.get("ticker")
        }

        positions = {}

        for j in journal:
            ticker = (j.get("ticker") or "").upper()
            if not ticker:
                continue

            name = j.get("name") or ticker
            trade_type = j.get("type", "Kauf")
            shares = float(j.get("shares") or 0)
            price = float(j.get("price") or 0)
            date = j.get("date")

            # Vorzeichen nach Trade-Typ
            signed_shares = -abs(shares) if trade_type == "Verkauf" else abs(shares)

            pos = positions.setdefault(
                ticker,
                {"name": name, "ticker": ticker, "targets": [], "trades": []},
            )
            pos["trades"].append(
                {"date": date, "shares": signed_shares, "price": price}
            )

        # Gespeicherte Targets je Ticker wieder anhängen
        for ticker, pos in positions.items():
            if ticker in old_targets:
                pos["targets"] = old_targets[ticker]

        cfg["portfolio"] = list(positions.values())

    # -----------------------------------------------------------
    # Überschrift
    # -----------------------------------------------------------
    st.markdown(
        icon_html(
            "edit_document_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=24,
            variant="teal",
        )
        + "<span style='font-size:1.05rem;font-weight:600;'>Neuen Trade eintragen</span>",
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------
    # 1) Trade-Formular
    # -----------------------------------------------------------
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
        # Plausibilitätsprüfung
        if not ticker or shares == 0 or price <= 0:
            st.error("Bitte mindestens Ticker, Stückzahl (≠ 0) und Preis > 0 angeben.")
        else:
            # Datum prüfen / setzen
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            else:
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    st.error("Datum ungültig, bitte im Format YYYY-MM-DD.")
                    return

            # Portfolio-Eintrag nur nutzen, um ggf. Targets zu speichern
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
                    "trades": [],  # wird gleich aus Journal neu aufgebaut
                }
                cfg.setdefault("portfolio", []).append(pos)
            else:
                # Falls neue Zielkurse angegeben wurden → überschreiben
                if targets_str:
                    pos["targets"] = [float(x) for x in targets_str.split(",")]

            # Journal-Eintrag erzeugen (Journal = Wahrheit)
            journal = cfg.setdefault("journal", [])
            next_id = max((j.get("id", 0) for j in journal), default=0) + 1
            journal.append(
                {
                    "id": next_id,
                    "ticker": ticker,
                    "name": name or ticker,
                    "type": trade_type,
                    "shares": float(shares),
                    "price": float(price),
                    "date": date_str,
                }
            )

            # Portfolio komplett aus Journal neu aufbauen
            _rebuild_portfolio_from_journal(cfg)
            save_config(cfg)

            st.success(
                f"Trade gespeichert: {trade_type} {shares} x {ticker} @ {price} am {date_str}"
            )

    # -----------------------------------------------------------
    # 2) Trade-Journal (Übersicht + Einzel-Löschung)
    # -----------------------------------------------------------
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

        # Einzelnen Trade löschen
        st.markdown("**Einzelnen Trade aus dem Journal löschen**")
        trade_ids = [j["id"] for j in journal]
        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            sel_id = st.selectbox(
                "Trade-ID auswählen (siehe Tabelle oben):",
                options=trade_ids,
            )
        with col_btn:
            if st.button("Ausgewählten Trade löschen"):
                cfg["journal"] = [
                    j for j in cfg.get("journal", []) if j.get("id") != sel_id
                ]
                _rebuild_portfolio_from_journal(cfg)
                save_config(cfg)
                st.success(
                    f"Trade mit ID {sel_id} wurde aus Journal und Portfolio entfernt."
                )

    # -----------------------------------------------------------
    # 3) Optional: ganze Aktie (alle Trades) löschen
    # -----------------------------------------------------------
    st.markdown("---")
    st.markdown("**Optional: Aktie vollständig aus Depot & Journal löschen**")

    # Portfolio wird nur genutzt, um die aktuell vorhandenen Ticker zu zeigen
    portfolio = cfg.get("portfolio", [])
    if not portfolio:
        st.info("Aktuell keine Positionen im Depot, nichts zu löschen.")
        return

    depot_ticker = sorted({p.get("ticker") for p in portfolio if p.get("ticker")})

    col_sel2, col_btn2 = st.columns([3, 1])
    with col_sel2:
        delete_choice = st.selectbox(
            "Ticker auswählen (alle Trades dieser Aktie werden gelöscht):",
            options=["— Bitte auswählen —"] + depot_ticker,
            index=0,
        )

    with col_btn2:
        if st.button("Alle Trades dieser Aktie löschen"):
            if delete_choice == "— Bitte auswählen —":
                st.warning("Bitte zuerst einen Ticker auswählen.")
            else:
                # Nur Journal-Einträge entfernen – Portfolio wird danach rekonstruiert
                cfg["journal"] = [
                    j
                    for j in cfg.get("journal", [])
                    if j.get("ticker") != delete_choice
                ]
                _rebuild_portfolio_from_journal(cfg)
                save_config(cfg)
                st.success(
                    f"Alle Trades zu {delete_choice} wurden aus Journal und Portfolio entfernt. "
                    f"Die Aktie bleibt natürlich im AI Universe Radar erhalten."
                )