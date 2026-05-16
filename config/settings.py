"""
Configuration centralisÃ©e du Trading Agent.
Les valeurs sensibles (clÃ©s API) sont dans .env
Ici on met les paramÃ¨tres de trading et les listes.

Les valeurs WATCHLIST, TICKER_ALIASES et les rÃ¨gles de trading sont chargÃ©es
depuis config/config.yaml si ce fichier existe, sinon les valeurs en dur
ci-dessous servent de fallback.
"""

from config.loader import (
    get_watchlist,
    get_aliases,
    get_killzone,
    get_trading_rules,
    get_dashboard_config,
)

# === WATCHLIST ===
# ChargÃ©e depuis config.yaml (fallback : valeurs en dur ci-dessous)
WATCHLIST = get_watchlist()

# Noms complets et aliases pour capter les news qui n'utilisent pas le ticker
# Format : "nom dans l'article" â†’ "ticker affichÃ© dans le rapport"
TICKER_ALIASES = get_aliases()


# === FLUX RSS ===
# Sources de news Ã  scanner (classÃ©es par fiabilitÃ©)
RSS_FEEDS = {
    # --- Tier 1 : Sources institutionnelles ---
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Reuters Tech": "https://feeds.reuters.com/reuters/technologyNews",
    "AP Business": "https://rsshub.app/apnews/topics/business",

    # --- Tier 2 : MÃ©dias financiers majeurs ---
    "CNBC Top News": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "CNBC Tech": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "MarketWatch Top": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "MarketWatch Stocks": "http://feeds.marketwatch.com/marketwatch/marketpulse/",

    # --- Tier 3 : Analyse et opinions ---
    "Seeking Alpha Market News": "https://seekingalpha.com/market_currents.xml",

    # --- Tier 4 : Institutionnel / Fed ---
    "Fed Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
}

# Mots-clÃ©s supplÃ©mentaires Ã  dÃ©tecter (en plus des tickers)
# Si un de ces mots apparaÃ®t, la news est considÃ©rÃ©e comme pertinente
MARKET_KEYWORDS = [
    "Fed", "FOMC", "interest rate", "inflation", "CPI", "NFP",
    "jobs report", "unemployment", "GDP", "earnings",
    "S&P 500", "Nasdaq", "Dow Jones", "Wall Street",
    "semiconductor", "chip", "AI stocks", "tech stocks",
    "tariff", "trade war", "sanctions",
]

# === CALENDRIER MACRO ===
# Ã‰vÃ©nements rÃ©currents Ã  vÃ©rifier
# Format : "description" : {"impact": FORT/MOYEN, "heure_cet": "HH:MM"}
MACRO_EVENTS = {
    "FOMC": {
        "impact": "FORT",
        "heure_cet": "20:00",
        "regle": "NO TRADE le jour J. Analyser J+1 Ã  J+2.",
        "frequence": "8x par an",
    },
    "NFP (Non-Farm Payrolls)": {
        "impact": "FORT",
        "heure_cet": "14:30",
        "regle": "NO TRADE le jour J. Setups post-NFP J+1.",
        "frequence": "1er vendredi du mois",
    },
    "CPI (Inflation)": {
        "impact": "FORT",
        "heure_cet": "14:30",
        "regle": "NO TRADE le jour J. Attendre la rÃ©action.",
        "frequence": "Mensuel, ~2Ã¨me semaine",
    },
    "PPI (Prix producteurs)": {
        "impact": "MOYEN",
        "heure_cet": "14:30",
        "regle": "Risque rÃ©duit 0.5%. Ã‰viter 15 min autour de l'annonce.",
        "frequence": "Mensuel",
    },
    "Jobless Claims": {
        "impact": "MOYEN",
        "heure_cet": "14:30",
        "regle": "Risque rÃ©duit 0.5%. Attention si chiffre surprise.",
        "frequence": "Chaque jeudi",
    },
    "Retail Sales": {
        "impact": "MOYEN",
        "heure_cet": "14:30",
        "regle": "Risque rÃ©duit 0.5%.",
        "frequence": "Mensuel",
    },
    "PCE (dÃ©penses conso)": {
        "impact": "MOYEN-FORT",
        "heure_cet": "14:30",
        "regle": "Indicateur favori de la Fed. Prudence.",
        "frequence": "Mensuel, derniÃ¨re semaine",
    },
    "GDP (PIB)": {
        "impact": "MOYEN-FORT",
        "heure_cet": "14:30",
        "regle": "Risque rÃ©duit 0.5%.",
        "frequence": "Trimestriel",
    },
    "ISM Manufacturing": {
        "impact": "MOYEN",
        "heure_cet": "16:00",
        "regle": "Risque rÃ©duit si < 50 (contraction).",
        "frequence": "1er jour ouvrÃ© du mois",
    },
}

# Earnings des Magnificent 7 (dates approximatives par trimestre)
# Ã€ mettre Ã  jour chaque trimestre !
# Mettre la date au format "YYYY-MM-DD" ou "TBD" si pas encore annoncÃ©
MAG7_EARNINGS = {
    "AAPL": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement fin janvier / fin avril / fin juillet / fin octobre"},
    "MSFT": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement fin janvier / fin avril / fin juillet / fin octobre"},
    "GOOGL": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement fin janvier / fin avril / fin juillet / fin octobre"},
    "AMZN": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement dÃ©but fÃ©vrier / fin avril / dÃ©but aoÃ»t / fin octobre"},
    "NVDA": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement fin fÃ©vrier / fin mai / fin aoÃ»t / fin novembre"},
    "META": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement fin janvier / fin avril / fin juillet / fin octobre"},
    "TSLA": {"Q1_2026": "TBD", "note": "GÃ©nÃ©ralement fin janvier / fin avril / fin juillet / fin octobre"},
}

# === TRADING RULES ===
# ChargÃ©es depuis config.yaml
_trading = get_trading_rules()
RISK_PCT_MIN = _trading["risk_pct_min"]
RISK_PCT_MAX = _trading["risk_pct_max"]
RR_MINIMUM = _trading["rr_minimum"]
MAX_TRADES_PER_DAY = _trading["max_trades_per_day"]
MAX_EXPOSURE_PCT = _trading["max_exposure_pct"]

# Killzone (heure CET)
_kz = get_killzone()
_kz_start = _kz.get("start", "14:30").split(":")
_kz_end = _kz.get("end", "16:30").split(":")
KILLZONE_START_HOUR = int(_kz_start[0])
KILLZONE_START_MIN = int(_kz_start[1])
KILLZONE_END_HOUR = int(_kz_end[0])
KILLZONE_END_MIN = int(_kz_end[1])
KILLZONE_TEST_MODE = False   # Mettre True pour forcer la killzone en dev

# Sessions de marché (heures CET / Europe/Paris)
TZ_MARKET          = "Europe/Paris"
SESSION_ASIA_CET   = {"start_h": 1,  "start_m": 0,  "end_h": 6,  "end_m": 0}
SESSION_LONDON_CET = {"start_h": 8,  "start_m": 0,  "end_h": 9,  "end_m": 30}
SESSION_NY_CET     = {"start_h": 14, "start_m": 30, "end_h": 21, "end_m": 0}

# === TELEGRAM ===
_dashboard = get_dashboard_config()
TELEGRAM_ENABLED = _dashboard.get("telegram_enabled", False)

# Format des messages
EMOJI_BULL = "ðŸŸ¢"
EMOJI_BEAR = "ðŸ”´"
EMOJI_NEUTRAL = "âšª"
EMOJI_WARNING = "âš ï¸"
EMOJI_NEWS = "ðŸ“°"
EMOJI_CHART = "ðŸ“Š"
EMOJI_CALENDAR = "ðŸ“…"
EMOJI_FIRE = "ðŸ”¥"
EMOJI_NO = "ðŸš«"
EMOJI_CHECK = "âœ…"

