"""
Market Breadth — Ampleur du marché (50 top constituents S&P 500).

Calcule advancers/decliners, A/D ratio, top gainers/losers.
Cache 5 min. Batch download via yf.download() pour rester rapide (<15s).
"""

from __future__ import annotations
import time
from datetime import datetime

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


_SP50 = [
    "AAPL", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "BRK-B",
    "JPM", "LLY", "V", "UNH", "XOM", "COST", "MA", "WMT", "PG", "JNJ",
    "HD", "NFLX", "ABBV", "BAC", "CRM", "AMD", "ORCL", "MRK", "CVX", "PLTR",
    "KO", "PEP", "ACN", "TMO", "ADBE", "IBM", "LIN", "MCD", "CSCO", "TXN",
    "ABT", "GE", "QCOM", "INTU", "AMGN", "NEE", "INTC", "RTX", "SPGI", "CAT",
]
_CACHE_TTL = 300
_breadth_cache: dict = {"data": None, "expires": 0.0}


def clean_for_json(obj):
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_for_json(i) for i in obj]
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    try:
        import math
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return str(obj)


def get_market_breadth() -> dict:
    """
    Télécharge les variations du jour pour les 50 top S&P 500.
    Cache 5 min. Retour dégradé si erreur réseau.
    """
    now = time.time()
    if _breadth_cache["data"] is not None and now < _breadth_cache["expires"]:
        print(f"[MarketBreadth] Cache valide ({int(_breadth_cache['expires'] - now)}s restantes)")
        return _breadth_cache["data"]

    fallback = {
        "advancers": 0, "decliners": 0, "ad_ratio": 1.0,
        "strong_advancers": 0, "strong_decliners": 0,
        "breadth_strength": "unknown",
        "top_gainers": [], "top_losers": [],
        "computed_at": datetime.now().isoformat(),
        "error": None,
    }

    if not _YF_OK or not _PANDAS_OK:
        fallback["error"] = "yfinance ou pandas non disponible"
        return fallback

    try:
        print(f"[MarketBreadth] Téléchargement batch {len(_SP50)} tickers...")
        raw = yf.download(
            _SP50,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw is None or raw.empty:
            fallback["error"] = "Pas de données yfinance"
            return fallback

        changes: list[dict] = []
        close_df = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)

        for ticker in _SP50:
            try:
                if ticker not in close_df.columns:
                    continue
                col = close_df[ticker].dropna()
                if len(col) < 2:
                    continue
                pct = (float(col.iloc[-1]) - float(col.iloc[-2])) / float(col.iloc[-2]) * 100
                changes.append({"ticker": ticker, "change_pct": round(pct, 2)})
            except Exception:
                continue

        if not changes:
            fallback["error"] = "Aucune variation calculable"
            return fallback

        advancers   = sum(1 for c in changes if c["change_pct"] > 0)
        decliners   = sum(1 for c in changes if c["change_pct"] < 0)
        strong_adv  = sum(1 for c in changes if c["change_pct"] >= 1.0)
        strong_dec  = sum(1 for c in changes if c["change_pct"] <= -1.0)
        ad_ratio    = round(advancers / decliners, 2) if decliners > 0 else float(advancers or 1)
        top_gainers = sorted(changes, key=lambda x: -x["change_pct"])[:5]
        top_losers  = sorted(changes, key=lambda x: x["change_pct"])[:5]

        if ad_ratio >= 1.5:
            strength = "bullish"
        elif ad_ratio <= 0.67:
            strength = "bearish"
        else:
            strength = "neutral"

        result = {
            "advancers":        advancers,
            "decliners":        decliners,
            "ad_ratio":         ad_ratio,
            "strong_advancers": strong_adv,
            "strong_decliners": strong_dec,
            "breadth_strength": strength,
            "top_gainers":      top_gainers,
            "top_losers":       top_losers,
            "tickers_analyzed": len(changes),
            "computed_at":      datetime.now().isoformat(),
            "error":            None,
        }
        result = clean_for_json(result)
        print(f"[MarketBreadth] {advancers} adv / {decliners} dec -> A/D={ad_ratio} ({strength})")
        _breadth_cache["data"]    = result
        _breadth_cache["expires"] = now + _CACHE_TTL
        return result

    except Exception as e:
        import traceback
        print(f"[MarketBreadth] ERREUR: {e}\n{traceback.format_exc()}")
        fallback["error"] = str(e)
        return fallback