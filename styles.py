STYLES = """
<style>
:root {
    --bg-main: #2b1305;         /* sehr dunkles Burnt Orange */
    --bg-card: #3b1a07;         /* etwas helleres Burnt Orange für Cards */
    --accent: #FFCE1B;          /* Mustard Yellow als Hauptakzent */
    --accent-soft: #BE5103;     /* Burnt Orange als softer Akzent */
    --accent-teal: #069494;     /* Teal für Kontrast-Details */
    --text-main: #FFEFD2;       /* warmer, heller Text */
    --text-muted: #F5D59A;      /* etwas dunkler, gedämpfter Text */
    --profit: #22c55e;          /* Gewinn (Grün) */
    --loss: #ff4d4f;            /* Verlust (Rot) */
}

/* Hintergrund & Standard-Textfarbe – klare Flat-Farbe */
html, body, .stApp {
    background-color: #069494 !important;   /* neuer Teal-Hintergrund */
    color: var(--text-main) !important;
}

/* ALLE Überschriften hell */
h1, h2, h3, h4, h5, h6 {
    color: var(--text-main) !important;
}

/* Standard-Text hell */
p, span, li, label, .stMarkdown, .stMarkdown p {
    color: var(--text-main) !important;
}

/* Sekundärer Text */
.small-text, .muted, .stCaption, .stMetric label {
    color: var(--text-muted) !important;
}

/* Tabs oben (Streamlit st.tabs) */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.4rem;
    margin-top: 0.9rem;
    margin-bottom: 0.8rem;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 999px;
    padding: 0.2rem 0.9rem;
    color: var(--text-muted);
    border: 1px solid rgba(255,255,255,0.07);
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: #BE5103 !important;      /* Burnt Orange */
    color: #fff !important;              /* gut lesbare Schrift */
    border-color: #BE5103 !important;
    font-weight: 600;
}
.stTabs [data-baseweb="tab"]::after {
    display: none !important;
    border-bottom: none !important;
}

/* KPI-Karten (Verkäufe / Käufe / HOLD) – flache Farbe */
.metric-card {
    background: var(--accent-soft);
    border-radius: 18px;
    padding: 0.8rem 1rem;
    box-shadow: 0 12px 24px rgba(0,0,0,0.55);
    border: 1px solid rgba(0,0,0,0.6);
}

/* Globale Depot-Signalkarten – flache Teal-Farbe */
.glass-card {
    background: var(--accent-teal);
    border-radius: 22px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 18px 36px rgba(0,0,0,0.7);
    border: 1px solid rgba(0,0,0,0.65);
}

/* einfache Sektionstitel */
.section-title {
    font-size: 1.0rem;
    font-weight: 600;
    margin: 0.4rem 0 0.2rem;
}

/* kleine Badges (z.B. Reversal, Breakout etc.) */
.badge-pill {
    display: inline-block;
    padding: 0.1rem 0.55rem;
    border-radius: 999px;
    font-size: 0.68rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* Badges jetzt ohne Alpha-Overlays, nur klare Farben */
.badge-profit {
    background: #166534;               /* dunkles Grün */
    border: 1px solid #16a34a;
    color: #dcfce7;
}
.badge-loss {
    background: #7f1d1d;               /* dunkles Rot */
    border: 1px solid #ef4444;
    color: #fee2e2;
}
.badge-neutral {
    background: #334155;               /* Slate */
    border: 1px solid #64748b;
    color: #e2e8f0;
}

/* Tabellen-Text hell */
.stDataFrame, .stDataFrame table, .stDataFrame tbody td, .stDataFrame thead th {
    color: var(--text-main) !important;
}

/* Tabellen-Hintergründe – klare Farben */
.stDataFrame tbody td {
    background: var(--bg-card) !important;
}
.stDataFrame thead th {
    background: var(--accent-soft) !important;
}

/* Überschriften-Abstände etwas knapper */
h1, h2, h3 {
    margin-bottom: 0.4rem;
}

/* Stock-Cards im Retro-Look – flache Card-Farbe */
.stock-card {
    background: var(--bg-card);
    border-radius: 16px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.8rem;
    border: 1px solid rgba(0,0,0,0.75);
    box-shadow: 0 12px 28px rgba(0,0,0,0.7);
}
.stock-card-header {
    font-size: 0.95rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
}
.stock-card-sub {
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
}
.stock-card-row {
    font-size: 0.8rem;
    margin-bottom: 0.14rem;
}

/* SVG-Icons, die du über icon_html() einbindest */
.agi-icon {
    vertical-align: middle;
    margin-right: 0.35rem;
}

/* optional: runder Hintergrund für Icons (kannst du lassen oder rausnehmen) */
.agi-icon-badge {
    padding: 4px;
    border-radius: 999px;
    background: #1a0b04;
}

/* Lade-Hinweis Box im Retro-Farbschema */
.loading-box {
    background: var(--accent-soft);          /* Burnt Orange #BE5103 */
    color: var(--text-main);
    border-radius: 16px;
    padding: 0.75rem 1.1rem;
    margin: 0.9rem 0 0.6rem;
    border: 1px solid rgba(0,0,0,0.65);
    box-shadow: 0 12px 26px rgba(0,0,0,0.65);
}

.loading-box-title {
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.82rem;
    margin-bottom: 0.25rem;
}

.loading-box-sub {
    font-size: 0.8rem;
    opacity: 0.95;
}
</style>
"""
