"""
Module de collecte de news via flux RSS.
Récupère les dernières news financières et filtre par tickers + mots-clés marché.

Phase 2 : c'est le premier module que tu fais tourner.
"""

import feedparser
from config.settings import RSS_FEEDS, WATCHLIST, MARKET_KEYWORDS, TICKER_ALIASES


def fetch_all_news(max_per_feed=5):
    """
    Récupère les dernières news de tous les flux RSS.

    Retourne une liste de dicts :
    [{"source": "Reuters", "title": "...", "link": "...", "summary": "..."}]
    """
    all_news = []

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:max_per_feed]:
                all_news.append({
                    "source": source_name,
                    "title": entry.get("title", "Sans titre"),
                    "summary": entry.get("summary", "")[:300],
                    "link": entry.get("link", ""),
                })

        except Exception as e:
            print(f"  [RSS] Erreur sur {source_name}: {e}")

    return all_news


def filter_by_tickers(news_list, tickers=None):
    """
    Filtre les news qui mentionnent un de tes tickers OU le nom de l'entreprise.
    Utilise TICKER_ALIASES pour matcher "Broadcom" → AVGO, "Nvidia" → NVDA, etc.

    Retourne les news pertinentes avec les tickers trouvés.
    """
    if tickers is None:
        tickers = WATCHLIST

    relevant = []

    for news in news_list:
        text = news["title"] + " " + news["summary"]
        text_upper = text.upper()

        matched_tickers = set()

        # 1. Chercher les tickers directs (AAPL, NVDA, etc.)
        for t in tickers:
            if t in text_upper:
                matched_tickers.add(t)

        # 2. Chercher les noms/aliases (Broadcom → AVGO, Nvidia → NVDA, etc.)
        for alias, ticker in TICKER_ALIASES.items():
            if alias.lower() in text.lower():
                matched_tickers.add(ticker)

        if matched_tickers:
            news["matched_tickers"] = sorted(matched_tickers)
            news["match_type"] = "TICKER"
            relevant.append(news)

    return relevant


def filter_by_keywords(news_list, keywords=None):
    """
    Filtre les news qui mentionnent des mots-clés macro/marché.
    Complément au filtrage par tickers.

    Retourne les news pertinentes avec les mots-clés trouvés.
    """
    if keywords is None:
        keywords = MARKET_KEYWORDS

    relevant = []

    for news in news_list:
        text = (news["title"] + " " + news["summary"]).upper()

        matched = [kw for kw in keywords if kw.upper() in text]

        if matched:
            news["matched_keywords"] = matched
            news["match_type"] = "KEYWORD"
            relevant.append(news)

    return relevant


def fetch_and_filter(max_per_feed=5, tickers=None, keywords=None):
    """
    Fonction tout-en-un : collecte + filtrage tickers + filtrage keywords.
    Déduplique les résultats (une news peut matcher ticker ET keyword).

    Retourne (all_news, ticker_news, keyword_news, combined_unique)
    """
    all_news = fetch_all_news(max_per_feed)

    ticker_news = filter_by_tickers(all_news, tickers)
    keyword_news = filter_by_keywords(all_news, keywords)

    # Dédupliquer : fusionner les deux listes sans doublons (par titre)
    seen_titles = set()
    combined = []

    for news in ticker_news:
        if news["title"] not in seen_titles:
            seen_titles.add(news["title"])
            combined.append(news)

    for news in keyword_news:
        if news["title"] not in seen_titles:
            seen_titles.add(news["title"])
            combined.append(news)

    return all_news, ticker_news, keyword_news, combined


# === TEST ===
if __name__ == "__main__":
    print("Récupération des news...")
    all_news, ticker_news, keyword_news, combined = fetch_and_filter(max_per_feed=3)

    print(f"Total : {len(all_news)} news récupérées")
    print(f"Par tickers : {len(ticker_news)}")
    print(f"Par mots-clés : {len(keyword_news)}")
    print(f"Combiné (unique) : {len(combined)}\n")

    for n in combined[:10]:
        match_type = n.get("match_type", "?")
        tickers = ", ".join(n.get("matched_tickers", []))
        keywords = ", ".join(n.get("matched_keywords", [])[:3])
        tag = tickers if match_type == "TICKER" else keywords
        print(f"[{match_type}] [{tag}] {n['title']}")
