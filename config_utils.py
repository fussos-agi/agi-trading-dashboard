import json
from pathlib import Path

CONFIG_PATH = Path("config.json")
AI_UNIVERSE_PATH = Path("ai_universe.json")


def load_config():
    """Konfiguration laden oder Defaults erzeugen."""
    if not CONFIG_PATH.exists():
        return {
            "currency": "EUR",
            "portfolio": [],
            "watchlist": [],
            "thresholds": {"run_up_pct": 30, "dip_pct": -30},
            "journal": [],
            "ladder_progress": {},  # neu: Fortschritt pro Aktie für Ladder-Stufen
        }

    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    # Defaults sicherstellen, falls ältere config.json geladen wird
    cfg.setdefault("currency", "EUR")
    cfg.setdefault("portfolio", [])
    cfg.setdefault("watchlist", [])
    cfg.setdefault("thresholds", {"run_up_pct": 30, "dip_pct": -30})
    cfg.setdefault("journal", [])
    cfg.setdefault("ladder_progress", {})

    return cfg


def save_config(cfg):
    """Konfiguration speichern."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_ai_universe():
    """Komplette AI/AGI-Liste aus Datei laden (für AI Universe Radar)."""
    if not AI_UNIVERSE_PATH.exists():
        return {"ai_universe": []}
    with open(AI_UNIVERSE_PATH, "r") as f:
        return json.load(f)


def find_portfolio_entry(cfg, ticker):
    """Eintrag im Portfolio nach Ticker finden (Case-insensitive)."""
    for pos in cfg.get("portfolio", []):
        if pos.get("ticker", "").upper() == ticker.upper():
            return pos
    return None


# --------------------------------------------------------------
# PORTFOLIO AUS DEM JOURNAL NEU AUFBAUEN (MASTER-FUNKTION)
# --------------------------------------------------------------


def rebuild_portfolio_from_journal(cfg):
    """
    Baut das gesamte Portfolio NUR basierend auf dem Journal neu.

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
        ticker_raw = j.get("ticker") or ""
        ticker = ticker_raw.upper()
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

    # Final ins Config-Objekt schreiben
    cfg["portfolio"] = list(positions.values())