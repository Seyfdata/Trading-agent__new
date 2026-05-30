"""
Router: endpoints marché.
Couvre: ping, market, tickers, breadth, history, postmarket, refresh.
"""
from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter

from core.data_provider import get_history, get_fast_info
from config.settings import WATCHLIST
from scrapers.market_data import get_market_context, scan_watchlist
from scrapers.rss_news import fetch_and_filter
from scrapers.reddit import find_scanner_dir, read_watchlist as read_reddit_csv, scan_reddit_direct
from analysis.scoring import score_ticker, score_market_context, rank_tickers
from analysis.technical_indicators import clean_for_json
from database.models import (
    save_scores, save_market_context,
    get_score_history, get_score_trend,
)
from dashboard.state import _today_alerts

router = APIRouter()

# ── Indicateurs macro supplémentaires ────────────────────────────────────────

_MACRO_INDICATORS = [
    {"symbol": "^IRX", "name": "T-Bill 13W"},
    {"symbol": "^FVX", "name": "Treasury 5Y"},
    {"symbol": "^TNX", "name": "Treasury 10Y"},
    {"symbol": "^TYX", "name": "Treasury 30Y"},
    {"symbol": "GC=F",  "name": "Gold"},
    {"symbol": "CL=F",  "name": "WTI Crude"},
]


def _fetch_macro_indicators() -> list:
    """Récupère les indicateurs macro via yfinance. Try/except individuel par symbole."""
    results = []
    for ind in _MACRO_INDICATORS:
        try:
            hist = get_history(ind["symbol"], interval="1d", period="5d")
            if hist is None or hist.empty or len(hist) < 2:
                results.append({"symbol": ind["symbol"], "name": ind["name"],
                                 "price": None, "change_pct": None})
                continue
            price = float(hist["Close"].iloc[-1])
            prev  = float(hist["Close"].iloc[-2])
            change_pct = round((price - prev) / prev * 100, 2) if prev else None
            results.append({"symbol": ind["symbol"], "name": ind["name"],
                             "price": round(price, 4), "change_pct": change_pct})
        except Exception:
            results.append({"symbol": ind["symbol"], "name": ind["name"],
                             "price": None, "change_pct": None})
    return results


# ── Helpers internes ──────────────────────────────────────────────────────────

def _extract_scoring_ctx(context: dict) -> dict:
    """Convertit le dict brut de get_market_context() pour score_market_context()."""
    ctx = {}
    if not context:
        return ctx
    vix = context.get("^VIX")
    spy = context.get("SPY")
    dxy = context.get("DX-Y.NYB")
    tny = context.get("^TNX")
    if vix and "price" in vix:
        ctx["vix"] = vix["price"]
    if spy and "change_pct" in spy:
        ctx["spy_change"] = spy["change_pct"]
    if dxy and "price" in dxy:
        ctx["dxy"] = dxy["price"]
    if tny and "price" in tny:
        ctx["us10y"] = tny["price"]
    return ctx


def _instrument(context: dict, key: str) -> dict:
    """Extrait {price, change} pour un instrument du market context."""
    info = context.get(key, {})
    if "error" in info or "price" not in info:
        return {"price": None, "change": None}
    return {"price": info["price"], "change": info.get("change_pct")}


def _reddit_map_from_csv(scanner_dir) -> dict:
    """Lit le CSV Reddit et retourne {ticker: {mentions, sentiment}}."""
    if scanner_dir is None:
        return {}
    try:
        df = read_reddit_csv(scanner_dir)
        if df is None or df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            if not ticker:
                continue
            mentions = int(row.get("Mentions", 0))
            net_sent = float(row.get("Net_Sentiment", 0))
            sentiment = max(-1.0, min(1.0, net_sent / max(mentions, 1)))
            result[ticker] = {"mentions": mentions, "sentiment": sentiment}
        return result
    except Exception:
        return {}


def _reddit_map_from_direct(watchlist_results: list) -> dict:
    """Convertit les watchlist_results de scan_reddit_direct en {ticker: {mentions, sentiment}}."""
    result = {}
    for r in watchlist_results:
        ticker = r.get("ticker", "")
        if not ticker:
            continue
        mentions = int(r.get("mentions", 0))
        net_sent = float(r.get("net_sentiment", 0))
        sentiment = max(-1.0, min(1.0, net_sent / max(mentions, 1)))
        result[ticker] = {"mentions": mentions, "sentiment": sentiment}
    return result


def _news_map_from_lists(ticker_news: list, keyword_news: list) -> dict:
    """Construit {ticker: {ticker_matches, keyword_matches}} depuis les listes de news."""
    result = {}
    for news in ticker_news:
        for t in news.get("matched_tickers", []):
            entry = result.setdefault(t, {"ticker_matches": 0, "keyword_matches": 0})
            entry["ticker_matches"] += 1
    for news in keyword_news:
        for t in news.get("matched_tickers", []):
            entry = result.setdefault(t, {"ticker_matches": 0, "keyword_matches": 0})
            entry["keyword_matches"] += 1
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ping")
def ping():
    return {"status": "ok", "message": "API fonctionne"}


@router.get("/market")
def get_market():
    """Contexte marché scoré : SPY, QQQ, VIX, DXY, US10Y + régime BULL/NEUTRAL/BEAR."""
    try:
        context = get_market_context()
        if not context:
            return {"error": "yfinance indisponible", "data": None}

        scoring_ctx = _extract_scoring_ctx(context)
        scored = score_market_context(scoring_ctx)

        return clean_for_json({
            "regime": scored["regime"],
            "score": scored["score"],
            "sizing_recommendation": scored["sizing_recommendation"],
            "instruments": {
                "spy":   _instrument(context, "SPY"),
                "qqq":   _instrument(context, "QQQ"),
                "vix":   _instrument(context, "^VIX"),
                "dxy":   _instrument(context, "DX-Y.NYB"),
                "us10y": _instrument(context, "^TNX"),
            },
            "macro_indicators": _fetch_macro_indicators(),
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return {"error": str(e), "data": None}


@router.get("/tickers")
def get_tickers():
    """Watchlist complète scorée et classée par score décroissant."""
    try:
        scan = scan_watchlist()
        if not scan:
            return {"error": "scan_watchlist indisponible", "data": []}

        _, ticker_news, keyword_news, _ = fetch_and_filter(max_per_feed=3)
        scanner_dir = find_scanner_dir()
        reddit_map = _reddit_map_from_csv(scanner_dir)
        news_map = _news_map_from_lists(ticker_news, keyword_news)

        scored_list = []
        for r in scan:
            if "error" in r:
                continue
            ticker = r["ticker"]
            md = {
                "current_price": r.get("price"),
                "sma200": r.get("sma200"),
                "price_vs_sma200_pct": r.get("dist_sma200"),
                "volume": r.get("vol_today"),
                "relative_volume": r.get("vol_relative"),
            }
            rd = reddit_map.get(ticker, {"mentions": 0, "sentiment": 0.0})
            nd = news_map.get(ticker, {"ticker_matches": 0, "keyword_matches": 0})
            result = score_ticker(ticker, md, rd, nd)
            result["market"] = {
                "price": r.get("price"),
                "change_day": r.get("change_day"),
                "change_week": r.get("change_week"),
                "sma200": r.get("sma200"),
                "dist_sma200": r.get("dist_sma200"),
                "above_sma200": r.get("above_sma200"),
                "vol_relative": r.get("vol_relative"),
            }
            result["reddit"] = rd
            result["news_count"] = nd
            scored_list.append(result)

        ranked = rank_tickers(scored_list)
        return clean_for_json({
            "count": len(ranked),
            "tickers": ranked,
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return {"error": str(e), "data": []}


@router.get("/breadth")
def get_breadth():
    """Ampleur du marché (50 top S&P 500) : advancers/decliners, A/D ratio."""
    try:
        from analysis.market_breadth import get_market_breadth
        return clean_for_json(get_market_breadth())
    except Exception as e:
        print(f"[API] /api/breadth error: {e}")
        return {"error": str(e), "ad_ratio": 1.0, "breadth_strength": "unknown"}


@router.get("/history")
def get_score_history_endpoint(days: int = 14):
    """Historique des scores sur N jours pour les tickers avec données."""
    try:
        history = {}
        for ticker in WATCHLIST:
            entries = get_score_history(ticker, days=days)
            if entries:
                trend = get_score_trend(ticker, days=7)
                history[ticker] = {
                    "scores": entries,
                    "trend": trend["trend"],
                    "delta": trend["delta"],
                }

        def _latest_score(item):
            entries = item[1]["scores"]
            return entries[0]["total_score"] if entries else 0

        top5 = dict(
            sorted(history.items(), key=_latest_score, reverse=True)[:5]
        )

        return {
            "days": days,
            "tickers": top5,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "tickers": {}}


@router.get("/postmarket")
def get_postmarket():
    """Résumé post-market : top 3 gainers/losers, volume, alertes killzone du jour."""
    today = datetime.now().strftime("%Y-%m-%d")
    _empty = {
        "date": today,
        "top_gainers": [], "top_losers": [], "summary": [],
        "market_close": {}, "killzone_alerts_count": 0,
    }
    try:
        results = []
        for ticker in WATCHLIST:
            try:
                hist = get_history(ticker, interval="1d", period="30d")
                if hist.empty or len(hist) < 2:
                    continue
                last       = hist.iloc[-1]
                prev       = hist.iloc[-2]
                close      = float(last["Close"])
                prev_close = float(prev["Close"])
                vol_today  = float(last["Volume"])
                avg_vol_20 = float(hist["Volume"].tail(20).mean()) if len(hist) >= 20 else vol_today
                chg_pct    = (close - prev_close) / prev_close * 100 if prev_close else 0.0
                vol_ratio  = vol_today / avg_vol_20 if avg_vol_20 > 0 else 1.0
                results.append({
                    "ticker":    ticker,
                    "close":     round(close, 2),
                    "change_pct": round(chg_pct, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "alert_triggered": any(
                        a.get("ticker") == ticker and a.get("date") == today
                        for a in _today_alerts
                    ),
                })
            except Exception:
                continue

        if not results:
            return clean_for_json(dict(_empty, error="aucune donnée yfinance"))

        sorted_chg  = sorted(results, key=lambda x: x["change_pct"], reverse=True)
        top_gainers = sorted_chg[:3]
        top_losers  = list(reversed(sorted_chg[-3:]))

        market_close = {}
        for sym, key in [("SPY", "spy"), ("QQQ", "qqq"), ("^VIX", "vix")]:
            try:
                h = get_history(sym, interval="1d", period="5d")
                if not h.empty and len(h) >= 2:
                    c = float(h["Close"].iloc[-1])
                    p = float(h["Close"].iloc[-2])
                    market_close[key] = {"price": round(c, 2), "change_pct": round((c - p) / p * 100, 2)}
                else:
                    market_close[key] = {"price": None, "change_pct": None}
            except Exception:
                market_close[key] = {"price": None, "change_pct": None}

        kz_count = len([a for a in _today_alerts if a.get("date") == today])

        return clean_for_json({
            "date":                    today,
            "top_gainers":             top_gainers,
            "top_losers":              top_losers,
            "summary":                 sorted_chg,
            "market_close":            market_close,
            "killzone_alerts_count":   kz_count,
        })

    except Exception as e:
        return clean_for_json(dict(_empty, error=str(e)))


@router.post("/refresh")
def refresh():
    """Scan complet synchrone : market + Reddit direct + news + scoring + DB.
    Bloque jusqu'à la fin (~30-60s). Retourne {"status": "ok", "duration": X}.
    """
    t0 = time.time()
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # 1. Market
        context = get_market_context()
        scan = scan_watchlist()
        scoring_ctx = _extract_scoring_ctx(context or {})
        ctx_scored = score_market_context(scoring_ctx)

        # 2. Reddit direct (cache_ttl=0 → scan frais, invalide le cache)
        try:
            wl_reddit, _ = scan_reddit_direct(cache_ttl=0)
            reddit_map = _reddit_map_from_direct(wl_reddit)
            active = sum(1 for r in wl_reddit if r.get("mentions", 0) > 0)
            print(f"[API /refresh] Reddit direct : {active}/{len(wl_reddit)} tickers actifs")
        except Exception as e_rd:
            print(f"[API /refresh] Reddit direct erreur : {e_rd} — reddit_map vide")
            reddit_map = {}

        # 3. News
        _, ticker_news, keyword_news, _ = fetch_and_filter(max_per_feed=5)
        news_map = _news_map_from_lists(ticker_news, keyword_news)

        # 4. Scoring
        scored_list = []
        for r in (scan or []):
            if "error" in r:
                continue
            ticker = r["ticker"]
            md = {
                "current_price": r.get("price"),
                "sma200": r.get("sma200"),
                "price_vs_sma200_pct": r.get("dist_sma200"),
                "volume": r.get("vol_today"),
                "relative_volume": r.get("vol_relative"),
            }
            rd = reddit_map.get(ticker, {"mentions": 0, "sentiment": 0.0})
            nd = news_map.get(ticker, {"ticker_matches": 0, "keyword_matches": 0})
            scored_list.append(score_ticker(ticker, md, rd, nd))

        # 5. Sauvegarde DB
        save_scores(today, scored_list)
        save_market_context(today, ctx_scored)

        duration = round(time.time() - t0, 1)
        print(f"[API /refresh] Scan terminé — {len(scored_list)} tickers | {duration}s")
        return {"status": "ok", "duration": duration, "tickers": len(scored_list)}

    except Exception as e:
        duration = round(time.time() - t0, 1)
        print(f"[API /refresh] Erreur : {e}")
        return {"status": "error", "message": str(e), "duration": duration}
