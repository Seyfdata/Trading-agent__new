"""
Calcul du score composite (0-100) pour chaque ticker de la watchlist.
Agrège les données market, Reddit et news en un score actionnable.
"""

from config.settings import WATCHLIST


# ── Score SMA200 (0-25) ─────────────────────────────────────────────────────

def _sma200_score(market_data: dict) -> tuple[int, str]:
    """
    Calcule le sous-score basé sur la distance au SMA200.

    market_data doit contenir :
        - current_price  (float)
        - sma200         (float)
        - price_vs_sma200_pct (float, optionnel — calculé si absent)
    """
    price = market_data.get("current_price")
    sma200 = market_data.get("sma200")

    if price is None or sma200 is None or sma200 == 0:
        return 0, "no_data"

    pct = market_data.get("price_vs_sma200_pct", (price - sma200) / sma200 * 100)

    if pct < 0:
        # Sous la SMA200
        detail = "below_sma200"
        # Plus c'est proche de 0 (en remontée), plus c'est intéressant
        if pct >= -5:
            score = 25  # juste sous la SMA200, rebond probable
        elif pct >= -10:
            score = 22
        else:
            score = 20  # discount profond
    elif pct <= 3:
        # Dans la zone ±3% autour de la SMA200
        detail = "near_sma200"
        score = 18
    elif pct <= 10:
        # Au-dessus, tendance saine
        detail = "above_sma200_healthy"
        score = 13
    else:
        # Étendu au-dessus — moins intéressant
        detail = "above_sma200_extended"
        score = max(0, int(10 - (pct - 10) * 0.3))

    return min(score, 25), detail


# ── Score Volume (0-25) ─────────────────────────────────────────────────────

def _volume_score(market_data: dict) -> tuple[int, str]:
    """
    Calcule le sous-score basé sur le volume relatif (vol / vol_avg_20d).

    market_data doit contenir :
        - volume          (int/float)
        - volume_avg_20d  (int/float)
        - relative_volume (float, optionnel — calculé si absent)
    """
    volume = market_data.get("volume")
    avg = market_data.get("volume_avg_20d")

    if volume is None or avg is None or avg == 0:
        return 5, "no_data"

    rel_vol = market_data.get("relative_volume", volume / avg)

    if rel_vol >= 2.0:
        return 25, "institutional_activity"
    elif rel_vol >= 1.5:
        return 18, "high_volume"
    elif rel_vol >= 1.2:
        return 10, "above_average"
    else:
        return 5, "normal"


# ── Score Reddit (0-25) ─────────────────────────────────────────────────────

def _reddit_score(reddit_data: dict) -> tuple[int, str]:
    """
    Calcule le sous-score basé sur les mentions Reddit.

    reddit_data doit contenir :
        - mentions  (int)
        - sentiment (float, entre -1 et 1)
    """
    mentions = reddit_data.get("mentions", 0)
    sentiment = reddit_data.get("sentiment", 0.0)

    positive = sentiment > 0.1

    if mentions > 10 and positive:
        score = min(25, 20 + int((mentions - 10) * 0.5))
        detail = "high_mentions_positive"
    elif mentions > 10:
        score = 12
        detail = "high_mentions_neutral"
    elif mentions > 5 and positive:
        score = min(18, 12 + mentions)
        detail = "medium_mentions_positive"
    elif mentions > 5:
        score = 8
        detail = "medium_mentions_neutral"
    elif mentions > 2:
        score = min(10, 5 + mentions)
        detail = "low_mentions"
    else:
        score = 0
        detail = "no_mentions"

    return min(score, 25), detail


# ── Score croisement Reddit × News × Tendance (–10 à +10) ──────────────────

def _cross_validation_score(
    reddit_data: dict,
    news_data: dict,
    trend_data: dict = None,
    in_watchlist: bool = True,
) -> tuple[int, str]:
    """
    Mesure la fiabilité du signal Reddit par croisement avec d'autres sources.

    Règles :
        +5   Reddit mentionné ET dans les news RSS (confirmation multi-source)
        +3   Reddit mentionné ET tendance RISING sur 5 jours
        -5   Reddit mentionné MAIS ni dans les news NI dans la watchlist
             (signal isolé, probablement bruit ou penny stock)

    Les bonus se cumulent. Le résultat est plafonné à [–10, +10].
    """
    mentions = reddit_data.get("mentions", 0)
    if mentions == 0:
        return 0, "no_reddit"

    bonus = 0
    flags = []

    in_news = (news_data.get("ticker_matches", 0) > 0)
    is_rising = bool(trend_data and trend_data.get("trend") == "RISING")

    if in_news:
        bonus += 5
        flags.append("reddit+news")

    if is_rising:
        bonus += 3
        flags.append("trending_rising")

    if not in_news and not in_watchlist:
        bonus -= 5
        flags.append("isolated_signal")

    score = max(-10, min(10, bonus))
    detail = "+".join(flags) if flags else "neutral"

    return score, detail


# ── Score News (0-25) ───────────────────────────────────────────────────────

def _news_score(news_data: dict) -> tuple[int, str]:
    """
    Calcule le sous-score basé sur les news filtrées.

    news_data doit contenir :
        - ticker_matches   (int)  : news qui mentionnent le ticker directement
        - keyword_matches  (int)  : news capturées via MARKET_KEYWORDS uniquement
    """
    ticker_matches = news_data.get("ticker_matches", 0)
    keyword_matches = news_data.get("keyword_matches", 0)

    if ticker_matches >= 3:
        score = min(25, 20 + ticker_matches)
        detail = "strong_ticker_news"
    elif ticker_matches >= 1:
        score = min(15, 10 + ticker_matches * 2)
        detail = "some_ticker_news"
    elif keyword_matches > 0:
        score = 5
        detail = "keyword_only"
    else:
        score = 0
        detail = "no_news"

    return min(score, 25), detail


# ── Score Options (–3 à +3) ─────────────────────────────────────────────────

def _options_score(options_data: dict) -> tuple[int, str]:
    """
    Bonus/malus basé sur le sentiment options.

    options_data doit contenir :
        - overall_direction  ("BULLISH" | "NEUTRAL" | "BEARISH")
        - conviction         ("HIGH" | "MEDIUM" | "LOW")

    Règles :
        sentiment_score > +0.3 → +3
        sentiment_score < −0.3 → −3
        sinon → 0
    """
    if not options_data:
        return 0, "no_data"

    direction  = options_data.get("overall_direction", "NEUTRAL")
    conviction = options_data.get("conviction", "LOW")

    conviction_factor = {"HIGH": 1.0, "MEDIUM": 0.67, "LOW": 0.33}.get(conviction, 0.33)

    if direction == "BULLISH":
        sentiment_score = conviction_factor
    elif direction == "BEARISH":
        sentiment_score = -conviction_factor
    else:
        sentiment_score = 0.0

    if sentiment_score > 0.3:
        return 3, f"options_bullish_{conviction.lower()}"
    if sentiment_score < -0.3:
        return -3, f"options_bearish_{conviction.lower()}"
    return 0, "options_neutral"


# ── Fonction principale ─────────────────────────────────────────────────────

def score_ticker(
    ticker: str,
    market_data: dict,
    reddit_data: dict,
    news_data: dict,
    trend_data: dict = None,
    in_watchlist: bool = True,
    options_data: dict = None,
) -> dict:
    """
    Calcule le score composite (0-100) pour un ticker.

    Paramètres
    ----------
    ticker       : str   — symbole boursier (ex: "NVDA")
    market_data  : dict  — données de marché (prix, SMA200, volume…)
    reddit_data  : dict  — données Reddit (mentions, sentiment)
    news_data    : dict  — données news (ticker_matches, keyword_matches)
    trend_data   : dict  — tendance Reddit 5j optionnelle {"trend": "RISING"|…}
    in_watchlist : bool  — ticker appartient à la watchlist perso (défaut True)
    options_data : dict  — sentiment options (overall_direction, conviction) — optionnel

    Retourne
    --------
    dict avec total_score (0-100), sous-scores et components détaillés.
    Le sous-score cross_validation (–10 à +10) mesure la fiabilité du signal.
    """
    sma200, sma200_detail = _sma200_score(market_data)
    volume, volume_detail = _volume_score(market_data)
    reddit, reddit_detail = _reddit_score(reddit_data)
    news, news_detail = _news_score(news_data)
    cross, cross_detail = _cross_validation_score(
        reddit_data, news_data, trend_data, in_watchlist
    )
    options, options_detail = _options_score(options_data or {})

    total = max(0, min(100, sma200 + volume + reddit + news + cross + options))

    return {
        "ticker": ticker,
        "total_score": total,
        "sma200_score": sma200,
        "volume_score": volume,
        "reddit_score": reddit,
        "news_score": news,
        "cross_validation_score": cross,
        "options_score": options,
        "options_sentiment": options_data or {},
        "components": {
            "sma200_detail": sma200_detail,
            "volume_detail": volume_detail,
            "reddit_detail": reddit_detail,
            "news_detail": news_detail,
            "cross_validation_detail": cross_detail,
            "options_detail": options_detail,
        },
    }


# ── Contexte de marché ──────────────────────────────────────────────────────

def score_market_context(market_context: dict) -> dict:
    """
    Calcule le régime de marché et la recommandation de taille de position.

    market_context doit contenir :
        - vix         (float)
        - spy_change  (float, variation % du jour)
        - dxy         (float, optionnel)
        - us10y       (float, optionnel)
    """
    vix = market_context.get("vix", 20)
    spy_change = market_context.get("spy_change", 0)
    dxy = market_context.get("dxy")
    us10y = market_context.get("us10y")

    # Score de base selon VIX
    if vix < 15:
        base_score = 85
        regime = "BULL"
        sizing = "1%"
    elif vix < 20:
        base_score = 50
        regime = "NEUTRAL"
        sizing = "0.5%"
    elif vix < 25:
        base_score = 30
        regime = "BEAR"
        sizing = "0.5%"
    else:
        base_score = 10
        regime = "BEAR"
        sizing = "NO TRADE"

    # Bonus/malus SPY
    if spy_change > 0.5:
        base_score = min(100, base_score + 10)
        if regime == "NEUTRAL":
            regime = "BULL"
            sizing = "1%"
    elif spy_change < -0.5:
        base_score = max(0, base_score - 10)
        if regime == "BULL" and vix >= 15:
            regime = "NEUTRAL"
            sizing = "0.5%"

    # Bonus/malus DXY (dollar fort = pression sur actions)
    if dxy is not None:
        if dxy > 106:
            base_score = max(0, base_score - 5)
        elif dxy < 100:
            base_score = min(100, base_score + 5)

    # Bonus/malus US10Y (taux élevés = pression sur multiples)
    if us10y is not None:
        if us10y > 4.5:
            base_score = max(0, base_score - 5)
        elif us10y < 3.5:
            base_score = min(100, base_score + 5)

    # Recalibrage final du sizing
    if base_score >= 70:
        regime = "BULL"
        sizing = "1%"
    elif base_score >= 40:
        if regime == "BULL":
            regime = "NEUTRAL"
        sizing = "0.5%"
    else:
        sizing = "NO TRADE"

    return {
        "regime": regime,
        "score": base_score,
        "sizing_recommendation": sizing,
        "details": {
            "vix": vix,
            "spy_change": spy_change,
            "dxy": dxy,
            "us10y": us10y,
        },
    }


# ── Classement ─────────────────────────────────────────────────────────────

def rank_tickers(scored_list: list[dict]) -> list[dict]:
    """
    Trie les tickers par score décroissant et marque le top 3.

    Paramètres
    ----------
    scored_list : liste de dicts retournés par score_ticker()

    Retourne
    --------
    Liste triée, chaque élément a un champ "rank" (int) et "top3" (bool).
    """
    sorted_list = sorted(scored_list, key=lambda x: x["total_score"], reverse=True)
    for i, item in enumerate(sorted_list):
        item["rank"] = i + 1
        item["top3"] = i < 3
    return sorted_list


# ── Test basique ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Test scoring.py ===\n")

    # Données de test pour quelques tickers
    test_cases = [
        {
            "ticker": "NVDA",
            "market_data": {
                "current_price": 118.0,
                "sma200": 120.0,        # légèrement sous SMA200
                "volume": 52_000_000,
                "volume_avg_20d": 25_000_000,  # vol 2x
            },
            "reddit_data": {"mentions": 15, "sentiment": 0.4},
            "news_data": {"ticker_matches": 4, "keyword_matches": 2},
        },
        {
            "ticker": "AAPL",
            "market_data": {
                "current_price": 210.0,
                "sma200": 195.0,        # +7.7% au-dessus SMA200
                "volume": 55_000_000,
                "volume_avg_20d": 50_000_000,  # vol normal
            },
            "reddit_data": {"mentions": 8, "sentiment": 0.2},
            "news_data": {"ticker_matches": 2, "keyword_matches": 1},
        },
        {
            "ticker": "PLTR",
            "market_data": {
                "current_price": 82.0,
                "sma200": 65.0,         # +26% au-dessus SMA200 (étendu)
                "volume": 38_000_000,
                "volume_avg_20d": 30_000_000,
            },
            "reddit_data": {"mentions": 20, "sentiment": 0.6},
            "news_data": {"ticker_matches": 3, "keyword_matches": 0},
        },
        {
            "ticker": "INTC",
            "market_data": {
                "current_price": 19.5,
                "sma200": 23.0,         # -15% sous SMA200
                "volume": 48_000_000,
                "volume_avg_20d": 35_000_000,
            },
            "reddit_data": {"mentions": 3, "sentiment": -0.1},
            "news_data": {"ticker_matches": 1, "keyword_matches": 3},
        },
    ]

    scored = [
        score_ticker(
            tc["ticker"],
            tc["market_data"],
            tc["reddit_data"],
            tc["news_data"],
        )
        for tc in test_cases
    ]

    ranked = rank_tickers(scored)

    print(f"{'Rank':<5} {'Ticker':<8} {'Total':>6} {'SMA200':>8} {'Volume':>8} {'Reddit':>8} {'News':>6} {'Top3'}")
    print("-" * 65)
    for r in ranked:
        top3 = "***" if r["top3"] else ""
        print(
            f"{r['rank']:<5} {r['ticker']:<8} {r['total_score']:>6} "
            f"{r['sma200_score']:>8} {r['volume_score']:>8} "
            f"{r['reddit_score']:>8} {r['news_score']:>6} {top3}"
        )

    print()

    # Contexte de marché
    ctx = score_market_context({
        "vix": 18.5,
        "spy_change": 0.3,
        "dxy": 103.2,
        "us10y": 4.2,
    })
    print(f"Contexte marché : {ctx['regime']} | Score {ctx['score']} | Taille : {ctx['sizing_recommendation']}")
    print(f"  VIX={ctx['details']['vix']}  SPY={ctx['details']['spy_change']:+.1f}%  DXY={ctx['details']['dxy']}  US10Y={ctx['details']['us10y']}%")

    print("\n[OK] scoring.py fonctionne correctement.")
