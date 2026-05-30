"""
core.scoring_pipeline — Orchestrateur unifié des 3 systèmes de scoring.

run_full_analysis(ticker) → dict complet avec :
  - unified_score   : 0-10  (SMC + setup_detector via unified_scorer)
  - composite_score : 0-100 (SMA200 + Volume + Reddit + News via scoring.py)
  - grade           : A/B/C/D/NO TRADE

Les deux scores sont calculés en un seul appel. Chaque bloc est protégé
par try/except pour ne jamais bloquer la réponse API.
"""
from __future__ import annotations

from analysis.technical_indicators import clean_for_json


# ── Helpers de collecte de données ───────────────────────────────────────────

def _fetch_market_data(ticker: str) -> dict:
    """Récupère les données de marché pour score_ticker via data_provider (cache 5 min)."""
    try:
        from core.data_provider import get_history
        df = get_history(ticker, interval="1d", period="1y")
        if df is None or df.empty or len(df) < 2:
            return {}
        close      = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2])
        sma200     = float(df["Close"].tail(200).mean()) if len(df) >= 200 else None
        vol_today  = float(df["Volume"].iloc[-1])
        avg_vol    = float(df["Volume"].tail(20).mean()) if len(df) >= 20 else vol_today
        return {
            "current_price":       round(close, 2),
            "prev_close":          round(prev_close, 2),
            "sma200":              round(sma200, 2) if sma200 else None,
            "price_vs_sma200_pct": round((close - sma200) / sma200 * 100, 2) if sma200 else None,
            "volume":              vol_today,
            "relative_volume":     round(vol_today / avg_vol, 2) if avg_vol > 0 else 1.0,
        }
    except Exception:
        return {}


def _fetch_reddit_data(ticker: str) -> dict:
    """Tente de lire les mentions Reddit depuis le CSV scanner (cache)."""
    try:
        from scrapers.reddit import find_scanner_dir, read_watchlist
        scanner_dir = find_scanner_dir()
        if scanner_dir is None:
            return {"mentions": 0, "sentiment": 0.0}
        df = read_watchlist(scanner_dir)
        if df is None or df.empty:
            return {"mentions": 0, "sentiment": 0.0}
        row = df[df["Ticker"].astype(str).str.upper() == ticker.upper()]
        if row.empty:
            return {"mentions": 0, "sentiment": 0.0}
        mentions = int(row.iloc[0].get("Mentions", 0))
        net_sent = float(row.iloc[0].get("Net_Sentiment", 0))
        sentiment = max(-1.0, min(1.0, net_sent / max(mentions, 1)))
        return {"mentions": mentions, "sentiment": sentiment}
    except Exception:
        return {"mentions": 0, "sentiment": 0.0}


def _fetch_news_data(ticker: str) -> dict:
    """Tente de compter les mentions news RSS pour ce ticker."""
    try:
        from scrapers.rss_news import fetch_and_filter
        _, ticker_news, keyword_news, _ = fetch_and_filter(max_per_feed=3)
        ticker_matches   = sum(1 for n in ticker_news   if ticker in n.get("matched_tickers", []))
        keyword_matches  = sum(1 for n in keyword_news  if ticker in n.get("matched_tickers", []))
        return {"ticker_matches": ticker_matches, "keyword_matches": keyword_matches}
    except Exception:
        return {"ticker_matches": 0, "keyword_matches": 0}


# ── Pipeline principal ────────────────────────────────────────────────────────

def run_full_analysis(ticker: str) -> dict:
    """
    Analyse complète d'un ticker en un seul appel.

    Ordre d'exécution :
      1. unified_analysis()  — SMC + setup_detector (score 0-10)
      2. _fetch_market_data() — données prix/volume (cached)
      3. _fetch_reddit_data() — mentions Reddit (cached)
      4. _fetch_news_data()   — mentions RSS
      5. score_ticker()       — score composite 0-100

    Retourne un dict fusionné. Toujours retourne même si l'un des blocs échoue.
    """
    result: dict = {
        "ticker":          ticker,
        "unified_score":   0.0,
        "composite_score": None,
        "grade":           "NO TRADE",
        "error":           None,
    }

    # ── 1. Score unifié SMC (0-10) ────────────────────────────────────────────
    try:
        from analysis.unified_scorer import unified_analysis
        unified = unified_analysis(ticker)
        result.update(unified)
    except Exception as e:
        result["error"] = f"unified_analysis: {e}"

    # ── 2. Score composite (0-100) ────────────────────────────────────────────
    try:
        from analysis.scoring import score_ticker
        md = _fetch_market_data(ticker)
        rd = _fetch_reddit_data(ticker)
        nd = _fetch_news_data(ticker)
        scored = score_ticker(ticker, md, rd, nd)
        result["composite_score"]      = scored.get("total_score")
        result["composite_breakdown"]  = {
            "sma200_score":   scored.get("sma200_score"),
            "volume_score":   scored.get("volume_score"),
            "reddit_score":   scored.get("reddit_score"),
            "news_score":     scored.get("news_score"),
        }
    except Exception as e:
        result["composite_score"]     = None
        result["composite_breakdown"] = {}

    return clean_for_json(result)
