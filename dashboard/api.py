"""
Dashboard API — FastAPI server pour le trading agent.

Lance avec :
    python -m uvicorn dashboard.api:app --reload --port 8000

Endpoints :
    GET  /api/market               — contexte marché scoré
    GET  /api/tickers              — watchlist scorée + classée
    GET  /api/reddit               — données Reddit (lecture fichiers existants)
    GET  /api/news                 — news filtrées avec sentiment
    GET  /api/macro                — calendrier macro du jour
    GET  /api/history              — historique des scores (14j)
    GET  /api/alerts               — alertes killzone intraday
    GET  /api/alerts/news          — nouvelles news depuis le dernier appel
    GET  /api/postmarket           — résumé post-market (top gainers/losers, marché, alertes)
    GET  /api/setups               — setups détectés (DISCOUNT_ZONE, SMA200_BOUNCE, MOMENTUM)
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
)

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Trading Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

        watchlist_set = set(WATCHLIST)

        # ── 5. Construction des lignes ────────────────────────────────────────
        rows = []
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            if not ticker:
                continue
            mentions = int(row.get("Mentions", 0))
            net_sent = int(row.get("Net_Sentiment", 0))
            style = str(row.get("Trade_Style", "?"))
            subreddits = row.get("Subreddits", "")

            # Tendance 5 jours
            td = trends.get(ticker, {
                "mentions_today": mentions,
                "mentions_avg_5d": None,
                "trend": "NEW",
                "trend_pct": None,
            })

            # Vérification ticker : connu statiquement OU confirmé yfinance
            in_wl = ticker in watchlist_set
            known = is_known_ticker(ticker)
            if not known:
                known = verify_ticker(ticker)  # appel yfinance avec cache

            # Cross-validation : Reddit ET news
            cross_validated = ticker in news_tickers

            rows.append({
                "ticker": ticker,
                "mentions": mentions,
                "net_sentiment": net_sent,
                "sentiment_label": "BULL" if net_sent > 0 else "BEAR" if net_sent < 0 else "NEUTRAL",
                "trade_style": style,
                "subreddits": str(subreddits).split(",") if subreddits else [],
                "signals": signals_by_ticker.get(ticker, {}),
                "in_watchlist": in_wl,
                # Nouveaux champs ───────────────────────────────────────────
                "verified": known,
                "cross_validated": cross_validated,
                "trend": td.get("trend", "NEW"),
                "trend_pct": td.get("trend_pct"),
                "mentions_avg_5d": td.get("mentions_avg_5d"),
            })

        # ── 6. Tri : vérifiés + cross-validés en premier, puis mentions desc ─
        def _sort_key(r):
            if r["verified"] and r["cross_validated"]:
                return (0, -r["mentions"])
            if r["verified"]:
                return (1, -r["mentions"])
            return (2, -r["mentions"])

        rows.sort(key=_sort_key)

        return {
            "count": len(rows),
            "data": rows,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "data": []}


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


# ── Setup detector ───────────────────────────────────────────────────────────

@app.get("/api/setups")
def get_setups():
    """Setups détectés sur la watchlist : DISCOUNT_ZONE, SMA200_BOUNCE, MOMENTUM."""
    try:
        import os
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        from analysis.setup_detector import detect_setups, calculate_position_size
        capital = float(os.getenv("CAPITAL", 10000))

        setups = detect_setups()
        enriched = []
        for s in setups:
            pos = calculate_position_size(s["entry"], s["stop"], capital)
            enriched.append({**s, "position": pos})

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
