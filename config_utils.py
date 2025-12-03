import json
from pathlib import Path

CONFIG_PATH = Path("config.json")
AI_UNIVERSE_PATH = Path("ai_universe.json")


def load_config():
    if not CONFIG_PATH.exists():
        return {
            "currency": "EUR",
            "portfolio": [],
            "watchlist": [],
            "thresholds": {"run_up_pct": 30, "dip_pct": -30},
            "journal": [],
        }
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    cfg.setdefault("currency", "EUR")
    cfg.setdefault("portfolio", [])
    cfg.setdefault("watchlist", [])
    cfg.setdefault("thresholds", {"run_up_pct": 30, "dip_pct": -30})
    cfg.setdefault("journal", [])
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_ai_universe():
    """Komplette AI/AGI-Liste aus Datei laden (für AI Universe Radar)."""
    if not AI_UNIVERSE_PATH.exists():
        return {"ai_universe": []}
    with open(AI_UNIVERSE_PATH, "r") as f:
        return json.load(f)


def find_portfolio_entry(cfg, ticker):
    for pos in cfg.get("portfolio", []):
        if pos.get("ticker", "").upper() == ticker.upper():
            return pos
    return None