import json
from datetime import datetime
from pathlib import Path

import streamlit as st
import yfinance as yf
import pandas as pd

CONFIG_PATH = Path("config.json")


# ---------- Config-Handling ----------

def load_config():
    """
    Lädt die Konfiguration aus config.json.
    Wenn die Datei nicht existiert, leer oder kaputt ist, wird ein Default zurückgegeben.
    """
    default = {
        "currency": "EUR",
        "portfolio": [],
        "watchlist": [],
        "thresholds": {"run_up_pct": 30, "dip_pct": -30},
    }

    if not CONFIG_PATH.exists() or CONFIG_PATH.stat().st_size == 0:
        return default

    try:
        with open(CONFIG_PATH, "r") as f:
            content = f.read().strip()
            if not content:
                return default
            return json.loads(content)
    except json.JSONDecodeError:
        # Falls die Datei mal kaputt ist, nicht abstürzen
        return default


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def find_portfolio_entry(cfg, ticker):
    for pos in cfg.get("portfolio", []):
        if pos.get("ticker", "").upper() == ticker.upper():
            return pos
    return None


# ---------- Kurs- & Analyse-Helfer ----------

def fetch_history(ticker, period="1y"):
    """1 Jahr Kursdaten (Daily) holen."""
    data = yf.Ticker(ticker).history(period=period, interval="1d")
    if data.empty:
        return None
    return data


def moving_average(series, window):
    if len(series) < window:
        return None
    return float(series[-window:].mean())


def summarize_trades(trades):
    """Gesamtstückzahl und gewichteten Durchschnittskurs berechnen."""
    if not trades:
        return 0, None
    total_shares = sum(t["shares"] for t in trades)
    if total_shares == 0:
        return 0, None
    volume = sum(t["shares"] * t["price"] for t in trades)
    avg_price = volume / total_shares
    return total_shares, avg_price


def detect_wave_stock(hist, ma_window=50):
    """
    Erkennt, ob eine Aktie ein 'Wellenkandidat' ist.

    Kriterien:
    - durchschnittliche tägliche Range (High-Low) in % des Schlusskurses
    - wie oft der Schlusskurs die 50-Tage-Linie kreuzt
    """
    if hist is None or len(hist) < ma_window + 30:
        return False, None, None

    closes = hist["Close"]
    highs = hist.get("High", closes)
    lows = hist.get("Low", closes)

    daily_range_pct = (highs - lows) / closes * 100
    avg_range_pct = float(daily_range_pct.mean())

    ma50_series = closes.rolling(ma_window).mean()
    cross_mask = (closes.shift(1) < ma50_series.shift(1)) & (closes > ma50_series)
    cross_mask |= (closes.shift(1) > ma50_series.shift(1)) & (closes < ma50_series)
    n_cross_50 = int(cross_mask.sum())

    is_wave = (avg_range_pct >= 4.0) and (n_cross_50 >= 8)
    return is_wave, avg_range_pct, n_cross_50


def wave_params_from_vol(avg_range_pct):
    """Leitet passende Take-Profit-/Re-Entry-Schwellen aus der Volatilität ab."""
    if avg_range_pct is None:
        return None, None

    if avg_range_pct < 4.0:
        return None, None  # zu ruhig, kein Wellenmodus
    elif avg_range_pct < 6.0:
        return 25, -20
    elif avg_range_pct < 8.0:
        return 35, -30
    else:
        return 50, -35


def classify_trend(price, ma50, ma200):
    if price is None or ma50 is None or ma200 is None:
        return "n/a"
    if price > ma50 > ma200:
        return "🟩 Aufwärtstrend"
    if price < ma50 < ma200:
        return "🟥 Abwärtstrend"
    return "🟧 Seitwärts"


def classify_52w_stage(price, high_52w, low_52w):
    if price is None or high_52w is None or low_52w is None:
        return "n/a"

    drawdown = (price - high_52w) / high_52w * 100
    if high_52w == low_52w:
        pos = 0.0
    else:
        pos = (price - low_52w) / (high_52w - low_52w)

    if drawdown <= -60:
        zone = "Crash-Zone"
    elif drawdown <= -30:
        zone = "starke Korrektur"
    else:
        zone = "nahe am Hoch"

    return f"{zone} (DD {drawdown:.1f}%, Pos {pos:.2f})"


def classify_momentum(price, price_20d_ago, thresholds):
    if price is None or price_20d_ago is None:
        return "n/a"
    change_pct = (price - price_20d_ago) / price_20d_ago * 100
    if change_pct >= thresholds["run_up_pct"]:
        return f"RUN (+{change_pct:.1f}%)"
    if change_pct <= thresholds["dip_pct"]:
        return f"DIP ({change_pct:.1f}%)"
    return f"neutral ({change_pct:+.1f}%)"


def classify_portfolio_position(price, buy_price, targets):
    if price is None or buy_price is None or not targets:
        return "kein Einstand", None, None

    change_pct = (price - buy_price) / buy_price * 100
    reached_levels = [t for t in targets if price >= t]

    if not reached_levels:
        next_target = targets[0]
        return f"unter Ziel 1 ({change_pct:+.1f}%)", next_target, change_pct

    if len(reached_levels) == len(targets):
        return f"über letztem Ziel (+{change_pct:.1f}%)", None, change_pct

    next_target = targets[len(reached_levels)]
    return f"Ziel {len(reached_levels)} erreicht (+{change_pct:.1f}%)", next_target, change_pct


def wave_signal(price, closes, up_pct, down_pct, window=20):
    """Wellenlogik mit dynamischen Schwellwerten."""
    if price is None or len(closes) < window or up_pct is None or down_pct is None:
        return "kein Wellenmodus"

    recent = closes[-window:]
    swing_low = float(recent.min())
    swing_high = float(recent.max())

    if swing_low == 0 or swing_high == 0:
        return "kein Wellenmodus"

    from_low_pct = (price - swing_low) / swing_low * 100
    from_high_pct = (price - swing_high) / swing_high * 100

    if from_low_pct >= up_pct and from_high_pct > -10:
        return f"📈 Take-Profit-Zone (+{from_low_pct:.1f}% über Tief, {from_high_pct:.1f}% unter Hoch)"

    if from_high_pct <= down_pct and from_low_pct < 15:
        return f"📉 Re-Entry-Zone ({from_high_pct:.1f}% unter Hoch, +{from_low_pct:.1f}% über Tief)"

    return f"neutral (vom Tief +{from_low_pct:.1f}%, vom Hoch {from_high_pct:.1f}%)"


def analyze_ticker(name, ticker, buy_price=None, targets=None,
                   ref_price=None, thresholds=None):
    """Zentrale Analysefunktion für einen Ticker."""
    hist = fetch_history(ticker, period="1y")
    if hist is None:
        return {
            "name": name,
            "ticker": ticker,
            "price": None,
            "trend": "n/a",
            "stage_52w": "n/a",
            "momentum_20d": "n/a",
            "status_vs_buy": None,
            "next_target": None,
            "pl_pct": None,
            "status_vs_ref": None,
            "history": None,
            "wave": "kein Wellenmodus",
            "is_wave": False,
            "avg_range_pct": None,
            "n_cross_50": None,
        }

    closes = hist["Close"]
    price = float(closes.iloc[-1])

    ma50 = moving_average(closes, 50)
    ma200 = moving_average(closes, 200)
    high_52w = float(closes.max())
    low_52w = float(closes.min())

    if len(closes) > 20:
        price_20d_ago = float(closes.iloc[-21])
    else:
        price_20d_ago = None

    trend = classify_trend(price, ma50, ma200)
    stage_52w = classify_52w_stage(price, high_52w, low_52w)
    momentum_20d = classify_momentum(price, price_20d_ago, thresholds) if thresholds else "n/a"

    is_wave, avg_range_pct, n_cross_50 = detect_wave_stock(hist)
    up_pct, down_pct = wave_params_from_vol(avg_range_pct)
    wave = wave_signal(price, closes, up_pct, down_pct) if is_wave else "zu ruhig / kein Wellenmodus"

    status_vs_buy = None
    next_target = None
    pl_pct = None
    if buy_price is not None and targets:
        status_vs_buy, next_target, pl_pct = classify_portfolio_position(price, buy_price, targets)

    status_vs_ref = None
    if ref_price is not None and thresholds:
        change_pct = (price - ref_price) / ref_price * 100
        if change_pct >= thresholds["run_up_pct"]:
            status_vs_ref = f"RUN vs Ref (+{change_pct:.1f}%)"
        elif change_pct <= thresholds["dip_pct"]:
            status_vs_ref = f"DIP vs Ref ({change_pct:.1f}%)"
        else:
            status_vs_ref = f"neutral vs Ref ({change_pct:+.1f}%)"

    return {
        "name": name,
        "ticker": ticker,
        "price": price,
        "trend": trend,
        "stage_52w": stage_52w,
        "momentum_20d": momentum_20d,
        "status_vs_buy": status_vs_buy,
        "next_target": next_target,
        "pl_pct": pl_pct,
        "status_vs_ref": status_vs_ref,
        "history": hist,
        "wave": wave,
        "is_wave": is_wave,
        "avg_range_pct": avg_range_pct,
        "n_cross_50": n_cross_50,
    }


# ---------- Entscheidungslogik: Portfolio-Aktionen ----------

def decide_portfolio_action(analysis, total_shares):
    """
    Gibt eine Empfehlung:
    - SELL_25 / SELL_50
    - BUY_25 / BUY_50
    - HOLD
    """
    wave = analysis["wave"] or ""
    trend = analysis["trend"] or ""
    momentum = analysis["momentum_20d"] or ""
    pl_pct = analysis["pl_pct"]
    stage = analysis["stage_52w"] or ""

    # Default
    action = "HOLD"
    reason = "Keine klaren Signale"

    if total_shares <= 0 or analysis["price"] is None or pl_pct is None:
        return action, "Keine Daten / keine Stücke"

    is_take_profit = wave.startswith("📈")
    is_reentry = wave.startswith("📉")
    is_run = "RUN" in momentum
    is_dip = "DIP" in momentum
    is_crash = "Crash-Zone" in stage
    is_correction = "starke Korrektur" in stage

    # 1) Take-Profit-Zone: Teilverkauf
    if is_take_profit and pl_pct > 20:
        if pl_pct > 80 or is_run:
            action = "SELL_50"
            reason = "Take-Profit-Zone + starker Gewinn / RUN"
        else:
            action = "SELL_25"
            reason = "Take-Profit-Zone + solider Gewinn"
        return action, reason

    # 2) Re-Entry-Zone: Nachkauf
    if is_reentry:
        if is_crash and trend != "🟥 Abwärtstrend":
            action = "BUY_50"
            reason = "Re-Entry in Crash-Zone mit stabilem/neutralem Trend"
        elif is_correction and (is_dip or trend == "🟩 Aufwärtstrend"):
            action = "BUY_25"
            reason = "Re-Entry nach starker Korrektur in Dip/Trend"
        else:
            action = "BUY_25"
            reason = "Re-Entry-Zone"
        return action, reason

    # 3) Starker RUN ohne Welle: eher halten oder kleinen Teilverkauf
    if is_run and pl_pct > 40:
        action = "SELL_25"
        reason = "Starker RUN + hoher Gewinn, leicht trimmen"
        return action, reason

    # 4) Großer Verlust + Crash-Zone: eher Nachkauf, wenn Trend nicht tiefrot
    if pl_pct < -30 and (is_crash or is_correction) and trend != "🟥 Abwärtstrend":
        action = "BUY_25"
        reason = "Großer Buchverlust in Crash/Korrektur, aber Trend nicht tiefrot"
        return action, reason

    # 5) Sonst: halten
    return action, reason


# ---------- Entscheidungslogik: Monatskauf-Empfehlung ----------

CORE_BONUS = {
    "BBAI": 15,
    "SOUN": 12,
    "SYM": 10,
    "TSLA": 8,
    "SMCI": 8,
    "RXRX": 6,
    "ABCL": 6,
    "LMND": 5,
    "HIVE": 5,
    "MSTR": 4,
}


def score_watchlist_candidate(analysis):
    """Berechnet einen Score, wie attraktiv ein Kauf aktuell ist."""
    score = 0
    ticker = analysis["ticker"]
    wave = analysis["wave"] or ""
    trend = analysis["trend"] or ""
    momentum = analysis["momentum_20d"] or ""
    stage = analysis["stage_52w"] or ""
    status_vs_ref = analysis["status_vs_ref"] or ""

    # Wellen-Signale
    if wave.startswith("📉"):
        score += 30  # Re-Entry-Zone
    if wave.startswith("📈"):
        score -= 30  # oben, eher nicht kaufen

    # Momentum
    if "DIP" in momentum or "DIP" in status_vs_ref:
        score += 20
    if "RUN" in momentum or "RUN" in status_vs_ref:
        score -= 25

    # Trend
    if trend.startswith("🟩"):
        score += 10
    if trend.startswith("🟥"):
        score -= 10

    # 52-Wochen-Status
    if "Crash-Zone" in stage:
        score += 20
    elif "starke Korrektur" in stage:
        score += 10
    elif "nahe am Hoch" in stage:
        score -= 10

    # Core-/Story-Bonus
    score += CORE_BONUS.get(ticker.upper(), 0)

    return score


def get_monthly_buy_recommendations(cfg, thresholds):
    """Gibt eine sortierte Liste von Kaufkandidaten (Score, Analyse) zurück."""
    recs = []
    for w in cfg.get("watchlist", []):
        analysis = analyze_ticker(
            name=w["name"],
            ticker=w["ticker"],
            ref_price=w.get("reference_price"),
            targets=w.get("targets", []),
            thresholds=thresholds,
        )
        score = score_watchlist_candidate(analysis)
        recs.append((score, analysis))
    recs.sort(key=lambda x: x[0], reverse=True)
    return recs


# ---------- Streamlit UI ----------

def main():
    st.set_page_config(
        page_title="AGI Trading Dashboard",
        layout="centered",          # besser für Handy
        initial_sidebar_state="collapsed"
    )

    # Leichtes CSS-Tuning für Mobile
    st.markdown("""
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* Etwas weniger Rand auf kleinen Screens */
        .block-container {
            padding-top: 0.5rem;
            padding-bottom: 0.5rem;
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }

        /* Tabellen-Schrift minimal kleiner */
        .stDataFrame table {
            font-size: 0.8rem;
        }

        /* Überschrift-Abstände etwas kleiner */
        h1, h2, h3 {
            margin-bottom: 0.4rem;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("🤖 AGI & AI Trading Dashboard")

    cfg = load_config()
    thresholds = cfg.get("thresholds", {"run_up_pct": 30, "dip_pct": -30})

    tab_portfolio, tab_watchlist, tab_actions, tab_trades = st.tabs(
        ["📊 Portfolio", "📈 Watchlist", "⚙️ Aktionen", "📝 Trade eintragen"]
    )

    # --- TAB: Portfolio ---
    with tab_portfolio:
        st.subheader("Dein aktuelles Portfolio")

        portfolio = cfg.get("portfolio", [])
        if not portfolio:
            st.info("Noch keine Positionen im Portfolio. Trage im Tab 'Trade eintragen' deinen ersten Kauf ein.")
        else:
            rows = []
            analyses_portfolio = {}
            gesamt_wert = 0.0
            gesamt_einsatz = 0.0

            for pos in portfolio:
                trades = pos.get("trades", [])
                total_shares, avg_price = summarize_trades(trades)

                analysis = analyze_ticker(
                    name=pos["name"],
                    ticker=pos["ticker"],
                    buy_price=avg_price,
                    targets=pos.get("targets", []),
                    thresholds=thresholds,
                )
                analyses_portfolio[pos["ticker"].upper()] = (analysis, total_shares)

                kurs = analysis["price"] or 0.0
                wert = (total_shares or 0) * kurs
                einsatz = (total_shares or 0) * (avg_price or 0)

                gesamt_wert += wert
                gesamt_einsatz += einsatz

                rows.append({
                    "Name": analysis["name"],
                    "Ticker": analysis["ticker"],
                    "Stücke": total_shares,
                    "P/L %": round(analysis["pl_pct"], 1) if analysis["pl_pct"] is not None else None,
                    "Trend": analysis["trend"],
                    "Wave": "✅" if analysis["is_wave"] else "❌",
                    "Signal": analysis["wave"],
                })

            # Kennzahlenkarten oben
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "Gesamtwert Portfolio",
                    f"{gesamt_wert:,.0f} {cfg.get('currency','EUR')}"
                )
            with col2:
                if gesamt_einsatz > 0:
                    pl_gesamt = (gesamt_wert - gesamt_einsatz) / gesamt_einsatz * 100
                    st.metric("Gesamt P/L %", f"{pl_gesamt:+.1f} %")
                else:
                    st.metric("Gesamt P/L %", "n/a")

            st.markdown("### Positionen (kompakt)")
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                height=260   # damit es auf dem Handy nicht zu lang wird
            )

            st.session_state["analyses_portfolio"] = analyses_portfolio

            # Einfacher Chart-Auswahl unten drunter
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
                hist = sel_analysis["history"]
                st.line_chart(hist["Close"])

    # --- TAB: Watchlist ---
    with tab_watchlist:
        st.subheader("Watchlist – mögliche nächste Käufe / Vorziehen / Dips")

        watchlist = cfg.get("watchlist", [])
        if not watchlist:
            st.info("Noch keine Watchlist angelegt.")
        else:
            rows = []
            analyses_watchlist = {}
            for w in watchlist:
                analysis = analyze_ticker(
                    name=w["name"],
                    ticker=w["ticker"],
                    ref_price=w.get("reference_price"),
                    targets=w.get("targets", []),
                    thresholds=thresholds,
                )
                analyses_watchlist[w["ticker"].upper()] = analysis
                rows.append({
                    "Name": analysis["name"],
                    "Ticker": analysis["ticker"],
                    "Kurs": round(analysis["price"], 2) if analysis["price"] else None,
                    "Trend": analysis["trend"],
                    "Momentum 20d": analysis["momentum_20d"],
                    "Status vs Ref": analysis["status_vs_ref"],
                    "52W-Stage": analysis["stage_52w"],
                    "Wellen-Aktie?": "✅" if analysis["is_wave"] else "❌",
                    "Ø Tagesrange %": round(analysis["avg_range_pct"], 1) if analysis["avg_range_pct"] else None,
                    "Wave-Signal": analysis["wave"],
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            st.session_state["analyses_watchlist"] = analyses_watchlist

    # --- TAB: Aktionen (Teilverkauf / Nachkauf / Monatskauf) ---
    with tab_actions:
        st.subheader("Aktionen für bestehende Positionen & Monatskauf-Empfehlung")

        analyses_portfolio = st.session_state.get("analyses_portfolio", {})
        if not analyses_portfolio:
            st.info("Keine Portfolio-Analysen verfügbar. Bitte zuerst im Portfolio-Tab aktualisieren.")
        else:
            action_rows = []
            for ticker, (analysis, total_shares) in analyses_portfolio.items():
                action, reason = decide_portfolio_action(analysis, total_shares)
                action_rows.append({
                    "Name": analysis["name"],
                    "Ticker": ticker,
                    "Stücke": total_shares,
                    "P/L %": round(analysis["pl_pct"], 1) if analysis["pl_pct"] is not None else None,
                    "Trend": analysis["trend"],
                    "Wave-Signal": analysis["wave"],
                    "Aktion": action,
                    "Begründung": reason,
                })
            st.markdown("### 🔁 Empfehlungen für Teilverkäufe / Teilnachkäufe")
            st.dataframe(pd.DataFrame(action_rows), use_container_width=True)

        st.markdown("---")
        st.markdown("### 📆 Monatskauf – welche Aktie als Nächstes kaufen?")

        buy_recs = get_monthly_buy_recommendations(cfg, thresholds)
        if not buy_recs:
            st.info("Keine Watchlist-Kandidaten vorhanden.")
        else:
            top_rows = []
            for score, analysis in buy_recs[:10]:
                top_rows.append({
                    "Name": analysis["name"],
                    "Ticker": analysis["ticker"],
                    "Score": score,
                    "Kurs": round(analysis["price"], 2) if analysis["price"] else None,
                    "Trend": analysis["trend"],
                    "Momentum 20d": analysis["momentum_20d"],
                    "Status vs Ref": analysis["status_vs_ref"],
                    "Wave-Signal": analysis["wave"],
                    "52W-Stage": analysis["stage_52w"],
                })
            st.dataframe(pd.DataFrame(top_rows), use_container_width=True)
            best = top_rows[0]
            st.success(
                f"🎯 Empfehlung für den nächsten Monatskauf: **{best['Name']} ({best['Ticker']})** "
                f"mit Score **{best['Score']}**"
            )

    # --- TAB: Trade eintragen ---
    with tab_trades:
        st.subheader("Neuen Trade eintragen")

        with st.form("trade_form"):
            ticker = st.text_input("Ticker (z.B. BBAI)").upper().strip()
            name = st.text_input("Name (z.B. BigBear.ai)")
            shares = st.number_input("Anzahl Aktien (+ für Kauf, - für Verkauf)", step=1.0, value=0.0)
            price = st.number_input("Preis pro Aktie", step=0.01, value=0.0)
            date_str = st.text_input("Datum (YYYY-MM-DD, leer = heute)", value="")
            targets_str = st.text_input(
                "Zielkurse (nur beim ersten Mal, Komma-getrennt, z.B. 12,20,35,60,100)"
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
                        st.stop()

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

                trade = {"date": date_str, "shares": shares, "price": price}
                pos.setdefault("trades", []).append(trade)
                save_config(cfg)
                st.success(f"Trade gespeichert: {shares} x {ticker} @ {price} am {date_str}")


if __name__ == "__main__":
    main()