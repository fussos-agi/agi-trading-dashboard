STYLES = """
<style>

/* ----------------------------------------------------------
   Google Fonts Import
-----------------------------------------------------------*/
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Montserrat:wght@500;600;700;800&display=swap');

/* ----------------------------------------------------------
   Farb-Variablen – Retro Sunset
-----------------------------------------------------------*/
:root {
    --burnt-orange: #BE5103;
    --mustard: #FFCE1B;
    --teal: #069494;
    --rust: #B7410E;

    --bg-main: #069494;
    --bg-card: #2b1305;
    --bg-card-soft: #B7410E;

    --text-main: #FFF7E5;
    --text-muted: #F5D59A;

    --profit: #A3FF4A;
    --loss: #FF6B4A;
}

/* ----------------------------------------------------------
   Grundlayout – Primäre Schrift: INTER
-----------------------------------------------------------*/
html, body, .stApp {
    background: var(--bg-main) !important;
    color: var(--text-main) !important;

    font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, sans-serif !important;
}

main.block-container {
    padding-top: 0.8rem;
    padding-bottom: 2.5rem;
    max-width: 1200px;
}

.stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li {
    color: var(--text-main) !important;
    font-family: "Inter", sans-serif !important;
}

/* ----------------------------------------------------------
   Überschriften – Sekundäre Schrift: MONTSERRAT
-----------------------------------------------------------*/
h1, h2, h3, h4 {
    font-family: "Montserrat", sans-serif !important;
    color: var(--text-main);
    letter-spacing: 0.03em;
    font-weight: 600;
}

hr {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.09);
    margin: 1.2rem 0;
}

/* ----------------------------------------------------------
   Tabs
-----------------------------------------------------------*/
.stTabs [data-baseweb="tab-list"] {
    gap: 0.4rem;
    margin-top: 0.9rem;
    margin-bottom: 0.8rem;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 999px;
    padding: 0.25rem 0.95rem;

    font-family: "Inter", sans-serif !important;

    color: var(--text-muted);
    border: 1px solid rgba(255,255,255,0.12);
    font-size: 0.9rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.stTabs [data-baseweb="tab"]:hover {
    border-color: rgba(255,255,255,0.35);
}

.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: var(--burnt-orange) !important;
    color: #fff !important;
    border-color: var(--burnt-orange) !important;
    font-weight: 600;
}

/* ----------------------------------------------------------
   Einheitliche Navigation / Tabs – Gleich breite Buttons
-----------------------------------------------------------*/

.stTabs [data-baseweb="tab-list"] {
    justify-content: center !important;
    width: 100%;
    max-width: 900px;   /* Breite der Navigation */
    margin: 0 auto 1rem auto !important;
}

.stTabs [data-baseweb="tab"] {
    flex: 1 1 0 !important;       /* Jeder Tab gleich breit */
    text-align: center !important;
    padding: 0.6rem 1rem !important;
    border-radius: 999px !important;
    margin: 0 0.3rem !important;
    min-width: 140px;            /* Mindestbreite pro Tab */
}

/* Wenn ein Tab aktiv ist */
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: var(--burnt-orange) !important;
    color: #fff !important;
    border-color: var(--burnt-orange) !important;
    font-weight: 600 !important;
}

/* Hover-Effekt nur leicht */
.stTabs [data-baseweb="tab"]:hover {
    opacity: 0.92;
}

/* ----------------------------------------------------------
   Karten
-----------------------------------------------------------*/
.stock-card {
    background: var(--bg-card-soft);
    border-radius: 1.4rem;
    padding: 1rem 1.2rem;
    margin-bottom: 0.9rem;
    box-shadow: 0 16px 30px rgba(0,0,0,0.45);
    border: 1px solid rgba(255,255,255,0.04);
}

.stock-card-header {
    font-family: "Montserrat", sans-serif !important;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    font-size: 0.86rem;
    margin-bottom: 0.4rem;
}

.stock-card-sub {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-bottom: 0.4rem;
    font-family: "Inter", sans-serif !important;
}

.stock-card-row {
    font-size: 0.85rem;
    margin: 0.1rem 0;
    font-family: "Inter", sans-serif !important;
}

/* Badges */
.badge-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    padding: 0.18rem 0.6rem;

    font-family: "Montserrat", sans-serif !important;

    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.badge-profit {
    background: rgba(163,255,74,0.35);  /* Retro Yellow-Green */
    color: #A3FF4A;
}

.badge-loss {
    background: rgba(255,107,74,0.35);  /* Retro Coral-Red */
    color: #FF6B4A;
}

.badge-neutral {
    background: rgba(148,163,184,0.18);
    color: #e5e7eb;
}

/* ----------------------------------------------------------
   Tabellen – st.dataframe & st.table im Retro-Theme
-----------------------------------------------------------*/

/* Rahmen & Schatten für alle Tabellen-Container */
.stDataFrame,
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border-radius: 1.2rem !important;
    overflow: hidden !important;
    box-shadow: 0 16px 28px rgba(0,0,0,0.45) !important;
}

/* Innerer Wrapper (damit die Rundung wirklich greift) */
[data-testid="stDataFrame"] > div,
[data-testid="stTable"] > div {
    border-radius: 1.2rem !important;
    overflow: hidden !important;
}

/* Tabellen-Hintergrund – überall Mustard (#FFCE1B) */
.stDataFrame table,
[data-testid="stDataFrame"] table,
[data-testid="stTable"] table {
    background: var(--mustard) !important;   /* #FFCE1B */
    color: #111 !important;
    border-collapse: collapse !important;
    width: 100%;
}

/* Header-Reihe – Burnt Orange (#BE5103) */
.stDataFrame thead tr,
[data-testid="stDataFrame"] thead tr,
[data-testid="stTable"] thead tr {
    background: var(--burnt-orange) !important;   /* #BE5103 */
    color: #fff !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.74rem;
    font-family: "Montserrat", sans-serif !important;
}

/* Zellen-Borders */
.stDataFrame th, .stDataFrame td,
[data-testid="stDataFrame"] th, [data-testid="stDataFrame"] td,
[data-testid="stTable"] th, [data-testid="stTable"] td {
    border-bottom: 1px solid rgba(0,0,0,0.08) !important;
}

/* Scrollbar in interaktiven DataFrames */
.stDataFrame [class*="scrollbar"],
.stDataFrame ::-webkit-scrollbar,
[data-testid="stDataFrame"] [class*="scrollbar"],
[data-testid="stDataFrame"] ::-webkit-scrollbar {
    height: 8px;
}

.stDataFrame ::-webkit-scrollbar-thumb,
[data-testid="stDataFrame"] ::-webkit-scrollbar-thumb {
    background: rgba(0,0,0,0.35);
    border-radius: 999px;
}

/* ----------------------------------------------------------
   Statische Tabellen (st.table)
-----------------------------------------------------------*/

[data-testid="stTable"] {
    border-radius: 1.2rem !important;
    overflow: hidden !important;
    box-shadow: 0 16px 28px rgba(0,0,0,0.45) !important;
}

[data-testid="stTable"] table {
    width: 100%;
    background: var(--mustard) !important;   /* #FFCE1B */
    color: #111 !important;
    border-collapse: collapse !important;
}

[data-testid="stTable"] thead tr {
    background: var(--burnt-orange) !important;   /* #BE5103 */
    color: #fff !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.74rem;
}

[data-testid="stTable"] th,
[data-testid="stTable"] td {
    border-bottom: 1px solid rgba(0,0,0,0.08) !important;
}

/* ----------------------------------------------------------
   Formular-Elemente
-----------------------------------------------------------*/
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stDateInput input {
    background: transparent !important;
    color: #111 !important;
    border-radius: 999px;
    border: none !important;
    padding: 0.35rem 0.8rem;
    font-size: 0.9rem;

    font-family: "Inter", sans-serif !important;
}

.stTextInput > div,
.stNumberInput > div,
.stDateInput > div,
.stTextArea > div {
    background: var(--mustard) !important;
    border-radius: 999px !important;
    border: 2px solid rgba(0,0,0,0.22) !important;
    padding: 0.15rem 0.35rem !important;
}

.stTextInput > div:focus-within,
.stNumberInput > div:focus-within,
.stDateInput > div:focus-within,
.stTextArea > div:focus-within {
    border-color: var(--burnt-orange) !important;
    box-shadow: 0 0 0 2px rgba(190,81,3,0.4);
}

.stForm label, .stForm p {
    color: var(--text-main) !important;
}

/* Selectbox */
.stSelectbox > div > div {
    background: var(--mustard) !important;
    border-radius: 999px !important;
    border: 2px solid rgba(0,0,0,0.22) !important;
}

.stSelectbox div[role="button"] {
    color: #111 !important;
    font-size: 0.9rem;

    font-family: "Inter", sans-serif !important;
}

.stSelectbox [data-baseweb="menu"] {
    background: #FFF9D9 !important;
    border-radius: 1rem !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
}

.stSelectbox [data-baseweb="menu"] div {
    color: #111 !important;
}

/* ----------------------------------------------------------
   Buttons
-----------------------------------------------------------*/
.stApp button {
    border-radius: 999px !important;
    background: var(--burnt-orange) !important;
    color: #FFEFD2 !important;
    padding: 0.55rem 1.4rem !important;

    font-family: "Montserrat", sans-serif !important;

    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.78rem !important;

    border: none !important;
    box-shadow: 0 12px 26px rgba(0,0,0,0.45);
}

.stApp button:hover {
    background: var(--rust) !important;
    box-shadow: 0 16px 32px rgba(0,0,0,0.55);
}

/* ----------------------------------------------------------
   Ladebox
-----------------------------------------------------------*/
.loading-box {
    background: var(--bg-card-soft);
    border-radius: 1.2rem;
    padding: 0.9rem 1rem;
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: 0 16px 30px rgba(0,0,0,0.5);
    margin-bottom: 0.8rem;

    font-family: "Inter", sans-serif !important;
}

.loading-box-title {
    font-family: "Montserrat", sans-serif !important;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.82rem;
}

.loading-box-sub {
    font-size: 0.8rem;
    opacity: 0.96;
    font-family: "Inter", sans-serif !important;
}

</style>
"""