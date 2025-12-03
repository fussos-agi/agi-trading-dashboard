from pathlib import Path
import base64
from functools import lru_cache

# Ordner mit deinen SVG-Icons (z.B. src/account_balance_....svg etc.)
ICON_DIR = Path(__file__).parent / "src"

# Retro-Sunset-Palette
COLOR_MAP = {
    "burnt": "#BE5103",     # burnt orange
    "mustard": "#FFCE1B",   # mustard yellow
    "teal": "#069494",      # teal
    "rust": "#B7410E",      # dark orange/red
    "white": "#FFFFFF",
}


@lru_cache(maxsize=None)
def _svg_data_uri(filename: str, color_variant: str | None = None) -> str:
    """
    SVG laden, optional die Standardfarbe (#1F1F1F) durch eine Retro-Farbe ersetzen
    und als data:-URI zurückgeben.
    """
    path = ICON_DIR / filename
    svg = path.read_text(encoding="utf-8")

    if color_variant:
        color = COLOR_MAP.get(color_variant)
        if color:
            # Material-Icons nutzen meist #1F1F1F als Füllfarbe
            svg = svg.replace("#1F1F1F", color)

    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


def icon_html(
    filename: str,
    size: int = 22,
    variant: str = "mustard",
    extra_class: str = "",
) -> str:
    """
    Icon als <img>-HTML zurückgeben, ready für st.markdown(..., unsafe_allow_html=True).
    """
    src = _svg_data_uri(filename, color_variant=variant)
    cls = "agi-icon"
    if extra_class:
        cls += f" {extra_class}"
    return (
        f'<img src="{src}" width="{size}" height="{size}" '
        f'class="{cls}" alt=""/>'
    )
