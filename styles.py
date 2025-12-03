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
    --profit: #22c55e;          /* Gewinn (Grün – kann so bleiben) */
    --loss: #ff4d4f;            /* Verlust (Rot) */
}

/* Hintergrund & Standard-Textfarbe – Retro Sunset Gradient */
html, body, .stApp {
    background: radial-gradient(circle at top,
        #B7410E 0%,
        #2b1305 40%,
        #120607 80%
    ) !important;
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

/* Tabs oben */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
}
.stTabs [data-baseweb="tab"] {
    background: rgba(61, 26, 7, 0.95);  /* dunkles Burnt Orange */
    border-radius: 999px;
    padding: 0.2rem 0.9rem;
    color: var(--text-muted);
    border: 1px solid rgba(255,255,255,0.06);
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: var(--accent);          /* Mustard Yellow */
    color: #2b1305;
    border-color: var(--accent-soft);
}

/* KPI-Karten (Verkäufe / Käufe / HOLD) */
.metric-card {
    background: linear-gradient(135deg,
        rgba(190, 81, 3, 0.9),    /* Burnt Orange */
        rgba(183, 65, 14, 0.95)   /* Darker Orange */
    );
    border-radius: 18px;
    padding: 0.8rem 1rem;
    box-shadow: 0 16px 32px rgba(0,0,0,0.65);
    border: 1px solid rgba(255,255,255,0.08);
}

/* GLOBALE Depot-Signalkarten – Teal-Touch */
.glass-card {
    background: linear-gradient(135deg,
        rgba(183, 65, 14, 0.96),
        rgba(6, 148, 148, 0.9)   /* Teal-Mix */
    );
    border-radius: 22px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 18px 40px rgba(0,0,0,0.8);
    border: 1px solid rgba(255,255,255,0.12);
}

/* Titel in der Card ein Hauch heller & größer */
.glass-card h3, .glass-card h4, .glass-card strong {
    color: #fffdf6 !important;
}

/* Ladder-Ziele und kleine Labels */
.glass-card .muted, .glass-card .small-text {
    color: var(--text-muted) !important;
}

/* Badges (P/L, Trend etc.) */
.badge {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-profit {
    background: rgba(34, 197, 94, 0.16);
    border: 1px solid rgba(34, 197, 94, 0.75);
    color: #c9ffdd;
}
.badge-trend {
    background: rgba(255, 206, 27, 0.18);        /* Mustard Yellow */
    border: 1px solid rgba(255, 206, 27, 0.8);
    color: #fff2b0;
}

/* Tabellen-Text hell */
.stDataFrame, .stDataFrame table, .stDataFrame tbody td, .stDataFrame thead th {
    color: var(--text-main) !important;
}

/* Tabellen-Hintergründe mit leichtem Teal-Touch */
.stDataFrame tbody td {
    background: rgba(6, 148, 148, 0.16);
}
.stDataFrame thead th {
    background: rgba(190, 81, 3, 0.95);
}

/* Überschriften-Abstände etwas knapper */
h1, h2, h3 {
    margin-bottom: 0.4rem;
}

/* Stock-Cards im Retro-Look */
.stock-card {
    background: linear-gradient(135deg,
        rgba(61, 26, 7, 0.95),
        rgba(6, 148, 148, 0.75)
    );
    border-radius: 16px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.8rem;
    border: 1px solid rgba(255,255,255,0.12);
}
.stock-card-header {
    font-weight: 700;
    margin-bottom: 0.2rem;
}
.stock-card-sub {
    font-size: 0.8rem;
    margin-bottom: 0.4rem;
}
.stock-card-row {
    font-size: 0.85rem;
    margin-bottom: 0.1rem;
}
.badge-pill {
    padding: 0.12rem 0.5rem;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.35);
    font-size: 0.75rem;
}
.badge-loss {
    background: rgba(255, 77, 79, 0.18);
    border-color: rgba(255, 77, 79, 0.8);
    color: #ffd0d1;
}
.badge-neutral {
    background: rgba(148, 163, 184, 0.25);
    border-color: rgba(148, 163, 184, 0.8);
    color: #e2e8f0;
}

/* SVG-Icons */
.agi-icon {
    vertical-align: middle;
    margin-right: 0.35rem;
}

/* optional: runder Hintergrund, falls du willst */
.agi-icon-badge {
    padding: 4px;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.18);
}
</style>
"""
