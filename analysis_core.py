import yfinance as yf
import pandas as pd
from datetime import datetime

# -------------------------------------------------------------------
# Caches
# -------------------------------------------------------------------

FUND_CACHE = {}
EARNINGS_CACHE = {}
MACRO_CACHE = None


# -------------------------------------------------------------------
# Kurs- & Analyse-Helfer
# -------------------------------------------------------------------

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
    """
    Wellenlogik mit dynamischen Schwellwerten.
    """
    if price is None or len(closes) < window or up_pct is None or down_pct is None:
        return "kein Wellenmodus", None, None, None, None

    recent = closes[-window:]
    swing_low = float(recent.min())
    swing_high = float(recent.max())

    if swing_low == 0 or swing_high == 0:
        return "kein Wellenmodus", None, None, None, None

    from_low_pct = (price - swing_low) / swing_low * 100
    from_high_pct = (price - swing_high) / swing_high * 100

    tp_level = swing_low * (1 + up_pct / 100.0) if up_pct is not None else None
    reentry_level = swing_high * (1 + down_pct / 100.0) if down_pct is not None else None

    if from_low_pct >= up_pct and from_high_pct > -10:
        label = f"📈 Take-Profit-Zone (+{from_low_pct:.1f}% über Tief, {from_high_pct:.1f}% unter Hoch)"
    elif from_high_pct <= down_pct and from_low_pct < 15:
        label = f"📉 Re-Entry-Zone ({from_high_pct:.1f}% unter Hoch, +{from_low_pct:.1f}% über Tief)"
    else:
        label = f"neutral (vom Tief +{from_low_pct:.1f}%, vom Hoch {from_high_pct:.1f}%)"

    return label, swing_low, swing_high, tp_level, reentry_level


def compute_ladder_targets(buy_price, tp_level_est, reentry_level_est):
    """
    Ladder 1–4 werden so gesetzt, dass:
    - L1 >= max(EK, ReEntry * 1.05)
    - L4 <= TP * 0.98
    Falls Wave-Infos fehlen → Fallback 30/50/70/100% über EK.
    """
    if buy_price is None or buy_price <= 0:
        return []

    # Wenn keine Wave-Infos vorhanden sind → einfacher Prozent-Fallback
    if tp_level_est is None and reentry_level_est is None:
        mults = [1.3, 1.5, 1.7, 2.0]
        return [round(buy_price * m, 2) for m in mults]

    start = buy_price
    if reentry_level_est:
        start = max(start, reentry_level_est * 1.05)  # mind. 5% über Re-Entry

    end = None
    if tp_level_est and tp_level_est > 0:
        end = tp_level_est * 0.98  # knapp unter Top-Level

    # Wenn irgendwas schief geht oder Bereich zu klein ist → Fallback
    if end is None or end <= start * 1.05:
        mults = [1.3, 1.5, 1.7, 2.0]
        return [round(buy_price * m, 2) for m in mults]

    step = (end - start) / 4.0
    return [round(start + step * i, 2) for i in range(1, 5)]


# -------------------------------------------------------------------
# Fundamentals & Events
# -------------------------------------------------------------------

def fetch_fundamentals(ticker):
    """
    Holt grobe Fundamentals (Jahreszahlen) und berechnet:
    - rev_growth_1y (%)
    - net_margin (%)
    - debt_to_assets (Quote 0–1+)
    """
    if ticker in FUND_CACHE:
        return FUND_CACHE[ticker]

    result = {
        "rev_growth_1y": None,
        "net_margin": None,
        "debt_to_assets": None,
    }

    try:
        t = yf.Ticker(ticker)
        fin = t.financials
        if fin is not None and not fin.empty:
            if "Total Revenue" in fin.index:
                rev = fin.loc["Total Revenue"]
            else:
                rev = None
            if "Net Income" in fin.index:
                ni = fin.loc["Net Income"]
            else:
                ni = None

            if rev is not None and len(rev) >= 2:
                last = float(rev.iloc[0])
                prev = float(rev.iloc[1])
                if prev != 0:
                    result["rev_growth_1y"] = (last - prev) / prev * 100.0

            if rev is not None and ni is not None and len(rev) >= 1 and len(ni) >= 1:
                r0 = float(rev.iloc[0])
                n0 = float(ni.iloc[0])
                if r0 != 0:
                    result["net_margin"] = n0 / r0 * 100.0

        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            if "Total Liab" in bs.index and "Total Assets" in bs.index:
                liab = float(bs.loc["Total Liab"].iloc[0])
                assets = float(bs.loc["Total Assets"].iloc[0])
                if assets != 0:
                    result["debt_to_assets"] = liab / assets
    except Exception:
        # bewusst ruhig: wir wollen nur "None" zurück
        pass

    FUND_CACHE[ticker] = result
    return result


def fetch_earnings_info(ticker):
    """
    Liefert Tage bis zum nächsten Earnings-Termin (falls verfügbar).
    days_to_earnings:
      >0 = in Zukunft
      <0 = liegt in der Vergangenheit
    """
    if ticker in EARNINGS_CACHE:
        return EARNINGS_CACHE[ticker]

    result = {"days_to_earnings": None}

    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            edate = cal.loc["Earnings Date"].iloc[0]
            if isinstance(edate, (pd.Timestamp, datetime)):
                today = datetime.utcnow().date()
                d = (edate.date() - today).days
                result["days_to_earnings"] = int(d)
    except Exception:
        pass

    EARNINGS_CACHE[ticker] = result
    return result


# -------------------------------------------------------------------
# Makro-Kontext
# -------------------------------------------------------------------

def compute_macro_context():
    """
    Grober Makro-Kontext auf Basis des S&P 500 (^GSPC).
    Liefert:
      - dd_spy   : Drawdown vs. 52W-High (%)
      - chg20_spy: 20-Tage-Performance (%)
      - regime   : 'bull', 'normal', 'correction', 'crash', 'unknown'
    """
    global MACRO_CACHE
    if MACRO_CACHE is not None:
        return MACRO_CACHE

    ctx = {"dd_spy": None, "chg20_spy": None, "regime": "unknown"}

    try:
        data = yf.download("^GSPC", period="1y", interval="1d", progress=False)
        closes = data["Close"].dropna()
        if closes.empty:
            MACRO_CACHE = ctx
            return ctx

        price = float(closes.iloc[-1])
        high_52w = float(closes.max())
        dd = (price - high_52w) / high_52w * 100.0 if high_52w else None

        if len(closes) > 20:
            p20 = float(closes.iloc[-21])
            chg20 = (price - p20) / p20 * 100.0
        else:
            chg20 = None

        regime = "normal"
        if dd is not None:
            if dd <= -30:
                regime = "crash"
            elif dd <= -20:
                regime = "correction"
            elif dd >= -5:
                regime = "bull"

        ctx = {"dd_spy": dd, "chg20_spy": chg20, "regime": regime}
    except Exception:
        ctx = {"dd_spy": None, "chg20_spy": None, "regime": "unknown"}

    MACRO_CACHE = ctx
    return ctx


# -------------------------------------------------------------------
# Analyse eines einzelnen Tickes
# -------------------------------------------------------------------

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
            "wave_swing_low": None,
            "wave_swing_high": None,
            "wave_tp_level": None,
            "wave_reentry_level": None,
            "targets": targets or [],
            "targets_reached": 0,
            "drawdown_52w": None,
            "change_20d_pct": None,
            "change_3d_pct": None,
            "avg_volume_20d": None,
            "is_viable": True,
            "quality_note": None,
            "fundamentals": {"rev_growth_1y": None, "net_margin": None, "debt_to_assets": None},
            "days_to_earnings": None,
        }

    closes = hist["Close"]
    price = float(closes.iloc[-1])

    ma50 = moving_average(closes, 50)
    ma200 = moving_average(closes, 200)
    high_52w = float(closes.max())
    low_52w = float(closes.min())

    # --- 20-Tage-Preis ---
    if len(closes) > 20:
        price_20d_ago = float(closes.iloc[-21])
    else:
        price_20d_ago = None

    # --- 3-Tage-Preis (für Reversal) ---
    if len(closes) > 3:
        price_3d_ago = float(closes.iloc[-4])
    else:
        price_3d_ago = None

    # Rohwerte für weiches Scoring
    drawdown_52w = None
    if high_52w:
        drawdown_52w = (price - high_52w) / high_52w * 100  # negativ = unter Hoch

    change_20d_pct = None
    if price_20d_ago:
        change_20d_pct = (price - price_20d_ago) / price_20d_ago * 100

    change_3d_pct = None
    if price_3d_ago:
        change_3d_pct = (price - price_3d_ago) / price_3d_ago * 100

    # Liquidität & „Zombie“-Check
    avg_volume_20d = None
    if "Volume" in hist.columns:
        avg_volume_20d = float(hist["Volume"].tail(20).mean())

    is_zombie = False
    zombie_reasons = []

    if price is not None:
        if price < 0.5:
            is_zombie = True
            zombie_reasons.append("Kurs < 0,50")
        if high_52w < 1.0:
            is_zombie = True
            zombie_reasons.append("52W-High < 1,00")

    if avg_volume_20d is not None and avg_volume_20d < 100_000:
        is_zombie = True
        zombie_reasons.append("∅ Volumen 20d < 100k")

    quality_note = "; ".join(zombie_reasons) if is_zombie else None

    trend = classify_trend(price, ma50, ma200)
    stage_52w = classify_52w_stage(price, high_52w, low_52w)
    momentum_20d = classify_momentum(price, price_20d_ago, thresholds) if thresholds else "n/a"

    is_wave, avg_range_pct, n_cross_50 = detect_wave_stock(hist)
    up_pct, down_pct = wave_params_from_vol(avg_range_pct)

    if is_wave:
        wave_label, swing_low, swing_high, tp_level, reentry_level = wave_signal(
            price, closes, up_pct, down_pct
        )
    else:
        wave_label = "zu ruhig / kein Wellenmodus"
        swing_low = swing_high = tp_level = reentry_level = None

    # ---- Ladder-Ziele berechnen ----
    ladder_targets = targets or []
    if buy_price is not None and not ladder_targets:
        ladder_targets = compute_ladder_targets(buy_price, tp_level, reentry_level)

    status_vs_buy = None
    next_target = None
    pl_pct = None
    if buy_price is not None and ladder_targets:
        status_vs_buy, next_target, pl_pct = classify_portfolio_position(price, buy_price, ladder_targets)

    status_vs_ref = None
    if ref_price is not None and thresholds:
        change_pct_ref = (price - ref_price) / ref_price * 100
        if change_pct_ref >= thresholds["run_up_pct"]:
            status_vs_ref = f"RUN vs Ref (+{change_pct_ref:.1f}%)"
        elif change_pct_ref <= thresholds["dip_pct"]:
            status_vs_ref = f"DIP vs Ref ({change_pct_ref:.1f}%)"
        else:
            status_vs_ref = f"neutral vs Ref ({change_pct_ref:+.1f}%)"

    targets_reached = 0
    if ladder_targets and price is not None:
        targets_reached = sum(1 for t in ladder_targets if price >= t)

    fundamentals = fetch_fundamentals(ticker)
    earnings_info = fetch_earnings_info(ticker)
    days_to_earnings = earnings_info.get("days_to_earnings")

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
        "wave": wave_label,
        "is_wave": is_wave,
        "avg_range_pct": avg_range_pct,
        "n_cross_50": n_cross_50,
        "wave_swing_low": swing_low,
        "wave_swing_high": swing_high,
        "wave_tp_level": tp_level,
        "wave_reentry_level": reentry_level,
        "targets": ladder_targets,
        "targets_reached": targets_reached,
        "drawdown_52w": drawdown_52w,
        "change_20d_pct": change_20d_pct,
        "change_3d_pct": change_3d_pct,
        "avg_volume_20d": avg_volume_20d,
        "is_viable": not is_zombie,
        "quality_note": quality_note,
        "fundamentals": fundamentals,
        "days_to_earnings": days_to_earnings,
    }


# -------------------------------------------------------------------
# Entscheidungslogik: Portfolio-Aktionen
# -------------------------------------------------------------------

def decide_portfolio_action(analysis, total_shares):
    """
    Gibt eine Empfehlung:
    - SELL_20  : 20% der Position verkaufen (Leiter)
    - SELL_ALL : alles verkaufen (Kapitalschutz)
    - BUY_20   : 20% nachkaufen
    - BUY_40   : 40% nachkaufen
    - HOLD     : nichts tun
    """
    wave = analysis["wave"] or ""
    trend = analysis["trend"] or ""
    momentum = analysis["momentum_20d"] or ""
    pl_pct = analysis["pl_pct"]
    stage = analysis["stage_52w"] or ""
    price = analysis["price"]
    targets = analysis.get("targets") or []
    targets_reached = analysis.get("targets_reached", 0)

    action = "HOLD"
    reason = "Keine klaren Signale"

    if total_shares <= 0 or price is None or pl_pct is None:
        return action, "Keine Daten / keine Stücke"

    is_take_profit = wave.startswith("📈")
    is_reentry = wave.startswith("📉")
    is_run = "RUN" in momentum
    is_dip = "DIP" in momentum
    is_crash = "Crash-Zone" in stage
    is_correction = "starke Korrektur" in stage
    is_bear = trend.startswith("🟥")
    is_bull = trend.startswith("🟩")

    # Crash-Absicherung
    if pl_pct < -45 and is_bear and (is_crash or is_correction):
        return "SELL_ALL", "Starker Abwärtstrend und >45% im Minus – Kapitalschutz, lieber später neu einsteigen."

    # Leiter-Verkäufe
    if is_take_profit or (is_run and pl_pct > 30):
        if targets and targets_reached < 4 and pl_pct > 20:
            stufe = targets_reached + 1
            action = "SELL_20"
            reason = (
                f"Leiter-Stufe {stufe} erreicht (Kurs über Ziel {stufe}) – "
                "empfohlen: 20% der Position verkaufen, Gewinne sichern."
            )
            return action, reason

        if targets_reached >= 4 and pl_pct > 0:
            return "HOLD", "Alle 4 Gewinnziele erreicht – 20% Restposition laufen lassen, bis ein klares Verkaufssignal kommt."

    # Re-Entry-Zonen
    if is_reentry:
        if is_crash and not is_bear:
            return "BUY_40", "Re-Entry in Crash-Zone mit stabilerem Trend – Chance auf starken Rebound, 40% Nachkauf."
        if (is_correction or is_dip or is_bull):
            return "BUY_20", "Wellen-Re-Entry-Zone nach Korrektur – schrittweise Position aufbauen (20% Nachkauf)."

    # RUN ohne Wellen-Signal
    if is_run and pl_pct > 60 and not is_take_profit:
        return "SELL_20", "Sehr starker RUN + hoher Gewinn – 20% trimmen, um Risiko zu reduzieren."

    # Großer Verlust, aber kein klarer Crash
    if pl_pct < -30 and (is_crash or is_correction) and not is_bear:
        return "BUY_20", "Großer Buchverlust in Crash/Korrektur, aber Trend nicht tiefrot – vorsichtiger 20%-Nachkauf möglich."

    return action, reason


# -------------------------------------------------------------------
# Scores – Short-Term (STS) & Long-Term AGI (LAS)
# -------------------------------------------------------------------

# AGI-Core-Bonus (wird in beiden Scores genutzt, aber unterschiedlich stark)
CORE_BONUS_LAS = {
    "BBAI": 30,
    "SOUN": 25,
    "SMCI": 25,
    "ABCL": 20,
    "RXRX": 20,
    "SYM": 20,
    "TSLA": 15,
}

CORE_BONUS_STS = {
    "BBAI": 8,
    "SOUN": 8,
    "SMCI": 6,
    "ABCL": 6,
    "RXRX": 5,
    "SYM": 5,
    "TSLA": 4,
    "LMND": 3,
    "HIVE": 3,
    "MSTR": 3,
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def score_dual_candidate(analysis, thresholds, macro=None):
    """
    Liefert zwei weiche Scores (0–100):

    STS = Short-Term Score (Trading / schnelle Gewinne)
    LAS = Long-Term AGI Score (billig einsammeln & halten)
    """

    # Illiquide / Zombie-Werte nicht scoren
    if not analysis.get("is_viable", True):
        return 0.0, 0.0

    price = analysis["price"]
    ticker = analysis["ticker"].upper()

    # Wenn kein handelbarer Kurs vorhanden ist -> Score 0 / 0
    if price is None or price <= 0:
        return 0.0, 0.0

    wave = analysis["wave"] or ""
    trend = analysis["trend"] or ""
    dd = analysis.get("drawdown_52w")          # z.B. -45.0 (% unter Hoch)
    change20 = analysis.get("change_20d_pct")  # z.B. -28.0 (% in 20 Tagen)
    avg_range = analysis.get("avg_range_pct")
    tp = analysis.get("wave_tp_level")
    reentry = analysis.get("wave_reentry_level")
    days_to_earn = analysis.get("days_to_earnings")

    fund = analysis.get("fundamentals") or {}
    rev_g = fund.get("rev_growth_1y")
    net_m = fund.get("net_margin")
    dta = fund.get("debt_to_assets")

    run_up = (thresholds or {}).get("run_up_pct", 30)
    dip_th = (thresholds or {}).get("dip_pct", -30)

    # ---------------- STS: kurzfristiger Trading-Score ----------------
    sts = 0.0

    # 1) 52W-Drawdown (weich, max +20)
    if dd is not None:
        if dd >= 0:
            dd_pos = _clamp(dd, 0.0, 20.0)
            sts -= (dd_pos / 20.0) * 5.0
        else:
            dd_clip = _clamp(dd, -70.0, 0.0)
            sts += (abs(dd_clip) / 70.0) * 20.0

    # 2) 20d Momentum (weich, -25 bis +25)
    if change20 is not None:
        if change20 >= 0:
            max_up = run_up * 2.0  # z.B. +60%
            c_clip = _clamp(change20, 0.0, max_up)
            sts -= (c_clip / max_up) * 25.0
        else:
            max_dip = dip_th * 2.0  # z.B. -60%
            c_clip = _clamp(change20, max_dip, 0.0)
            sts += (abs(c_clip) / abs(max_dip)) * 25.0

    # 3) Wave-Signal (kleiner Bonus/Malus)
    if wave.startswith("📉"):
        sts += 10.0
    elif wave.startswith("📈"):
        sts -= 10.0

    # 4) Distanz zu Re-Entry (bis +15)
    if price is not None and reentry:
        dist = (price - reentry) / reentry * 100.0
        if dist <= 0:
            dist_clip = _clamp(dist, -20.0, 0.0)
            sts += (abs(dist_clip) / 20.0) * 15.0
        elif dist <= 5:
            sts += (5.0 - dist) / 5.0 * 5.0

    # 5) Distanz zu TP-Level (bis -20)
    if price is not None and tp:
        dist_tp = (price - tp) / tp * 100.0
        if dist_tp >= -5.0:
            dist_clip = _clamp(dist_tp, -5.0, 15.0)
            penalty = ((dist_clip + 5.0) / 20.0) * 20.0
            sts -= penalty

    # 6) Trend (leicht)
    if trend.startswith("🟩"):
        sts += 5.0
    elif trend.startswith("🟥"):
        sts -= 5.0

    # 7) Volatilität für Trading (Moonshot, max +10)
    if avg_range is not None:
        ar = max(0.0, avg_range - 3.0)
        vol_bonus = _clamp((ar / 7.0) * 10.0, 0.0, 10.0)
        sts += vol_bonus

    # 8) Fundamentals – eher kleiner Effekt für STS
    if rev_g is not None:
        rev_clip = _clamp(rev_g, -40.0, 60.0)
        sts += (rev_clip / 60.0) * 8.0    # grob -5 bis +8
    if net_m is not None:
        nm_clip = _clamp(net_m, -30.0, 30.0)
        sts += (nm_clip / 30.0) * 5.0
    if dta is not None:
        dta_clip = _clamp(dta, 0.0, 1.5)
        sts -= (dta_clip / 1.5) * 6.0     # hohe Verschuldung -> Malus

    # 9) Event-Risiko: Earnings
    if days_to_earn is not None:
        if -2 <= days_to_earn <= 2:
            sts -= 10.0   # direkt um Earnings herum vorsichtig
        elif -7 <= days_to_earn <= 7:
            sts -= 5.0
        elif 7 < days_to_earn <= 21:
            sts -= 2.0

    # 10) AGI-Core-Bonus (kleiner Effekt)
    sts += CORE_BONUS_STS.get(ticker, 0.0)

    # 11) Makro-Kontext
    if macro:
        regime = macro.get("regime", "normal")
        if regime == "crash":
            sts -= 10.0
        elif regime == "correction":
            sts -= 5.0
        elif regime == "bull":
            sts += 3.0

    # ---------------- LAS: langfristiger AGI-Score ----------------
    las = 0.0

    # A) Drawdown (max +30, kleiner Malus über Hoch)
    if dd is not None:
        if dd >= 0:
            dd_pos = _clamp(dd, 0.0, 20.0)
            las -= (dd_pos / 20.0) * 10.0
        else:
            dd_clip = _clamp(dd, -80.0, 0.0)
            las += (abs(dd_clip) / 80.0) * 30.0

    # B) DIP / RUN: für Langfrist weicher
    if change20 is not None:
        if change20 >= 0:
            max_up = run_up * 2.0
            c_clip = _clamp(change20, 0.0, max_up)
            las -= (c_clip / max_up) * 8.0
        else:
            max_dip = dip_th * 2.0
            c_clip = _clamp(change20, max_dip, 0.0)
            las += (abs(c_clip) / abs(max_dip)) * 15.0

    # C) Wave-ReEntry betonen
    if wave.startswith("📉"):
        las += 15.0

    # D) Nähe zu ReEntry (max +10)
    if price is not None and reentry:
        dist = (price - reentry) / reentry * 100.0
        if dist <= 5.0:
            dist_clip = _clamp(dist, -15.0, 5.0)
            las += (5.0 - dist_clip) / 20.0 * 10.0

    # E) Volatilität: leichte Präferenz (Moonshot)
    if avg_range is not None and avg_range >= 4.0:
        las += 5.0

    # F) Fundamentals – stärkerer Effekt
    if rev_g is not None:
        rev_clip = _clamp(rev_g, -40.0, 80.0)
        las += (rev_clip / 80.0) * 15.0
    if net_m is not None:
        nm_clip = _clamp(net_m, -30.0, 30.0)
        las += (nm_clip / 30.0) * 10.0
    if dta is not None:
        dta_clip = _clamp(dta, 0.0, 1.5)
        las -= (dta_clip / 1.5) * 10.0

    # G) Starker AGI-Bonus
    las += CORE_BONUS_LAS.get(ticker, 0.0)

    # H) Makro-Kontext: Crash/Korrektur sind eher gut für Langfrist-Käufe
    if macro:
        regime = macro.get("regime", "normal")
        if regime == "crash":
            las += 5.0
        elif regime == "correction":
            las += 3.0
        elif regime == "bull":
            las -= 2.0  # langfristig eher teuer

    # Scores sauber auf 0–100 begrenzen
    sts = _clamp(sts, 0.0, 100.0)
    las = _clamp(las, 0.0, 100.0)

    return round(sts, 1), round(las, 1)


# Wrapper: alter Name liefert jetzt STS (für bestehenden Code)
def score_watchlist_candidate(analysis, thresholds, macro=None):
    sts, las = score_dual_candidate(analysis, thresholds, macro)
    return sts


# -------------------------------------------------------------------
# Portfolio-Übersicht
# -------------------------------------------------------------------

def build_portfolio_overview(cfg, thresholds):
    """Portfolio-Analysen und Tabellenzeilen berechnen."""
    portfolio = cfg.get("portfolio", [])
    analyses_portfolio = {}
    rows = []
    gesamt_wert = 0.0
    gesamt_einsatz = 0.0

    for pos in portfolio:
        trades = pos.get("trades", [])
        total_shares, avg_price = summarize_trades(trades)

        analysis = analyze_ticker(
            name=pos["name"],
            ticker=pos["ticker"],
            buy_price=avg_price,
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
            "Einstand (EK)": round(avg_price, 2) if avg_price else None,
            "Kurs": round(analysis["price"], 2) if analysis["price"] else None,
            "P/L %": round(analysis["pl_pct"], 1) if analysis["pl_pct"] is not None else None,
            "Trend": analysis["trend"],
            "Wave": "✅" if analysis["is_wave"] else "❌",
            "Signal": analysis["wave"],
        })

    return portfolio, analyses_portfolio, rows, gesamt_wert, gesamt_einsatz