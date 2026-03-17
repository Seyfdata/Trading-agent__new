"""
Dashboard API — FastAPI server pour le trading agent.

Lance avec :
    python -m uvicorn dashboard.api:app --reload --port 8000

Endpoints :
    GET  /api/market               — contexte marché scoré
    GET  /api/tickers              — watchlist scorée + classée
    GET  /api/reddit               — données Reddit (lecture fichiers existants)
    GET  /api/reddit/discoveries   — tickers hors watchlist détectés sur Reddit (lent, manuel)
    GET  /api/watchlist/temp       — watchlist temporaire (en mémoire, reset au redémarrage)
    POST /api/watchlist/temp       — ajouter un ticker temporaire {ticker, name, sector}
    DELETE /api/watchlist/temp/{ticker} — retirer un ticker temporaire
    GET  /api/news                 — news filtrées avec sentiment
    GET  /api/macro                — calendrier macro du jour
    GET  /api/history              — historique des scores (14j)
    GET  /api/alerts               — alertes killzone intraday
    GET  /api/alerts/news          — nouvelles news depuis le dernier appel
    GET  /api/postmarket           — résumé post-market (top gainers/losers, marché, alertes)
    GET  /api/setups               — setups détectés (DISCOUNT_ZONE, SMA200_BOUNCE, MOMENTUM)
                                     query: extra_tickers=SOFI,ROKU  (tickers temporaires)
    GET  /api/analysis/{ticker}   — analyse SMC complète pour un ticker
    GET  /api/analysis            — analyse SMC des top 5 tickers de la watchlist
    GET  /api/unified/{ticker}    — score de conviction unifié (setup_detector + SMC)
    GET  /api/unified             — scan unifié des top N tickers
    POST /api/refresh              — lance un scan complet en arrière-plan
    POST /api/trades               — créer un nouveau trade
    GET  /api/trades               — liste tous les trades (params: status, limit)
    GET  /api/trades/{trade_id}    — un trade spécifique
    PUT  /api/trades/{trade_id}/close — clôturer un trade
    DELETE /api/trades/{trade_id}  — supprimer un trade
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    np = None
    _NUMPY = False


def clean_for_json(obj):
    """Convertit les types numpy en types Python natifs pour la sérialisation JSON."""
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_for_json(item) for item in obj]
    if _NUMPY:
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)

DASHBOARD_HTML = Path(__file__).parent / "index.html"
REDDIT_SCANNER = Path(__file__).parent.parent / "RedditScanner" / "main.py"

# ── Imports internes ────────────────────────────────────────────────────────

from config.settings import WATCHLIST
from scrapers.market_data import get_market_context, scan_watchlist
from scrapers.rss_news import fetch_and_filter
from scrapers.macro_calendar import (
    detect_recurring_events, check_earnings_today, get_trading_recommendation,
)
from scrapers.reddit import find_scanner_dir, read_watchlist as read_reddit_csv, is_known_ticker
from analysis.scoring import score_ticker, score_market_context, rank_tickers
from analysis.reddit_trend import get_reddit_trends, save_today_snapshot, verify_ticker
from database.models import (
    init_db, save_scores, save_market_context,
    get_score_history, get_score_trend,
    save_trade, get_all_trades, get_trade_by_id, close_trade, delete_trade,
    get_open_trades, DB_PATH,
)

try:
    import yfinance as _yf
    _YF_AVAILABLE = True
except ImportError:
    _yf = None
    _YF_AVAILABLE = False

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Trading Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Watchlist temporaire (en mémoire, reset au redémarrage) ─────────────────
# {ticker: {ticker, name, sector, added_at, is_temp}}
_TEMP_WATCHLIST: dict = {}


# Initialise la DB au démarrage du serveur
@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print(f"[API] init_db erreur : {e}")


# ── Helpers internes ────────────────────────────────────────────────────────

_BULL_KW = {"surge", "beat", "rise", "growth", "gain", "record", "strong",
            "buy", "positive", "rally", "jump", "upgrade", "outperform"}
_BEAR_KW = {"fall", "drop", "miss", "loss", "decline", "weak", "sell",
            "negative", "crash", "downgrade", "plunge", "slump", "cut"}


def _news_sentiment(title: str, summary: str = "") -> str:
    text = (title + " " + summary).lower()
    bull = sum(1 for w in _BULL_KW if w in text)
    bear = sum(1 for w in _BEAR_KW if w in text)
    if bull > bear:
        return "BULL"
    if bear > bull:
        return "BEAR"
    return "NEUTRAL"


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


def _instrument(context: dict, key: str) -> dict:
    """Extrait {price, change} pour un instrument du market context."""
    info = context.get(key, {})
    if "error" in info or "price" not in info:
        return {"price": None, "change": None}
    return {"price": info["price"], "change": info.get("change_pct")}


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/api/ping")
def ping():
    return {"status": "ok", "message": "API fonctionne"}


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
    try:
        import yfinance as yf
    except ImportError:
        return []

    results = []
    for ind in _MACRO_INDICATORS:
        try:
            tk = yf.Ticker(ind["symbol"])
            hist = tk.history(period="5d", interval="1d", auto_adjust=True)
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


@app.get("/api/market")
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


@app.get("/api/tickers")
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
            # Enrichir avec les données brutes de marché
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


@app.get("/api/reddit")
def get_reddit():
    """
    Données Reddit enrichies :
      - tendance 5 jours (RISING / FALLING / STABLE / NEW)
      - verified    : ticker connu (VALID_TICKERS ou watchlist) ou confirmé yfinance
      - cross_validated : mentionné Reddit + dans les news RSS
    Ne relance pas le scanner — lit les fichiers existants.
    """
    try:
        scanner_dir = find_scanner_dir()
        if scanner_dir is None:
            return {"error": "Scanner Reddit non trouvé", "data": []}

        df = read_reddit_csv(scanner_dir)
        if df is None or df.empty:
            return {"error": "Pas de données Reddit (CSV vide)", "data": []}

        # ── 1. Snapshot journalier ────────────────────────────────────────────
        csv_path = scanner_dir / "reddit_watchlist.csv"
        snapshots_dir = scanner_dir / "snapshots"
        save_today_snapshot(csv_path, snapshots_dir)

        # ── 2. Tendances 5 jours ──────────────────────────────────────────────
        trends = get_reddit_trends(snapshots_dir)

        # ── 3. Tickers news (cross-validation) ───────────────────────────────
        news_tickers: set = set()
        try:
            _, ticker_news, _, _ = fetch_and_filter(max_per_feed=3)
            for n in ticker_news:
                for t in n.get("matched_tickers", []):
                    news_tickers.add(str(t).upper())
        except Exception:
            pass  # non bloquant

        # ── 4. Signaux JSON ───────────────────────────────────────────────────
        signals_by_ticker = {}
        signals_path = scanner_dir / "reddit_sentiment_signals.json"
        if signals_path.exists():
            try:
                with open(signals_path, "r", encoding="utf-8") as f:
                    signals = json.load(f)
                for sig in signals:
                    t = sig.get("ticker", "")
                    if t:
                        signals_by_ticker[t] = sig.get("sentiment_summary", {})
            except Exception:
                pass

        # ── 5. Ensemble autorisé : WATCHLIST + tickers temporaires ──────────────
        # SEULS ces tickers peuvent apparaître dans le tableau principal.
        watchlist_set = set(t.upper() for t in WATCHLIST)
        for t in _TEMP_WATCHLIST.values():
            watchlist_set.add(t["ticker"].upper())

        # Compte rapide des trouvailles potentielles AVANT le filtre strict
        # (tickers hors watchlist vérifiés avec >= 2 mentions dans le CSV)
        discoveries_count = 0
        from scrapers.reddit import TICKER_BLACKLIST as _BL
        for _, row in df.iterrows():
            tk = str(row.get("Ticker", "")).strip().upper()
            if tk and tk not in watchlist_set and tk not in _BL:
                try:
                    ment = int(row.get("Mentions", 0))
                except Exception:
                    ment = 0
                if ment >= 2 and is_known_ticker(tk):
                    discoveries_count += 1

        # ── 6. Construction des lignes — FILTRE STRICT watchlist_set ──────────
        # Toute ligne dont le ticker n'est PAS dans watchlist_set est ignorée.
        csv_by_ticker: dict = {}
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", "")).strip().upper()
            if not ticker or ticker not in watchlist_set:
                continue                                   # ← filtre strict ici
            csv_by_ticker[ticker] = row

        # ── 7. Construire une ligne pour CHACUN des 22 tickers (+ temp) ────────
        wl_rows = []
        for ticker in sorted(watchlist_set):
            row = csv_by_ticker.get(ticker)

            if row is not None:
                try:
                    mentions = int(row.get("Mentions", 0))
                except Exception:
                    mentions = 0
                try:
                    net_sent = int(row.get("Net_Sentiment", 0))
                except Exception:
                    net_sent = 0
                style      = str(row.get("Trade_Style", "—"))
                subreddits = row.get("Subreddits", "")
                subs_list  = [s.strip() for s in str(subreddits).split(",") if s.strip() and str(subreddits) != "nan"]
                td = trends.get(ticker, {"trend": "NEW", "trend_pct": None, "mentions_avg_5d": None})
            else:
                # Ticker de la watchlist absent du CSV → 0 mentions
                mentions, net_sent, style, subs_list = 0, 0, "—", []
                td = {"trend": "NEW", "trend_pct": None, "mentions_avg_5d": None}

            wl_rows.append({
                "ticker":          ticker,
                "mentions":        mentions,
                "net_sentiment":   net_sent,
                "sentiment_label": "BULL" if net_sent > 0 else "BEAR" if net_sent < 0 else "NEUTRAL",
                "trade_style":     style,
                "subreddits":      subs_list,
                "signals":         signals_by_ticker.get(ticker, {}),
                "in_watchlist":    True,
                "verified":        True,
                "cross_validated": ticker in news_tickers,
                "trend":           td.get("trend", "NEW"),
                "trend_pct":       td.get("trend_pct"),
                "mentions_avg_5d": td.get("mentions_avg_5d"),
                "is_temp":         ticker in {t["ticker"].upper() for t in _TEMP_WATCHLIST.values()},
            })

        # Tri : mentions descendantes
        wl_rows.sort(key=lambda r: -r["mentions"])

        return {
            "count":             len(wl_rows),
            "data":              wl_rows,
            "updated_at":        datetime.now().isoformat(),
            "discoveries_count": discoveries_count,
        }
    except Exception as e:
        return {"error": str(e), "data": [], "discoveries_count": 0}


@app.get("/api/reddit/discoveries")
def get_reddit_discoveries_endpoint():
    """
    Scan Reddit pour les tickers hors watchlist (lent ~30-60s, à déclencher manuellement).
    Filtre : VALID_TICKERS ou vérifiés yfinance, market cap > 1B$, >= 3 mentions.
    Enrichit chaque ticker avec dist_sma200 et vol_relative.
    """
    try:
        from scrapers.reddit import get_reddit_discoveries
        discoveries = get_reddit_discoveries()

        # Mini-analyse technique pour chaque trouvaille
        enriched = []
        for d in discoveries:
            ticker = d["ticker"]
            mini   = {"dist_sma200": None, "vol_relative": None}
            if _YF_AVAILABLE:
                try:
                    hist = _yf.Ticker(ticker).history(period="1y", interval="1d")
                    if hist is not None and len(hist) >= 20:
                        avg_vol  = float(hist["Volume"].tail(20).mean())
                        last_vol = float(hist["Volume"].iloc[-1])
                        if avg_vol > 0:
                            mini["vol_relative"] = round(last_vol / avg_vol, 2)
                    if hist is not None and len(hist) >= 200:
                        sma200 = float(hist["Close"].tail(200).mean())
                        last   = float(hist["Close"].iloc[-1])
                        if sma200 > 0:
                            mini["dist_sma200"] = round((last - sma200) / sma200 * 100, 1)
                except Exception:
                    pass
            enriched.append({**d, **mini})

        return clean_for_json({
            "discoveries":   enriched,
            "scan_date":     datetime.now().isoformat(),
            "total_scanned": len(enriched),
        })
    except Exception as e:
        return {"error": str(e), "discoveries": [], "scan_date": datetime.now().isoformat(), "total_scanned": 0}


# ── Watchlist temporaire ──────────────────────────────────────────────────────

@app.get("/api/watchlist/temp")
def get_temp_watchlist():
    """Retourne la watchlist temporaire (tickers ajoutés depuis Reddit discoveries)."""
    return {"tickers": list(_TEMP_WATCHLIST.values()), "count": len(_TEMP_WATCHLIST)}


@app.post("/api/watchlist/temp")
async def add_temp_ticker(request: Request):
    """Ajoute un ticker temporaire. Body JSON : {ticker, name?, sector?}"""
    try:
        body   = await request.json()
        ticker = str(body.get("ticker", "")).upper().strip()
        if not ticker:
            return {"error": "ticker requis"}
        _TEMP_WATCHLIST[ticker] = {
            "ticker":   ticker,
            "name":     body.get("name", ticker),
            "sector":   body.get("sector"),
            "added_at": datetime.now().isoformat(),
            "is_temp":  True,
        }
        return {"success": True, "ticker": ticker}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/watchlist/temp/{ticker}")
def remove_temp_ticker(ticker: str):
    """Retire un ticker de la watchlist temporaire."""
    ticker = ticker.upper().strip()
    if ticker in _TEMP_WATCHLIST:
        del _TEMP_WATCHLIST[ticker]
        return {"success": True}
    return {"success": False, "error": "ticker non trouvé"}


@app.get("/api/news")
def get_news():
    """News filtrées par tickers et mots-clés, avec sentiment BULL/BEAR/NEUTRAL."""
    try:
        all_news, ticker_news, keyword_news, combined = fetch_and_filter(max_per_feed=5)

        def _enrich(news_list, news_type):
            result = []
            for n in news_list:
                result.append({
                    "title": n.get("title", ""),
                    "source": n.get("source", ""),
                    "link": n.get("link", ""),
                    "summary": n.get("summary", "")[:200],
                    "type": news_type,
                    "matched_tickers": n.get("matched_tickers", []),
                    "matched_keywords": n.get("matched_keywords", []),
                    "sentiment": _news_sentiment(
                        n.get("title", ""), n.get("summary", "")
                    ),
                })
            return result

        ticker_titles = {n["title"] for n in ticker_news}
        keyword_only = [n for n in keyword_news if n["title"] not in ticker_titles]

        return {
            "total_fetched": len(all_news),
            "ticker_news": _enrich(ticker_news, "TICKER"),
            "market_news": _enrich(keyword_only, "MACRO"),
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "ticker_news": [], "market_news": []}


@app.get("/api/macro")
def get_macro():
    """Calendrier macro du jour : verdict + events récurrents + earnings."""
    try:
        events = detect_recurring_events()
        earnings = check_earnings_today()
        reco = get_trading_recommendation(events, earnings)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "verdict": reco["verdict"],
            "raison": reco["raison"],
            "risque": reco["risque"],
            "events": [
                {
                    "name": e["name"],
                    "impact": e["impact"],
                    "heure": e["heure"],
                    "regle": e["regle"],
                }
                for e in events
            ],
            "earnings_today": earnings,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "verdict": "INCONNU", "events": [], "earnings_today": []}


@app.get("/api/history")
def get_history(days: int = 14):
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

        # Trier par score le plus récent (desc) et garder top 5
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


# ── Suivi positions temps réel ───────────────────────────────────────────────

@app.get("/api/positions/monitor")
def monitor_positions():
    """
    Suivi temps réel des positions OPEN : prix actuel, PnL latent, alertes.

    Pour chaque position ouverte :
      - current_price         : prix actuel via yfinance.fast_info
      - pnl_latent            : (current - entry) × shares
      - pnl_pct               : % du capital engagé
      - r_current             : R réalisé actuellement
      - distance_target_pct   : % restant jusqu'au target
      - distance_stop_pct     : % de marge avant le stop
      - status_alert          : TARGET_HIT | STOP_HIT | NEAR_TARGET | NEAR_STOP | BREAKEVEN | null

    Retourne {positions, alerts, checked_at, count}.
    """
    if not _YF_AVAILABLE:
        return {"error": "yfinance non installé", "positions": [], "alerts": []}

    try:
        open_trades = get_open_trades()
        if not open_trades:
            return clean_for_json({
                "positions": [], "alerts": [],
                "checked_at": datetime.now().strftime("%H:%M:%S"), "count": 0,
            })

        positions = []
        pos_alerts = []

        for t in open_trades:
            ticker = str(t.get("ticker", "")).strip()
            try:
                entry  = float(t.get("entry_price",  0))
                stop   = float(t.get("stop_price",   0))
                target = float(t.get("target_price", 0))
                shares = int(t.get("shares", 0))

                if not ticker or entry <= 0 or stop <= 0 or entry <= stop:
                    continue

                # ── Prix actuel ──────────────────────────────────────────────
                fi = _yf.Ticker(ticker).fast_info
                current = float(fi.last_price) if fi.last_price else None
                if not current or current <= 0:
                    continue

                # ── Calculs ─────────────────────────────────────────────────
                risk         = entry - stop
                pnl_latent   = round((current - entry) * shares, 2)
                pnl_pct      = round(pnl_latent / (entry * shares) * 100, 2) if entry * shares > 0 else 0.0
                r_current    = round((current - entry) / risk, 2) if risk > 0 else 0.0
                dist_target  = round((target - current) / current * 100, 2) if current > 0 and target > current else 0.0
                dist_stop    = round((current - stop) / current * 100, 2)   if current > 0 else 0.0

                # ── Alerte statut ────────────────────────────────────────────
                status_alert = None
                if current >= target:
                    status_alert = "TARGET_HIT"
                elif current <= stop:
                    status_alert = "STOP_HIT"
                elif 0 < dist_target < 1.5:
                    status_alert = "NEAR_TARGET"
                elif 0 < dist_stop < 1.5:
                    status_alert = "NEAR_STOP"
                elif -0.1 <= r_current <= 0.1:
                    status_alert = "BREAKEVEN"

                pos = {
                    "id":                  t.get("id"),
                    "ticker":              ticker,
                    "entry_price":         entry,
                    "stop_price":          stop,
                    "target_price":        target,
                    "shares":              shares,
                    "current_price":       round(current, 2),
                    "pnl_latent":          pnl_latent,
                    "pnl_pct":             pnl_pct,
                    "r_current":           r_current,
                    "distance_target_pct": dist_target,
                    "distance_stop_pct":   dist_stop,
                    "status_alert":        status_alert,
                }
                positions.append(pos)

                # ── Alerte push si statut critique ───────────────────────────
                if status_alert and status_alert != "BREAKEVEN":
                    severity  = "HIGH" if status_alert in ("TARGET_HIT", "STOP_HIT") else "MEDIUM"
                    pnl_str   = ("+" if pnl_latent >= 0 else "") + f"${pnl_latent:.0f}"
                    r_str     = ("+" if r_current  >= 0 else "") + f"{r_current:.1f}R"

                    _msgs = {
                        "TARGET_HIT":  f"Target atteint à ${current:.2f} ({r_str}, {pnl_str})",
                        "STOP_HIT":    f"Stop touché à ${current:.2f} ({r_str}, {pnl_str})",
                        "NEAR_TARGET": f"Proche du target ${target:.2f} — dist {dist_target:.1f}% ({r_str})",
                        "NEAR_STOP":   f"Proche du stop ${stop:.2f} — dist {dist_stop:.1f}%",
                    }
                    pos_alerts.append({
                        "ticker":       ticker,
                        "severity":     severity,
                        "status_alert": status_alert,
                        "message":      _msgs.get(status_alert, ""),
                        "timestamp":    datetime.now().strftime("%H:%M:%S"),
                    })

            except Exception as ex:
                print(f"[positions/monitor] {ticker} : {ex}")
                continue

        return clean_for_json({
            "positions":  positions,
            "alerts":     pos_alerts,
            "checked_at": datetime.now().strftime("%H:%M:%S"),
            "count":      len(positions),
        })

    except Exception as e:
        return {"error": str(e), "positions": [], "alerts": []}


# ── Refresh (scan complet synchrone) ─────────────────────────────────────────

@app.post("/api/refresh")
def refresh():
    """Scan complet synchrone : market + Reddit subprocess + news + scoring + DB.
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

        # 2. Reddit subprocess (lance un vrai scan frais)
        if REDDIT_SCANNER.exists():
            try:
                subprocess.run(
                    [sys.executable, str(REDDIT_SCANNER),
                     "--refresh", "--cache-ttl", "1800", "--prefer-new"],
                    capture_output=True, text=True, timeout=90,
                )
            except subprocess.TimeoutExpired:
                print("[API /refresh] Reddit scanner timeout (>90s)")
            except Exception as e:
                print(f"[API /refresh] Reddit scanner erreur : {e}")
        else:
            print(f"[API /refresh] RedditScanner introuvable : {REDDIT_SCANNER}")

        # 3. News
        _, ticker_news, keyword_news, _ = fetch_and_filter(max_per_feed=5)
        news_map = _news_map_from_lists(ticker_news, keyword_news)

        # 4. Reddit map depuis le CSV mis à jour par le subprocess
        scanner_dir = find_scanner_dir()
        reddit_map = _reddit_map_from_csv(scanner_dir)

        # 5. Scoring
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

        # 6. Sauvegarde DB
        save_scores(today, scored_list)
        save_market_context(today, ctx_scored)

        duration = round(time.time() - t0, 1)
        print(f"[API /refresh] Scan termine — {len(scored_list)} tickers | {duration}s")
        return {"status": "ok", "duration": duration, "tickers": len(scored_list)}

    except Exception as e:
        duration = round(time.time() - t0, 1)
        print(f"[API /refresh] Erreur : {e}")
        return {"status": "error", "message": str(e), "duration": duration}


# ── Alertes killzone ──────────────────────────────────────────────────────────

# Set en mémoire pour dédupliquer les news déjà vues
_seen_news_titles: set = set()

# Alertes déclenchées pendant la killzone du jour courant (dédupliquées type+ticker)
_today_alerts: list = []


def _is_killzone() -> bool:
    """True si on est lundi-vendredi entre 14h30 et 16h30 CET (UTC+1/UTC+2)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    now = datetime.now(ZoneInfo("Europe/Paris"))
    if now.weekday() >= 5:       # samedi=5, dimanche=6
        return False
    minutes = now.hour * 60 + now.minute
    return 14 * 60 + 30 <= minutes <= 16 * 60 + 30


def _next_killzone_str() -> str:
    """Retourne l'heure de la prochaine killzone sous forme lisible."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    now = datetime.now(ZoneInfo("Europe/Paris"))
    minutes = now.hour * 60 + now.minute
    # Aujourd'hui si pas encore passée
    if now.weekday() < 5 and minutes < 14 * 60 + 30:
        return "aujourd'hui 14h30 CET"
    # Trouver le prochain jour ouvré
    days_ahead = 1
    while True:
        candidate = (now.weekday() + days_ahead) % 7
        if candidate < 5:
            label = "demain" if days_ahead == 1 else ["lun", "mar", "mer", "jeu", "ven"][candidate]
            return f"{label} 14h30 CET"
        days_ahead += 1


def _scan_alerts() -> list:
    """Scanne la watchlist intraday et génère les alertes."""
    try:
        import yfinance as yf
    except ImportError:
        return []

    alerts = []
    now_str = datetime.now().strftime("%H:%M:%S")

    for ticker in WATCHLIST:
        try:
            tk = yf.Ticker(ticker)
            # Données courantes via fast_info
            fi = tk.fast_info
            current_price  = float(fi.last_price)    if fi.last_price  else None
            prev_close     = float(fi.previous_close) if fi.previous_close else None
            day_high       = float(fi.day_high)       if fi.day_high    else None
            day_low        = float(fi.day_low)        if fi.day_low     else None
            volume_today   = int(fi.three_month_average_volume * 0 + (fi.shares or 0)) if hasattr(fi, 'shares') else None

            # Historique 20j pour SMA200 et volume moyen
            hist = tk.history(period="60d", interval="1d", auto_adjust=True)
            if hist.empty or current_price is None:
                continue

            sma200_series = tk.history(period="1y", interval="1d", auto_adjust=True)["Close"].rolling(200).mean()
            sma200 = float(sma200_series.dropna().iloc[-1]) if len(sma200_series.dropna()) > 0 else None

            avg_vol_20 = float(hist["Volume"].tail(20).mean()) if len(hist) >= 20 else None
            vol_today  = float(hist["Volume"].iloc[-1]) if len(hist) > 0 else None

            # Variation intraday
            if prev_close and current_price:
                chg_pct = (current_price - prev_close) / prev_close * 100
            elif len(hist) >= 2:
                chg_pct = (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[-2])) / float(hist["Close"].iloc[-2]) * 100
            else:
                chg_pct = None

            # ── Alerte 1 : Volume Breakout ──────────────────────────────────
            if vol_today and avg_vol_20 and avg_vol_20 > 0:
                ratio = vol_today / avg_vol_20
                if ratio >= 2.0:
                    severity = "HIGH" if ratio >= 3.0 else "MEDIUM"
                    alerts.append({
                        "type": "VOLUME",
                        "ticker": ticker,
                        "message": f"🔥 {ticker} volume ×{ratio:.1f} — activité institutionnelle",
                        "severity": severity,
                        "timestamp": now_str,
                        "details": {"vol_today": round(vol_today), "avg_vol_20": round(avg_vol_20), "ratio": round(ratio, 2)},
                    })

            # ── Alerte 2 : Approche SMA200 ──────────────────────────────────
            if sma200 and current_price and sma200 > 0:
                dist_pct = (current_price - sma200) / sma200 * 100
                if abs(dist_pct) <= 1.5:
                    severity = "HIGH" if abs(dist_pct) <= 0.5 else "MEDIUM"
                    direction = "approche SMA200" if dist_pct > 0 else "test SMA200 par en-dessous"
                    alerts.append({
                        "type": "SMA200",
                        "ticker": ticker,
                        "message": f"📍 {ticker} {direction} ({current_price:.2f} → SMA: {sma200:.2f}, dist: {dist_pct:+.1f}%)",
                        "severity": severity,
                        "timestamp": now_str,
                        "details": {"price": round(current_price, 2), "sma200": round(sma200, 2), "dist_pct": round(dist_pct, 2)},
                    })

            # ── Alerte 3 : Mouvement fort ───────────────────────────────────
            if chg_pct is not None and abs(chg_pct) >= 3.0:
                severity = "HIGH" if abs(chg_pct) >= 5.0 else "MEDIUM"
                icon = "🚀" if chg_pct > 0 else "⚠️"
                sign = "+" if chg_pct > 0 else ""
                alerts.append({
                    "type": "MOVE",
                    "ticker": ticker,
                    "message": f"{icon} {ticker} {sign}{chg_pct:.1f}% intraday",
                    "severity": severity,
                    "timestamp": now_str,
                    "details": {"change_pct": round(chg_pct, 2), "price": round(current_price, 2) if current_price else None},
                })

        except Exception:
            continue

    # Trier : HIGH en premier, puis MEDIUM, puis LOW
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 2))
    return alerts


@app.get("/api/alerts")
def get_alerts(force: bool = False):
    """Alertes killzone intraday : volume breakout, approche SMA200, mouvement fort.
    Paramètre optionnel : force=true pour ignorer la vérification d'horaire (test mode).
    """
    try:
        in_kz = force or _is_killzone()
        scanned_at = datetime.now().strftime("%H:%M:%S")

        if not in_kz:
            return clean_for_json({
                "in_killzone": False,
                "test_mode": False,
                "alerts": [],
                "next_killzone": _next_killzone_str(),
                "scanned_at": scanned_at,
            })

        alerts = _scan_alerts()
        # Enregistrer les nouvelles alertes du jour (dédupliquées par type+ticker)
        _alert_date = datetime.now().strftime("%Y-%m-%d")
        _seen_keys = {(a.get("type"), a.get("ticker")) for a in _today_alerts}
        for _a in alerts:
            _k = (_a.get("type"), _a.get("ticker"))
            if _k not in _seen_keys:
                _today_alerts.append({"date": _alert_date, "type": _a.get("type"), "ticker": _a.get("ticker")})
                _seen_keys.add(_k)
        return clean_for_json({
            "in_killzone": True,
            "test_mode": bool(force),
            "alerts": alerts,
            "next_killzone": _next_killzone_str(),
            "scanned_at": scanned_at,
        })
    except Exception as e:
        return clean_for_json({
            "in_killzone": False,
            "test_mode": False,
            "alerts": [],
            "next_killzone": "erreur",
            "scanned_at": datetime.now().strftime("%H:%M:%S"),
            "error": str(e),
        })


@app.get("/api/alerts/news")
def get_alerts_news():
    """Retourne uniquement les nouvelles news depuis le dernier appel (déduplication en mémoire)."""
    global _seen_news_titles
    try:
        all_news, ticker_news, keyword_news, _ = fetch_and_filter(max_per_feed=5)
        combined = ticker_news + [n for n in keyword_news if n.get("title") not in {x["title"] for x in ticker_news}]
        fetched_at = datetime.now().isoformat()
        new_news = []
        for n in combined:
            title = n.get("title", "")
            if title and title not in _seen_news_titles:
                _seen_news_titles.add(title)
                new_news.append({
                    "title": title,
                    "source": n.get("source", ""),
                    "link": n.get("link", ""),
                    "summary": n.get("summary", "")[:200],
                    "matched_tickers": n.get("matched_tickers", []),
                    "sentiment": _news_sentiment(title, n.get("summary", "")),
                    "fetched_at": fetched_at,
                })
        return {"new_news": new_news, "total_checked": len(combined)}
    except Exception as e:
        return {"new_news": [], "total_checked": 0, "error": str(e)}


# ── SMC Analysis ─────────────────────────────────────────────────────────────

@app.get("/api/analysis/{ticker}")
def get_smc_analysis(ticker: str):
    """Analyse SMC complète (structure, OBs, FVGs, liquidité, setup) pour un ticker."""
    try:
        from analysis.smc_analyzer import analyze_ticker, format_smc_report
        ticker = ticker.upper().strip()
        analysis = analyze_ticker(ticker)
        analysis["report"] = format_smc_report(analysis)
        return clean_for_json(analysis)
    except Exception as e:
        return {"error": str(e), "ticker": ticker, "mode": "DEMO"}


@app.get("/api/analysis")
def get_smc_analysis_watchlist():
    """Analyse SMC des top 5 tickers de la watchlist (peut prendre ~30s)."""
    try:
        from analysis.smc_analyzer import analyze_ticker, format_smc_report

        # Essayer de récupérer les tickers les mieux classés depuis la DB
        try:
            from database.models import get_score_history
            rows = get_score_history(limit=5)
            top_tickers = [r["ticker"] for r in rows[:5]] if rows else WATCHLIST[:5]
        except Exception:
            top_tickers = WATCHLIST[:5]

        results = []
        for t in top_tickers:
            a = analyze_ticker(t)
            a["report"] = format_smc_report(a)
            results.append(clean_for_json(a))

        return clean_for_json({
            "count":       len(results),
            "analyses":    results,
            "analyzed_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return {"error": str(e), "analyses": [], "count": 0}


# ── Unified Scorer ────────────────────────────────────────────────────────────

@app.get("/api/unified/{ticker}")
def get_unified(ticker: str):
    """Score de conviction unifié (setup_detector × SMC) pour un ticker."""
    try:
        from analysis.unified_scorer import unified_analysis
        result = unified_analysis(ticker.upper().strip())
        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e), "ticker": ticker, "unified_score": 0, "grade": "NO TRADE"}


@app.get("/api/unified")
def get_unified_scan(top_n: int = 5):
    """Scan unifié sur les top N tickers (trié par unified_score)."""
    try:
        from analysis.unified_scorer import scan_unified
        results = scan_unified(top_n=top_n)
        return clean_for_json({
            "count":       len(results),
            "analyses":    results,
            "scanned_at":  datetime.now().isoformat(),
        })
    except Exception as e:
        return {"error": str(e), "analyses": [], "count": 0}


# ── Setup detector ───────────────────────────────────────────────────────────

@app.get("/api/setups")
def get_setups(extra_tickers: str = ""):
    """
    Setups détectés sur la watchlist : DISCOUNT_ZONE, SMA200_BOUNCE, MOMENTUM.
    query param extra_tickers : tickers supplémentaires séparés par virgule (ex: SOFI,ROKU).
    Les setups des extra_tickers portent is_discovery=True.
    """
    try:
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        from analysis.setup_detector import detect_setups, calculate_position_size
        capital = float(os.getenv("CAPITAL", 10000))

        extras     = [t.strip().upper() for t in extra_tickers.split(",") if t.strip()] if extra_tickers else []
        extras_set = set(extras)
        wl_set     = set(WATCHLIST)
        combined   = list(WATCHLIST) + [t for t in extras if t not in wl_set]

        setups   = detect_setups(combined if extras else None)
        enriched = []
        for s in setups:
            pos = calculate_position_size(s["entry"], s["stop"], capital)
            enriched.append({**s, "position": pos, "is_discovery": s["ticker"] in extras_set})

        return clean_for_json({
            "count":      len(enriched),
            "setups":     enriched,
            "capital":    capital,
            "scanned_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return clean_for_json({
            "count": 0, "setups": [], "capital": 0,
            "scanned_at": datetime.now().isoformat(),
            "error": str(e),
        })


# ── Post-market summary ───────────────────────────────────────────────────────

@app.get("/api/postmarket")
def get_postmarket():
    """Résumé post-market : top 3 gainers/losers, volume, alertes killzone du jour."""
    today = datetime.now().strftime("%Y-%m-%d")
    _empty = {
        "date": today,
        "top_gainers": [], "top_losers": [], "summary": [],
        "market_close": {}, "killzone_alerts_count": 0,
    }
    try:
        import yfinance as yf
    except ImportError:
        return clean_for_json(dict(_empty, error="yfinance non installé"))

    try:
        results = []
        for ticker in WATCHLIST:
            try:
                tk   = yf.Ticker(ticker)
                hist = tk.history(period="30d", interval="1d", auto_adjust=True)
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

        # SPY / QQQ / VIX close
        market_close = {}
        for sym, key in [("SPY", "spy"), ("QQQ", "qqq"), ("^VIX", "vix")]:
            try:
                h = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
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


# ── Journal de trading ────────────────────────────────────────────────────────

@app.post("/api/trades")
async def create_trade(request: Request):
    """Crée un nouveau trade OPEN.
    Body JSON requis : ticker, entry_price, stop_price, target_price, shares.
    Optionnels : setup_type, direction, notes, score_at_entry, market_regime.
    """
    try:
        body = await request.json()
        required = ("ticker", "entry_price", "stop_price", "target_price", "shares")
        missing = [f for f in required if f not in body]
        if missing:
            return {"error": f"Champs manquants : {', '.join(missing)}"}
        trade_id = save_trade(body)
        trade = get_trade_by_id(trade_id)
        return clean_for_json({"id": trade_id, "trade": trade})
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/trades")
def list_trades(status: str = None, limit: int = 100):
    """Liste tous les trades triés par date décroissante.
    Params optionnels : status (OPEN/CLOSED_WIN/CLOSED_LOSS/CLOSED_BE), limit.
    """
    try:
        trades = get_all_trades(limit=limit, status=status)
        return clean_for_json({
            "count": len(trades),
            "trades": trades,
        })
    except Exception as e:
        return {"error": str(e), "trades": []}


@app.get("/api/trades/{trade_id}")
def get_trade(trade_id: int):
    """Retourne un trade par son id."""
    try:
        trade = get_trade_by_id(trade_id)
        if trade is None:
            return {"error": f"Trade {trade_id} introuvable"}
        return clean_for_json({"trade": trade})
    except Exception as e:
        return {"error": str(e)}


@app.put("/api/trades/{trade_id}/close")
async def close_trade_endpoint(trade_id: int, request: Request):
    """Clôture un trade et calcule automatiquement PnL, R:R réalisé et statut.
    Body JSON requis : close_price.
    Optionnel : notes.
    """
    try:
        body = await request.json()
        if "close_price" not in body:
            return {"error": "close_price requis"}
        trade = close_trade(trade_id, float(body["close_price"]), body.get("notes"))
        if trade is None:
            return {"error": f"Trade {trade_id} introuvable"}
        return clean_for_json({"trade": trade})
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/trades/{trade_id}")
def delete_trade_endpoint(trade_id: int):
    """Supprime un trade définitivement."""
    try:
        ok = delete_trade(trade_id)
        if not ok:
            return {"error": f"Trade {trade_id} introuvable"}
        return {"deleted": True, "id": trade_id}
    except Exception as e:
        return {"error": str(e)}


# ── Performance analytics ──────────────────────────────────────────────────────

@app.get("/api/performance")
def get_performance():
    """Stats de performance complètes sur tous les trades clôturés."""
    _empty = {
        "total_trades": 0, "wins": 0, "losses": 0, "be": 0,
        "winrate": 0, "profit_factor": None, "expectancy": 0,
        "max_drawdown": 0, "total_pnl": 0, "avg_rr_realized": None,
        "best_trade": None, "worst_trade": None,
        "equity_curve": [], "monthly_returns": [], "drawdown_curve": [],
        "by_ticker": [], "by_setup": [], "by_regime": [],
    }
    try:
        import sqlite3 as _sq
        with _sq.connect(DB_PATH) as conn:
            conn.row_factory = _sq.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status != 'OPEN' ORDER BY date_close ASC"
            ).fetchall()
        trades = [dict(r) for r in rows]

        if not trades:
            return clean_for_json(_empty)

        wins   = [t for t in trades if t["status"] == "CLOSED_WIN"]
        losses = [t for t in trades if t["status"] == "CLOSED_LOSS"]
        be     = [t for t in trades if t["status"] == "CLOSED_BE"]

        total_pnl     = sum(t["pnl_dollars"] or 0 for t in trades)
        gross_win     = sum(t["pnl_dollars"] or 0 for t in wins)
        gross_loss    = abs(sum(t["pnl_dollars"] or 0 for t in losses))
        winrate       = round(len(wins) / len(trades) * 100, 1)
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
        expectancy    = round(total_pnl / len(trades), 2)

        rr_vals  = [t["rr_realized"] for t in trades if t.get("rr_realized") is not None]
        avg_rr   = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None

        by_pnl      = sorted(trades, key=lambda t: t["pnl_dollars"] or 0)
        best_trade  = {"ticker": by_pnl[-1]["ticker"], "pnl": by_pnl[-1]["pnl_dollars"], "date": (by_pnl[-1]["date_close"] or "")[:10]} if by_pnl else None
        worst_trade = {"ticker": by_pnl[0]["ticker"],  "pnl": by_pnl[0]["pnl_dollars"],  "date": (by_pnl[0]["date_close"] or "")[:10]}  if by_pnl else None

        # Equity curve + drawdown curve (chronological)
        cum = 0.0
        peak = 0.0
        equity_curve   = []
        drawdown_curve = []
        for t in trades:
            cum  += t["pnl_dollars"] or 0
            date  = (t["date_close"] or t["date_open"] or "")[:10]
            equity_curve.append({"date": date, "pnl": round(cum, 2)})
            peak  = max(peak, cum)
            drawdown_curve.append({"date": date, "drawdown": round(cum - peak, 2)})

        max_drawdown = min((d["drawdown"] for d in drawdown_curve), default=0)

        # Monthly returns
        monthly: dict = {}
        for t in trades:
            date  = (t["date_close"] or t["date_open"] or "")[:10]
            month = date[:7]
            if month not in monthly:
                monthly[month] = {"month": month, "pnl": 0.0, "trades": 0, "wins": 0}
            monthly[month]["pnl"]    += t["pnl_dollars"] or 0
            monthly[month]["trades"] += 1
            if t["status"] == "CLOSED_WIN":
                monthly[month]["wins"] += 1
        monthly_returns = []
        for v in sorted(monthly.values(), key=lambda x: x["month"]):
            monthly_returns.append({
                "month":   v["month"],
                "pnl":     round(v["pnl"], 2),
                "trades":  v["trades"],
                "winrate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0,
            })

        # By ticker
        def _group(trades_list, key_fn, val_fn):
            m: dict = {}
            for t in trades_list:
                k = key_fn(t)
                if k not in m:
                    m[k] = {"_wins": 0, "_trades": 0, "_pnl": 0.0, "_gw": 0.0, "_gl": 0.0, "_rr": [], "_key": k}
                m[k]["_trades"] += 1
                m[k]["_pnl"]    += t["pnl_dollars"] or 0
                pnl = t["pnl_dollars"] or 0
                if pnl > 0: m[k]["_gw"] += pnl
                else:       m[k]["_gl"] += abs(pnl)
                if t["status"] == "CLOSED_WIN": m[k]["_wins"] += 1
                if t.get("rr_realized") is not None: m[k]["_rr"].append(t["rr_realized"])
            return {k: val_fn(v) for k, v in m.items()}

        tk_map = _group(
            trades,
            lambda t: t["ticker"],
            lambda v: {
                "ticker":  v["_key"],
                "trades":  v["_trades"],
                "winrate": round(v["_wins"] / v["_trades"] * 100, 1),
                "pnl":     round(v["_pnl"], 2),
                "avg_rr":  round(sum(v["_rr"]) / len(v["_rr"]), 2) if v["_rr"] else None,
            }
        )
        by_ticker = sorted(tk_map.values(), key=lambda x: x["pnl"], reverse=True)

        st_map = _group(
            trades,
            lambda t: t.get("setup_type") or "MANUAL",
            lambda v: {
                "type":          v["_key"],
                "trades":        v["_trades"],
                "winrate":       round(v["_wins"] / v["_trades"] * 100, 1),
                "pnl":           round(v["_pnl"], 2),
                "profit_factor": round(v["_gw"] / v["_gl"], 2) if v["_gl"] > 0 else None,
            }
        )
        by_setup = sorted(st_map.values(), key=lambda x: x["pnl"], reverse=True)

        rg_map = _group(
            trades,
            lambda t: t.get("market_regime") or "N/A",
            lambda v: {
                "regime":  v["_key"],
                "trades":  v["_trades"],
                "winrate": round(v["_wins"] / v["_trades"] * 100, 1),
                "pnl":     round(v["_pnl"], 2),
            }
        )
        by_regime = sorted(rg_map.values(), key=lambda x: x["pnl"], reverse=True)

        return clean_for_json({
            "total_trades":    len(trades),
            "wins":            len(wins),
            "losses":          len(losses),
            "be":              len(be),
            "winrate":         winrate,
            "profit_factor":   profit_factor,
            "expectancy":      expectancy,
            "max_drawdown":    round(max_drawdown, 2),
            "total_pnl":       round(total_pnl, 2),
            "avg_rr_realized": avg_rr,
            "best_trade":      best_trade,
            "worst_trade":     worst_trade,
            "equity_curve":    equity_curve,
            "monthly_returns": monthly_returns,
            "drawdown_curve":  drawdown_curve,
            "by_ticker":       by_ticker,
            "by_setup":        by_setup,
            "by_regime":       by_regime,
        })
    except Exception as e:
        return clean_for_json(dict(_empty, error=str(e)))


# ── Test pages ────────────────────────────────────────────────────────────────

@app.get("/journal-test", response_class=HTMLResponse)
def serve_journal_test():
    """Page de test isolée pour le composant JournalTab."""
    p = Path(__file__).parent / "journal_test.html"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return HTMLResponse("<h1>journal_test.html introuvable</h1>", status_code=404)


@app.get("/test", response_class=HTMLResponse)
def serve_test():
    """Page de test React minimale."""
    test_path = Path(__file__).parent / "test.html"
    return test_path.read_text(encoding="utf-8")


# ── Dashboard HTML ────────────────────────────────────────────────────────────

@app.get("/dashboard")
def serve_dashboard(response: Response):
    """Sert le fichier dashboard/index.html avec headers no-cache."""
    if DASHBOARD_HTML.exists():
        content = DASHBOARD_HTML.read_text(encoding="utf-8")
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"error": f"Dashboard introuvable : {DASHBOARD_HTML}"}


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "Trading Agent API",
        "version": "1.0.0",
        "dashboard": "http://localhost:8000/dashboard",
        "docs":      "http://localhost:8000/docs",
        "endpoints": [
            "GET  /dashboard",
            "GET  /api/market",
            "GET  /api/tickers",
            "GET  /api/reddit",
            "GET  /api/news",
            "GET  /api/macro",
            "GET  /api/history",
            "POST /api/refresh",
            "GET  /api/postmarket",
            "GET  /api/setups",
            "POST /api/trades",
            "GET  /api/trades",
            "GET  /api/trades/{id}",
            "PUT  /api/trades/{id}/close",
            "DELETE /api/trades/{id}",
        ],
    }
