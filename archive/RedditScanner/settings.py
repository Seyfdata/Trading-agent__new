"""
Configuration centralisée du Trading Agent.
Les valeurs sensibles (clés API) sont dans .env
Ici on met les paramètres de trading et les listes.
"""

# === WATCHLIST ===
# Actions que tu surveilles activement
WATCHLIST = [
    "AAPL",   # Apple
    "NVDA",   # Nvidia
    "TSLA",   # Tesla
    "MSFT",   # Microsoft
    "META",   # Meta (Facebook)
    "AMZN",   # Amazon
    "GOOGL",  # Google
    "AMD",    # AMD
    "AVGO",   # Broadcom
    "QCOM",   # Qualcomm
]

# Noms complets et aliases pour capter les news qui n'utilisent pas le ticker
# Format : "nom dans l'article" → "ticker affiché dans le rapport"
TICKER_ALIASES = {
    # Magnificent 7
    "Apple": "AAPL",
    "iPhone": "AAPL",
    "Nvidia": "NVDA",
    "GeForce": "NVDA",
    "Tesla": "TSLA",
    "Elon Musk": "TSLA",
    "Microsoft": "MSFT",
    "Azure": "MSFT",
    "Meta Platforms": "META",
    "Facebook": "META",
    "Instagram": "META",
    "Zuckerberg": "META",
    "Amazon": "AMZN",
    "AWS": "AMZN",
    "Alphabet": "GOOGL",
    "Google": "GOOGL",
    # Semi-conducteurs
    "Advanced Micro": "AMD",
    "Broadcom": "AVGO",
    "Qualcomm": "QCOM",
    "Snapdragon": "QCOM",
}

# === FLUX RSS ===
# Sources de news à scanner (classées par fiabilité)
RSS_FEEDS = {
    # --- Tier 1 : Sources institutionnelles ---
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Reuters Tech": "https://feeds.reuters.com/reuters/technologyNews",
    "AP Business": "https://rsshub.app/apnews/topics/business",

    # --- Tier 2 : Médias financiers majeurs ---
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

# Mots-clés supplémentaires à détecter (en plus des tickers)
# Si un de ces mots apparaît, la news est considérée comme pertinente
MARKET_KEYWORDS = [
    "Fed", "FOMC", "interest rate", "inflation", "CPI", "NFP",
    "jobs report", "unemployment", "GDP", "earnings",
    "S&P 500", "Nasdaq", "Dow Jones", "Wall Street",
    "semiconductor", "chip", "AI stocks", "tech stocks",
    "tariff", "trade war", "sanctions",
]

# === CALENDRIER MACRO ===
# Événements récurrents à vérifier
# Format : "description" : {"impact": FORT/MOYEN, "heure_cet": "HH:MM"}
MACRO_EVENTS = {
    "FOMC": {
        "impact": "FORT",
        "heure_cet": "20:00",
        "regle": "NO TRADE le jour J. Analyser J+1 à J+2.",
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
        "regle": "NO TRADE le jour J. Attendre la réaction.",
        "frequence": "Mensuel, ~2ème semaine",
    },
    "PPI (Prix producteurs)": {
        "impact": "MOYEN",
        "heure_cet": "14:30",
        "regle": "Risque réduit 0.5%. Éviter 15 min autour de l'annonce.",
        "frequence": "Mensuel",
    },
    "Jobless Claims": {
        "impact": "MOYEN",
        "heure_cet": "14:30",
        "regle": "Risque réduit 0.5%. Attention si chiffre surprise.",
        "frequence": "Chaque jeudi",
    },
    "Retail Sales": {
        "impact": "MOYEN",
        "heure_cet": "14:30",
        "regle": "Risque réduit 0.5%.",
        "frequence": "Mensuel",
    },
    "PCE (dépenses conso)": {
        "impact": "MOYEN-FORT",
        "heure_cet": "14:30",
        "regle": "Indicateur favori de la Fed. Prudence.",
        "frequence": "Mensuel, dernière semaine",
    },
    "GDP (PIB)": {
        "impact": "MOYEN-FORT",
        "heure_cet": "14:30",
        "regle": "Risque réduit 0.5%.",
        "frequence": "Trimestriel",
    },
    "ISM Manufacturing": {
        "impact": "MOYEN",
        "heure_cet": "16:00",
        "regle": "Risque réduit si < 50 (contraction).",
        "frequence": "1er jour ouvré du mois",
    },
}

# Earnings des Magnificent 7 (dates approximatives par trimestre)
# À mettre à jour chaque trimestre !
# Mettre la date au format "YYYY-MM-DD" ou "TBD" si pas encore annoncé
MAG7_EARNINGS = {
    "AAPL": {"Q1_2026": "TBD", "note": "Généralement fin janvier / fin avril / fin juillet / fin octobre"},
    "MSFT": {"Q1_2026": "TBD", "note": "Généralement fin janvier / fin avril / fin juillet / fin octobre"},
    "GOOGL": {"Q1_2026": "TBD", "note": "Généralement fin janvier / fin avril / fin juillet / fin octobre"},
    "AMZN": {"Q1_2026": "TBD", "note": "Généralement début février / fin avril / début août / fin octobre"},
    "NVDA": {"Q1_2026": "TBD", "note": "Généralement fin février / fin mai / fin août / fin novembre"},
    "META": {"Q1_2026": "TBD", "note": "Généralement fin janvier / fin avril / fin juillet / fin octobre"},
    "TSLA": {"Q1_2026": "TBD", "note": "Généralement fin janvier / fin avril / fin juillet / fin octobre"},
}

# === TRADING RULES ===
# Les core rules — ne jamais modifier sans raison
RISK_PCT_MIN = 0.5       # Risque minimum par trade (%)
RISK_PCT_MAX = 1.0       # Risque maximum par trade (%)
RR_MINIMUM = 2.5         # R:R minimum accepté
MAX_TRADES_PER_DAY = 2   # Maximum de trades par jour
MAX_EXPOSURE_PCT = 3.0   # Exposition max simultanée (%)

# Killzone (heure CET)
KILLZONE_START_HOUR = 14
KILLZONE_START_MIN = 30
KILLZONE_END_HOUR = 16
KILLZONE_END_MIN = 30

# === TELEGRAM ===
# Format des messages
EMOJI_BULL = "🟢"
EMOJI_BEAR = "🔴"
EMOJI_NEUTRAL = "⚪"
EMOJI_WARNING = "⚠️"
EMOJI_NEWS = "📰"
EMOJI_CHART = "📊"
EMOJI_CALENDAR = "📅"
EMOJI_FIRE = "🔥"
EMOJI_NO = "🚫"
EMOJI_CHECK = "✅"
