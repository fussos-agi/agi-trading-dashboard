from datetime import datetime

import streamlit as st
import pandas as pd
import altair as alt  # für schönere Charts

from config_utils import (
    load_ai_universe,
    save_config,
    find_portfolio_entry,
    rebuild_portfolio_from_journal,
)
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
# Ladder-Sell-Engine – Basislogik
# ---------------------------------------------------------------

LADDER_LEVELS = [0.30, 0.50, 0.75, 1.00, 1.50, 2.00]  # +30 %, +50 %, ...


def _get_exposure_map():
    uni = load_ai_universe()
    exposure_map = {}
    for entry in uni.get("ai_universe", []):
        ticker = (entry.get("ticker") or "").upper()
        if ticker:
            exposure_map[ticker] = entry.get("exposure")
    return exposure_map


def _core_and_ladder_pct(exposure):
    """
    Core- und Ladder-Anteile anhand AI-Exposure:
    - 9–10: 20 % Core behalten, 80 % laddern
    - 7–8 : 10 % Core behalten, 90 % laddern
    - 1–6 : 0 % Core, 100 % laddern (Komplett-Verkauf über Zeit)
    """
    if exposure is None:
        return 0.0, 1.0
    if exposure >= 9:
        return 0.20, 0.80
    if exposure >= 7:
        return 0.10, 0.90
    return 0.0, 1.0


def compute_ladder_signals(rows):
    """
    Alte Übersicht: Ladder-Engine ohne Fortschrittstracking.
    Wird weiterhin im Portfolio-Tab als Gesamtübersicht verwendet.
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
                "Core-Hinweis": core_text,
            }
        )

    return signals


# ---------------------------------------------------------------
# Ladder-Sell-Engine – tagesaktuelle Aktionen mit Fortschritt
# ---------------------------------------------------------------


def compute_daily_ladder_actions(rows, ladder_progress):
    exposure_map = _get_exposure_map()
    signals = []

    for r in rows:
        ticker_raw = r.get("Ticker")
        ticker = (ticker_raw or "").upper()
        name = r.get("Name")
        shares = r.get("Stücke") or 0
        pl_pct = r.get("P/L %")

        if not ticker or shares <= 0:
            continue
        if pl_pct is None or pl_pct <= 0:
            continue

        exposure = exposure_map.get(ticker)
        core_pct, ladder_pct = _core_and_ladder_pct(exposure)

        ladder_shares = int(shares * ladder_pct)
        if ladder_shares <= 0:
            continue

        profit_frac = pl_pct / 100
        max_levels = len(LADDER_LEVELS)
        levels_done = int(ladder_progress.get(ticker, 0))

        if levels_done >= max_levels:
            continue

        next_level_threshold = LADDER_LEVELS[levels_done]
        if profit_frac < next_level_threshold:
            continue

        frac_done = levels_done / max_levels
        frac_after = (levels_done + 1) / max_levels
        to_sell_before = int(ladder_shares * frac_done)
        to_sell_after = int(ladder_shares * frac_after)
        to_sell = max(0, to_sell_after - to_sell_before)

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
                "Ticker": ticker_raw,
                "TickerKey": ticker,
                "Exposure": exposure,
                "Gewinn %": round(pl_pct, 1),
                "Aktuelle Stufe": f"{levels_done}/{max_levels}",
                "Nächste Stufe": f"{levels_done + 1}/{max_levels}",
                "Schwelle nächste Stufe (%)": int(next_level_threshold * 100),
                "Empfohlen zu verkaufen": to_sell,
                "Core-Hinweis": core_text,
            }
        )

    return signals


# ---------------------------------------------------------------
# Hilfsfunktionen – z.B. Reversal-Logik
# ---------------------------------------------------------------


def is_reversal_candidate(analysis, thresholds):
    """
    Entscheidet, ob eine Aktie ein Reversal-Kandidat ist.
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
# TAB: Aktionen (HOME)
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
    # Vorwort / Mission Statement für die Home-Seite
    # -----------------------------------------------------------
    st.markdown("""
    <div style='padding: 1.2rem 1.6rem; background: #B7410E; 
                color: #FFF7E5; border-radius: 18px; 
                box-shadow: 0 6px 20px rgba(0,0,0,0.25);'>

    <h2 style='margin-top:0; color:#FFF7E5; font-weight:700;'>
        Willkommen auf AGI & AI Trading APP
    </h2>

    <p style='font-size:1.05rem; line-height:1.55;'>
    Diese Plattform verfolgt ein klares Ziel: 
    <b>systematisch jene Unternehmen zu identifizieren, die vom globalen Durchbruch künstlicher 
    Allgemeiner Intelligenz (AGI) am stärksten profitieren werden.</b>
    </p>

    <p style='font-size:1.05rem; line-height:1.55;'>
    Wir sammeln, analysieren und gewichten ein wachsendes Universum an börsennotierten 
    AGI- und AI-Werten, um schon heute die Positionen aufzubauen, die in den kommenden 
    fünf Jahren den größten strukturellen Vorteil besitzen. 
    Während die Welt erst langsam begreift, was vor uns liegt, wollen wir 
    <b>früh, organisiert und konsequent investiert sein</b>.
    </p>

    <p style='font-size:1.05rem; line-height:1.55;'>
    Unsere Strategie kombiniert <b>Bottom-Fishing</b> und <b>Momentum-Zyklen</b>:  
    Wir kaufen in <b>Korrekturphasen</b>, akkumulieren systematisch und realisieren Gewinne 
    durch <b>Ladder-Sales</b>, wenn Kurse in überdehnte Zonen laufen.  
    So wächst das Depot kontinuierlich – und schafft Kapitalreserven zur weiteren 
    Akkumulation hochwertiger AGI-Kernwerte.
    </p>

    <p style='font-size:1.05rem; line-height:1.55;'>
    Diese APP unterstützt dich dabei:
    </p>
    <ul style='font-size:1.0rem; line-height:1.5; margin-left:1.2rem;'>
      <li>Unterbewertete AI-Assets frühzeitig zu erkennen</li>
      <li>Trendstärke & Volatilität objektiv zu analysieren</li>
      <li>Kaufzonen & Ausstiegsniveaus präzise zu bestimmen</li>
      <li>Tägliche Handlungsbedarfe auf einen Blick zu sehen</li>
      <li>Ein langfristiges, robustes High-Conviction-AGI-Portfolio aufzubauen</li>
    </ul>

    <p style='font-size:1.05rem; line-height:1.55;'>
    Wir bauen kein kurzfristiges Trading-Depot –  
    <b>wir bauen ein strategisches AGI-Fundament für die kommende Superzyklus-Phase.</b>
    </p>

    <p style='font-size:1.1rem; font-weight:600; margin-bottom:0;'>
    Wenn der globale Run auf AGI-Unternehmen beginnt, wollen wir nicht erst einsteigen –  
    wir wollen bereitstehen. Mit vollen Positionen.
    </p>

    <p style='font-size:1.1rem; margin-top:0.5rem;'>
    <b>Let’s accumulate the future.</b>
    </p>

    </div>

    """, unsafe_allow_html=True)

    st.markdown("---")



    # -----------------------------------------------------------
    # Portfolio-Aktionen (Karten)
    # -----------------------------------------------------------
    if not portfolio:
        st.info("Noch keine Portfolio-Analysen verfügbar. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
    else:
        # 👉 Daily Action Center – Ladder-Verkäufe heute
        #    wird jetzt als erstes Element auf der HOME-Seite angezeigt.
        render_daily_actions_tab(cfg, thresholds)
        st.markdown("---")

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
                            {header_icon} Reversal-Kandidat
                          </div>
                          <div class="stock-card-sub">
                            {row['Name']} ({row['Ticker']}) – WKN: {wkn}
                          </div>
                          <div class="stock-card-row">
                            <span class="badge-pill {badge_class}">{pl_text}</span>
                            &nbsp; EK: {row['Einstand (EK)'] or 'n/a'} – Kurs: {row['Aktueller Kurs'] or 'n/a'}
                          </div>
                          <div class="stock-card-row">
                            Trend: {row['Trend']}<br/>
                            Wave: {row['Wave-Signal']}
                          </div>
                          <div class="stock-card-row">
                            Aktion: <b>{row['Aktion']}</b><br/>
                            <span style="font-size:0.78rem;color:#e5e7eb;">{row['Begründung']}</span>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        # --------------------------------------------------------
        # Top 3 Kaufideen (Detail-Reports)
        # --------------------------------------------------------
        if action_rows:
            macro_state = macro.get("regime", "unknown")

            # nach STS sortieren (über score_dual_candidate)
            scored = []
            for row in action_rows:
                analysis = row["analysis"]
                sts, las = score_dual_candidate(analysis, thresholds, macro)
                scored.append((sts, las, row, analysis))

            scored.sort(key=lambda x: x[0], reverse=True)
            top3 = scored[:3]

            st.markdown("---")
            st.markdown(
                icon_html(
                    "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
                    size=18,
                    variant="mustard",
                )
                + "<span style='font-size:1.0rem;font-weight:600;'>Detail-Reports – Top 3 Kaufideen</span>",
                unsafe_allow_html=True,
            )

            for sts, las, row, best_analysis in top3:
                wkn = wkn_map.get(row["Ticker"], "—")
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

                st.markdown(
                    f"""
                    <div class="stock-card">
                      <div class="stock-card-header">
                        {row['Name']} ({row['Ticker']}) – WKN: {wkn}
                      </div>
                      <div class="stock-card-sub">
                        <span class="badge-pill {badge_class}">{pl_text}</span>
                        &nbsp; STS: {sts:.1f} – LAS: {las:.1f}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown("**Technische Lage**")
                    st.markdown(f"- Trend: {best_analysis['trend']}")
                    st.markdown(f"- 52W-Stage: {best_analysis['stage_52w']}")
                    st.markdown(f"- Momentum 20d: {best_analysis['momentum_20d']}")
                    if best_analysis.get("wave_swing_low") is not None:
                        lo = best_analysis["wave_swing_low"]
                        hi = best_analysis["wave_swing_high"]
                        st.markdown(f"- Letzter Swing: Tief ~{lo:.2f}, Hoch ~{hi:.2f}")
                    if best_analysis.get("wave_tp_level") is not None:
                        tp = best_analysis["wave_tp_level"]
                        st.markdown(f"- Geschätztes TP-Level: **{tp:.2f}**")
                    if best_analysis.get("wave_reentry_level") is not None:
                        re = best_analysis["wave_reentry_level"]
                        st.markdown(f"- Geschätztes Re-Entry-Level: **{re:.2f}**")
                    dte = best_analysis.get("days_to_earnings")
                    if dte is not None:
                        st.markdown(f"- Tage bis Earnings: **{dte}**")

                with col_r:
                    st.markdown("**Story & Begründung**")
                    best_entry = next(
                        (e for e in universe_for_wkn if e.get("ticker") == row["Ticker"]),
                        {},
                    )
                    st.markdown(
                        f"- Kategorie: **{best_entry.get('category', 'n/a')}**, "
                        f"AI-Exposure: **{best_entry.get('exposure', 'n/a')}/10**"
                    )
                    st.markdown(f"- Setup: {best_analysis['wave']}")
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

                    macro_state = macro.get("regime", "unknown")
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

    st.markdown(
        """
**Wie liest man dieses Radar?**

**STS (Short-Term Score – Trading-Fokus)**  
- 0–30 → ignorieren / nur beobachten  
- 30–50 → „Watchlist“, es formt sich etwas, aber noch kein klarer Entry  
- 50–65 → opportunistischer Kauf möglich (guter DIP oder Re-Entry-Zone, aber noch nicht extrem)  
- >65 → Top-Trading-Kandidat (starker DIP, ordentliche Wellen-Struktur)

**LAS (Long-Term AGI Score – langfristig einsammeln)**  
- 0–40 → kein spannender Langfrist-Case  
- 40–60 → solide, kann man mitnehmen  
- >60 → AGI-Kernkandidat: tiefer 52W-Drawdown + klarer AGI-Bonus → ideal zum langsam Einsammeln
        """
    )

    macro_state = macro.get("regime", "unknown")
    dd_spy = macro.get("dd_spy")
    if dd_spy is not None:
        st.markdown(
            f"> **Aktuelles Makro-Regime:** {macro_state} (S&P Drawdown ca. {dd_spy:.1f}%)"
        )
    else:
        st.markdown(f"> **Aktuelles Makro-Regime:** {macro_state}")

    # -----------------------------------------------------------
    # Universe laden
    # -----------------------------------------------------------
    universe = load_ai_universe().get("ai_universe", [])
    if not universe:
        st.warning("Keine AI-Universe-Daten gefunden. Bitte ai_universe.json prüfen.")
        return

    rows = []
    for entry in universe:
        analysis = analyze_ticker(
            name=entry["name"],
            ticker=entry["ticker"],
            thresholds=thresholds,
        )

        # Unhandlbare / tote Werte überspringen
        if (
            analysis["price"] is None
            or analysis.get("is_zombie")
            or analysis.get("is_untradable")
        ):
            continue

        sts, las = score_dual_candidate(analysis, thresholds, macro)

        if sts >= 65 or las >= 60:
            ampel = "🟢 Kauf-Zone"
        elif sts >= 50 or las >= 50:
            ampel = "🟡 Watchlist / opportunistisch"
        else:
            ampel = "🔴 Kein Kauf / nur beobachten"

        fund = analysis.get("fundamentals") or {}
        reversal_flag = is_reversal_candidate(analysis, thresholds)
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

    # -----------------------------------------------------------
    # DataFrame bauen & sortieren
    # -----------------------------------------------------------
    df = pd.DataFrame(rows)
    if df.empty:
        st.info(
            "Aktuell gibt es keine AI/AGI-Kandidaten, die die Filterkriterien erfüllen."
        )
        return

    # Top-Kaufideen nach STS sortiert
    df = df.sort_values("STS (Short-Term)", ascending=False)

    # -----------------------------------------------------------
    # Retro-Table-Styling – exakt wie im Trade-Journal
    # -----------------------------------------------------------
    styled_df = (
        df.style
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#BE5103"),  # Header burnt orange
                        ("color", "white"),
                        ("font-family", '"Montserrat", sans-serif'),
                        ("font-weight", "600"),
                        ("text-align", "left"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("background-color", "#FFCE1B"),  # Body mustard yellow
                        ("color", "#111111"),
                        ("font-family", '"Inter", sans-serif'),
                    ],
                },
                {
                    "selector": "tbody tr",
                    "props": [("background-color", "#FFCE1B")],
                },
            ]
        )
        .set_properties(
            **{
                "background-color": "#FFCE1B",
                "color": "#111111",
                "border-bottom": "1px solid rgba(0,0,0,0.10)",
            }
        )
    )

    # WICHTIG: wie im Journal -> st.table, damit der gelbe/orange Rand korrekt gerendert wird
    st.table(styled_df)

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

    portfolio, analyses_portfolio, rows, gesamt_wert, gesamt_einsatz = build_portfolio_overview(
        cfg, thresholds
    )

    universe_for_wkn = load_ai_universe().get("ai_universe", [])
    wkn_map = {
        entry["ticker"]: entry.get("wkn", "—")
        for entry in universe_for_wkn
        if entry.get("ticker")
    }
    # zusätzliche Maps für Kategorie & Exposure
    category_map = {
        entry["ticker"]: entry.get("category", "n/a")
        for entry in universe_for_wkn
        if entry.get("ticker")
    }
    exposure_map = {
        entry["ticker"]: entry.get("exposure", None)
        for entry in universe_for_wkn
        if entry.get("ticker")
    }

    if not portfolio:
        st.info("Noch keine Positionen im Portfolio. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Gesamt-Einsatz", f"{gesamt_einsatz:,.2f} USD")
    with col2:
        st.metric("Gesamt-Wert", f"{gesamt_wert:,.2f} USD")

    st.markdown(
        icon_html(
            "account_balance_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=18,
            variant="teal",
        )
        + "<span style='font-size:1.0rem;font-weight:600;'>Aktuelle Aktien im Depot</span>",
        unsafe_allow_html=True,
    )

    # ---------------------------
    # Karten pro Depot-Position
    # ---------------------------
    for r in rows:
        ticker = r["Ticker"]
        ticker_u = (ticker or "").upper()
        analysis, total_shares = analyses_portfolio.get(ticker_u, (None, None))

        # Fallback, falls irgendwas schiefgeht
        if analysis is None:
            analysis = {}
            total_shares = r.get("Stücke", 0)

        # Kategorie & Exposure aus ai_universe.json
        category = category_map.get(ticker, "n/a")
        exposure = exposure_map.get(ticker)
        exposure_txt = f"{exposure}/10" if exposure is not None else "n/a"

        # Ladder-Ziele & nächstes Ziel
        ladder_targets = analysis.get("targets") or []
        if ladder_targets:
            ladder_str = " \u2192 ".join(f"{t:.2f}" for t in ladder_targets)  # →-Pfeil
        else:
            ladder_str = "keine definiert"
        next_target = analysis.get("next_target")

        # Empfehlung + Begründung aus decide_portfolio_action()
        action, reason = decide_portfolio_action(analysis, total_shares)

        # Momentum / 52W-Stage
        momentum_20d = analysis.get("momentum_20d", "n/a")
        stage_52w = analysis.get("stage_52w", "n/a")

        # P/L Badge
        pl = r["P/L %"]
        wkn = wkn_map.get(ticker, "—")
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
                {r['Name']} ({ticker})
              </div>
              <div class="stock-card-sub">
                <span class="badge-pill {badge_class}">{pl_text}</span>
                &nbsp;
                Stücke: {r['Stücke']} – EK: {r['Einstand (EK)'] or 'n/a'} – WKN: {wkn}
              </div>
              <div class="stock-card-row">
                Aktueller Kurs: {r['Aktueller Kurs'] or 'n/a'} – Wert: {r['Wert gesamt'] or 'n/a'}
              </div>
              <div class="stock-card-row">
                <b>Kategorie:</b> {category}<br/>
                <b>AI-Exposure:</b> {exposure_txt}
              </div>
              <div class="stock-card-row">
                <b>Ladder-Ziele:</b> {ladder_str}<br/>
                <b>Nächstes Ladder-Ziel:</b> {next_target if next_target is not None else 'n/a'}
              </div>
              <div class="stock-card-row">
                <b>Empfehlung:</b> {action}<br/>
                <span style="font-size:0.78rem;color:#e5e7eb;">{reason}</span>
              </div>
              <div class="stock-card-row">
                <b>Momentum 20d:</b> {momentum_20d}<br/>
                <b>52W-Stage:</b> {stage_52w}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---------------------------
    # Kursverlauf-Chart
    # ---------------------------
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


# ---------------------------------------------------------------
# TAB: Daily Action Center – tagesaktuelle Ladder-Verkäufe
# ---------------------------------------------------------------


def render_daily_actions_tab(cfg, thresholds):
    st.markdown(
        icon_html(
            "alarm_48dp_1F1F1F_FILL0_wght400_GRAD0_opsz48.svg",
            size=24,
            variant="burnt",
        )
        + "<span style='font-size:1.05rem;font-weight:600;'>Daily Action Center – Ladder-Verkäufe heute</span>",
        unsafe_allow_html=True,
    )

    portfolio, analyses_portfolio, rows, gesamt_wert, gesamt_einsatz = build_portfolio_overview(
        cfg, thresholds
    )

    if not portfolio:
        st.info("Noch keine Positionen im Portfolio. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
        return

    ladder_progress = cfg.setdefault("ladder_progress", {})

    # tagesaktuelle Aktionen berechnen
    signals = compute_daily_ladder_actions(rows, ladder_progress)

    if not signals:
        st.info("Heute wurden keine neuen Ladder-Stufen ausgelöst. Alles im grünen Bereich – HOLD.")
        return

    df = pd.DataFrame(signals)
    st.dataframe(df, use_container_width=True)

    # Bedien-Logik: Ladder-Stufe manuell als erledigt markieren
    st.markdown("---")
    st.markdown("**Ladder-Stufe als erledigt markieren (nachdem du den Verkauf ausgeführt hast)**")

    tickers_with_action = sorted({s["Ticker"] for s in signals})
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        sel_ticker = st.selectbox(
            "Ticker auswählen:",
            options=tickers_with_action,
        )
    with col_btn:
        if st.button("Stufe erledigt"):
            key = sel_ticker.upper()
            done_before = int(ladder_progress.get(key, 0))
            max_levels = len(LADDER_LEVELS)
            if done_before >= max_levels:
                st.info("Für diese Aktie sind bereits alle Ladder-Stufen erledigt.")
            else:
                ladder_progress[key] = done_before + 1
                cfg["ladder_progress"] = ladder_progress
                save_config(cfg)
                st.success(
                    f"Ladder-Stufe für {sel_ticker} auf {done_before + 1}/{max_levels} erhöht. "
                    "Bitte den entsprechenden Verkauf im Journal eintragen, falls noch nicht geschehen."
                )


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

    # ---------------------------------------------------------------
    # 1) Trade-Formular
    # ---------------------------------------------------------------
    with st.form("trade_form"):
        ticker = st.text_input("Ticker (z.B. BBAI)").upper().strip()
        name = st.text_input("Name (z.B. BigBear.ai)")
        trade_type = st.selectbox("Art des Trades", ["Kauf", "Verkauf"])
        shares = st.number_input("Anzahl Aktien", step=1.0, value=0.0)
        price = st.number_input("Preis pro Aktie", step=0.01, value=0.0)
        date_str = st.text_input("Datum (YYYY-MM-DD, leer = heute)")
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
                    st.error("Datum ungültig! Bitte YYYY-MM-DD verwenden.")
                    return

            pos = find_portfolio_entry(cfg, ticker)

            if pos is None:
                if not name:
                    name = ticker

                targets = [float(x) for x in targets_str.split(",")] if targets_str else []

                pos = {"name": name, "ticker": ticker, "targets": targets, "trades": []}
                cfg.setdefault("portfolio", []).append(pos)
            else:
                if targets_str:
                    pos["targets"] = [float(x) for x in targets_str.split(",")]

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

            rebuild_portfolio_from_journal(cfg)
            save_config(cfg)

            st.success(f"Trade gespeichert: {trade_type} {shares} x {ticker} @ {price} am {date_str}")

    # ---------------------------------------------------------------
    # 2) Trade-Journal Anzeige (RETRO GELB)
    # ---------------------------------------------------------------
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
        return

    df_j = pd.DataFrame(journal).sort_values("id", ascending=False)

    # Retro-Styling (Burnt Orange Header + Gelber Body)
    styled_journal = (
        df_j.style
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#BE5103"),
                        ("color", "white"),
                        ("font-family", '"Montserrat", sans-serif'),
                        ("font-weight", "600"),
                        ("text-align", "left"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("background-color", "#FFCE1B"),
                        ("color", "#111111"),
                        ("font-family", '"Inter", sans-serif'),
                    ],
                },
                {"selector": "tbody tr", "props": [("background-color", "#FFCE1B")]},
            ]
        )
        .set_properties(
            **{
                "background-color": "#FFCE1B",
                "color": "#111111",
                "border-bottom": "1px solid rgba(0,0,0,0.10)",
            }
        )
    )

    # WICHTIG: Farben nur sichtbar mit st.table, nicht mit st.dataframe
    st.table(styled_journal)

    # ---------------------------------------------------------------
    # 3) Ein Trade löschen
    # ---------------------------------------------------------------
    st.markdown("**Einzelnen Trade aus dem Journal löschen**")

    trade_ids = [j["id"] for j in journal]
    col_sel, col_btn = st.columns([3, 1])

    with col_sel:
        sel_id = st.selectbox("Trade-ID auswählen (siehe Tabelle oben):", trade_ids)

    with col_btn:
        if st.button("Ausgewählten Trade löschen"):
            cfg["journal"] = [j for j in journal if j["id"] != sel_id]
            rebuild_portfolio_from_journal(cfg)
            save_config(cfg)
            st.success(f"Trade {sel_id} wurde gelöscht.")

    # ---------------------------------------------------------------
    # 4) Alle Trades einer Aktie löschen
    # ---------------------------------------------------------------
    st.markdown("---")
    st.markdown("**Optional: Aktie vollständig aus Depot & Journal löschen**")

    portfolio = cfg.get("portfolio", [])
    if not portfolio:
        st.info("Keine Positionen vorhanden.")
        return

    depot_ticker = sorted({p["ticker"] for p in portfolio})

    col_sel2, col_btn2 = st.columns([3, 1])
    with col_sel2:
        delete_choice = st.selectbox(
            "Ticker auswählen:", ["— Bitte auswählen —"] + depot_ticker
        )

    with col_btn2:
        if st.button("Alle Trades dieser Aktie löschen"):
            if delete_choice == "— Bitte auswählen —":
                st.warning("Bitte einen Ticker auswählen.")
            else:
                cfg["journal"] = [j for j in journal if j["ticker"] != delete_choice]
                rebuild_portfolio_from_journal(cfg)
                save_config(cfg)
                st.success(
                    f"Alle Trades zu {delete_choice} wurden entfernt. "
                    "Die Aktie bleibt im AI-Universe-Radar sichtbar."
                )
