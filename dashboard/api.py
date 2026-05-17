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
import sys
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from core.cache import cache_get
from analysis.technical_indicators import clean_for_json

DASHBOARD_HTML = Path(__file__).parent / "index.html"
REDDIT_SCANNER = Path(__file__).parent.parent / "RedditScanner" / "main.py"

# ── Imports internes ────────────────────────────────────────────────────────

from config.settings import WATCHLIST
from scrapers.market_data import get_market_context, scan_watchlist
from scrapers.rss_news import fetch_and_filter
from scrapers.macro_calendar import (
    detect_recurring_events, check_earnings_today, get_trading_recommendation,
)
from scrapers.reddit import find_scanner_dir, read_watchlist as read_reddit_csv, is_known_ticker, scan_reddit_direct
from analysis.scoring import score_ticker, score_market_context, rank_tickers
from analysis.reddit_trend import get_reddit_trends, save_today_snapshot, verify_ticker
from database.models import (
    init_db,
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

from dashboard.state import _TEMP_WATCHLIST, _today_alerts, _seen_news_titles


# Initialise la DB au démarrage du serveur
@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print(f"[API] init_db erreur : {e}")



from dashboard.routers.market import router as market_router
app.include_router(market_router, prefix="/api")
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


@app.get("/api/reddit")
def get_reddit():
    """
    Données Reddit enrichies via scan_reddit_direct() (JSON public Reddit).
    Source principale : scrape live des 7 subreddits, cache 30 min.
    Fallback : lecture CSV RedditScanner si le scan direct échoue.
    """
    try:
        # ── Source principale : scan direct Reddit ────────────────────────────
        wl_rows, disc_rows = scan_reddit_direct(cache_ttl=1800)
        meta = cache_get("reddit_direct") or {}

        # ── Fusion buzztickr : ajouter les mentions watchlist depuis buzztickr ─
        from scrapers.reddit import scan_buzztickers, TICKER_BLACKLIST as _BL
        watchlist_set = set(t.upper() for t in WATCHLIST)
        try:
            buzz = scan_buzztickers()
            wl_idx = {r["ticker"]: r for r in wl_rows}
            for br in buzz:
                tk = br["ticker"]
                if tk in _BL or tk not in watchlist_set:
                    continue
                if tk in wl_idx:
                    wl_idx[tk]["mentions"] = wl_idx[tk]["mentions"] + br["mentions"]
                    if "buzztickr" not in wl_idx[tk].get("subreddits", []):
                        wl_idx[tk].setdefault("subreddits", []).append("buzztickr")
        except Exception as e_buzz:
            print(f"[/api/reddit] buzztickr merge erreur : {e_buzz}")

        # ── Ajouter les tickers temporaires manquants ─────────────────────────
        temp_tickers = set(t["ticker"].upper() for t in _TEMP_WATCHLIST.values())
        found_tickers = {r["ticker"] for r in wl_rows}
        for tk in sorted(temp_tickers):
            if tk not in found_tickers:
                wl_rows.append({
                    "ticker": tk, "mentions": 0, "net_sentiment": 0,
                    "sentiment_label": "NEUTRAL", "trade_style": "—",
                    "subreddits": [], "in_watchlist": True, "verified": True,
                    "source": "reddit_direct", "cross_validated": False,
                    "trend": "NEW", "trend_pct": None, "mentions_avg_5d": None,
                    "is_temp": True,
                })

        # Marquer les tickers temporaires
        for r in wl_rows:
            r["is_temp"] = r["ticker"] in temp_tickers

        discoveries_count = len(disc_rows)
        from_cache = meta.get("from_cache", False)
        scanned_at = meta.get("scanned_at", datetime.now().isoformat())

        print(f"[/api/reddit] scan_reddit_direct → "
              f"{sum(1 for r in wl_rows if r.get('mentions', 0) > 0)} actifs, "
              f"{discoveries_count} trouvailles, "
              f"cache={from_cache}")

        return clean_for_json({
            "count":             len(wl_rows),
            "data":              wl_rows,
            "updated_at":        scanned_at,
            "discoveries_count": discoveries_count,
            "source":            "reddit_direct",
            "from_cache":        from_cache,
        })

    except Exception as e:
        print(f"[/api/reddit] reddit_direct échoué : {e} — fallback CSV")
        # ── Fallback CSV RedditScanner ────────────────────────────────────────
        try:
            scanner_dir = find_scanner_dir()
            if scanner_dir is None:
                return {"error": "Scanner Reddit non trouvé", "data": [], "discoveries_count": 0}
            df = read_reddit_csv(scanner_dir)
            if df is None or df.empty:
                return {"error": "Pas de données Reddit (CSV vide)", "data": [], "discoveries_count": 0}

            csv_path      = scanner_dir / "reddit_watchlist.csv"
            snapshots_dir = scanner_dir / "snapshots"
            save_today_snapshot(csv_path, snapshots_dir)
            trends = get_reddit_trends(snapshots_dir)

            news_tickers: set = set()
            try:
                _, ticker_news, _, _ = fetch_and_filter(max_per_feed=3)
                for n in ticker_news:
                    for t in n.get("matched_tickers", []):
                        news_tickers.add(str(t).upper())
            except Exception:
                pass

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

            watchlist_set = set(t.upper() for t in WATCHLIST)
            for t in _TEMP_WATCHLIST.values():
                watchlist_set.add(t["ticker"].upper())

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

            csv_by_ticker: dict = {}
            for _, row in df.iterrows():
                ticker = str(row.get("Ticker", "")).strip().upper()
                if not ticker or ticker not in watchlist_set:
                    continue
                csv_by_ticker[ticker] = row

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
                    style     = str(row.get("Trade_Style", "—"))
                    subs_raw  = row.get("Subreddits", "")
                    subs_list = [s.strip() for s in str(subs_raw).split(",") if s.strip() and str(subs_raw) != "nan"]
                    td = trends.get(ticker, {"trend": "NEW", "trend_pct": None, "mentions_avg_5d": None})
                else:
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
                    "source":          "csv_fallback",
                })

            wl_rows.sort(key=lambda r: -r["mentions"])
            return clean_for_json({
                "count":             len(wl_rows),
                "data":              wl_rows,
                "updated_at":        datetime.now().isoformat(),
                "discoveries_count": discoveries_count,
                "source":            "csv_fallback",
            })
        except Exception as e2:
            return {"error": str(e2), "data": [], "discoveries_count": 0, "source": "error"}


@app.get("/api/reddit/discoveries")
def get_reddit_discoveries_endpoint():
    """
    Tickers hors watchlist détectés via scan_reddit_direct() + r/buzztickr.
    Source : discovery_results de scan_reddit_direct (cache 30 min) + buzztickr fusion.
    """
    try:
        from scrapers.reddit import scan_buzztickers, TICKER_BLACKLIST as _BL
        watchlist_set = set(t.upper() for t in WATCHLIST)

        # ── Source principale : discovery_results du scan direct ──────────────
        _, disc_rows = scan_reddit_direct(cache_ttl=1800)

        # ── Fusion buzztickr (non-watchlist uniquement) ───────────────────────
        try:
            buzz = scan_buzztickers()
            disc_idx = {d["ticker"]: d for d in disc_rows}
            for br in buzz:
                tk = br["ticker"]
                if tk in _BL or tk in watchlist_set:
                    continue
                if tk in disc_idx:
                    disc_idx[tk]["mentions"] += br["mentions"]
                    disc_idx[tk]["source"] = "both"
                else:
                    disc_idx[tk] = {
                        "ticker": tk, "mentions": br["mentions"],
                        "net_sentiment": 0, "sentiment_label": "NEUTRAL",
                        "trade_style": "?", "subreddits": [],
                        "source": "buzztickers", "verified": False,
                        "price": None, "change_pct": None,
                        "dist_sma200": None, "vol_relative": None,
                        "market_cap": None, "market_cap_str": None, "sector": None,
                        "in_watchlist": False,
                    }
            disc_rows = sorted(disc_idx.values(),
                               key=lambda x: (x.get("source") == "both", x.get("mentions", 0)),
                               reverse=True)[:20]
        except Exception as e_buzz:
            print(f"[/api/reddit/discoveries] buzztickr erreur : {e_buzz}")

        # ── Enrichissement léger : price + change_pct via yfinance ───────────
        if _YF_AVAILABLE:
            for d in disc_rows[:10]:
                if d.get("price") is not None:
                    continue
                try:
                    hist = _yf.Ticker(d["ticker"]).history(period="5d", interval="1d")
                    if hist is not None and len(hist) >= 1:
                        d["price"] = round(float(hist["Close"].iloc[-1]), 2)
                        if len(hist) >= 2:
                            pc = float(hist["Close"].iloc[-2])
                            lc = float(hist["Close"].iloc[-1])
                            if pc > 0:
                                d["change_pct"] = round((lc - pc) / pc * 100, 2)
                except Exception:
                    pass

        return clean_for_json({
            "discoveries":   disc_rows,
            "scan_date":     datetime.now().isoformat(),
            "total_scanned": len(disc_rows),
        })
    except Exception as e:
        import traceback
        print(f"[/api/reddit/discoveries] ERREUR: {e}\n{traceback.format_exc()}")
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


# ── Pullback Scanner ─────────────────────────────────────────────────────────

@app.get("/api/indicators/{ticker}")
def get_indicators(ticker: str):
    """Indicateurs techniques complets pour un ticker (RSI, BB, Stoch, ADX, MACD, MAs)."""
    try:
        from analysis.technical_indicators import analyze_ticker
        return clean_for_json(analyze_ticker(ticker.upper()))
    except Exception as e:
        print(f"[API] /api/indicators/{ticker} error: {e}")
        return {"error": str(e), "ticker": ticker}


@app.get("/api/pullbacks")
def get_pullbacks():
    """Scan de survente sur la watchlist (RSI<35, BB%B<0, Stoch<20) + contexte marché."""
    try:
        from analysis.pullback_scanner import scan_pullbacks
        return clean_for_json(scan_pullbacks())
    except Exception as e:
        print(f"[API] /api/pullbacks error: {e}")
        return {"error": str(e), "alerts": [], "watches": [], "no_alerts": []}


@app.get("/api/relative-strength")
def get_relative_strength(period: str = "1m", top: int = 2):
    """Classement alpha vs SPY sur 1w/1m/3m + deep analysis top N."""
    try:
        from analysis.relative_strength import scan_relative_strength
        top = max(1, min(5, top))
        return scan_relative_strength(ranking_period=period, top_n=top)
    except Exception as e:
        print(f"[API] /api/relative-strength error: {e}")
        return {"error": str(e), "ranking": [], "deep_analyses": []}


@app.get("/api/alpha/{ticker}")
def get_alpha(ticker: str):
    """Alpha vs SPY sur 1w/1m/3m pour un ticker."""
    try:
        from analysis.relative_strength import calc_alpha
        return calc_alpha(ticker.upper())
    except Exception as e:
        print(f"[API] /api/alpha/{ticker} error: {e}")
        return {"error": str(e), "ticker": ticker}


@app.get("/api/deep-analysis/{ticker}")
def get_deep_analysis(ticker: str):
    """Analyse technique approfondie + labels narratifs pour un ticker."""
    try:
        from analysis.relative_strength import deep_analysis
        return deep_analysis(ticker.upper())
    except Exception as e:
        print(f"[API] /api/deep-analysis/{ticker} error: {e}")
        return {"error": str(e), "ticker": ticker}


# ── Alertes killzone ──────────────────────────────────────────────────────────




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

@app.get("/api/options/{ticker}")
def get_options(ticker: str):
    """Analyse du flux options (PCR, max pain, unusual activity, smart money) pour un ticker."""
    try:
        from analysis.options_flow import get_options_sentiment
        result = get_options_sentiment(ticker.upper().strip())
        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@app.get("/api/analysis/{ticker}")
def get_smc_analysis(ticker: str):
    """Analyse SMC complète (structure, OBs, FVGs, liquidité, setup) pour un ticker."""
    try:
        from analysis.smc_analyzer import analyze_ticker, format_smc_report
        from analysis.options_flow import get_options_sentiment
        ticker = ticker.upper().strip()
        analysis = analyze_ticker(ticker)
        analysis["report"] = format_smc_report(analysis)
        try:
            analysis["options_data"] = get_options_sentiment(ticker)
        except Exception:
            analysis["options_data"] = {}
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


# ── Propositions de trade ────────────────────────────────────────────────────

@app.get("/api/proposals")
def get_proposals(capital: float = 10000.0):
    """
    Propose jusqu'à 3 trades actionnables basés sur la convergence des signaux.
    Croise : score composite, pullback status, indicateurs techniques.
    Calcule : entrée, SL, TP1 (1:1.5), TP2 (1:2.5), position sizing.
    """
    try:
        from config.settings import WATCHLIST
        from analysis.technical_indicators import analyze_ticker as ti_analyze, clean_for_json as ti_clean
        from analysis.scoring import score_ticker, score_market_context, rank_tickers

        # 1. Contexte marché
        ctx = score_market_context()
        regime = ctx.get("regime", "UNKNOWN")

        if regime == "BEAR":
            return {
                "proposals": [],
                "regime": regime,
                "message": "Régime BEAR — pas de trade LONG recommandé. Attendre un retournement.",
                "generated_at": datetime.now().isoformat(),
            }

        # 2. Scores watchlist
        ticker_scores = []
        for ticker in WATCHLIST:
            try:
                ticker_scores.append(score_ticker(ticker, ctx))
            except Exception:
                continue
        ranked = rank_tickers(ticker_scores)

        # 3. Pullback status (cache 5 min)
        pullback_map: dict = {}
        try:
            from analysis.pullback_scanner import scan_pullbacks
            pb_data = scan_pullbacks()
            for item in pb_data.get("results", []):
                pullback_map[item["ticker"]] = item.get("status", "neutral")
        except Exception:
            pass

        # 4. Score de convergence pour les top 10
        candidates = []
        for t in ranked[:10]:
            base   = float(t.get("total_score") or 0)
            pb     = pullback_map.get(t["ticker"], "neutral")
            bonus  = {"alert": 25, "watch": 12, "neutral": 0, "overbought": -15}.get(pb, 0)
            candidates.append({
                "ticker":      t["ticker"],
                "score":       base,
                "pb_status":   pb,
                "convergence": base + bonus,
                "market":      t.get("market", {}),
            })
        candidates.sort(key=lambda x: x["convergence"], reverse=True)

        # 5. Générer les fiches trade
        proposals = []
        RISK_PCT = 0.01  # 1% du capital par trade

        for cand in candidates:
            if len(proposals) >= 3:
                break
            ticker = cand["ticker"]
            try:
                ind = ti_analyze(ticker)
                if ind.get("error"):
                    continue

                price = float(ind.get("price") or 0)
                if price <= 0:
                    continue

                mas    = ind.get("mas", {})
                sma200 = mas.get("sma200")
                sma20  = mas.get("sma20")

                # SL = sous SMA20 ou 3% stop, le plus proche mais pas plus de 6%
                default_sl = price * 0.97
                sl = max(sma20 * 0.995, default_sl) if (sma20 and sma20 < price) else default_sl
                risk     = price - sl
                risk_pct = risk / price * 100

                if risk_pct < 0.5 or risk_pct > 6.0:
                    continue

                tp1 = round(price + 1.5 * risk, 2)
                tp2 = round(price + 2.5 * risk, 2)

                # Position sizing
                shares        = int((capital * RISK_PCT) / risk) if risk > 0 else 0
                total_risk_usd = round(shares * risk, 2)

                # Étoiles de confiance
                conv  = cand["convergence"]
                stars = 5 if conv >= 85 else 4 if conv >= 70 else 3 if conv >= 55 else 2 if conv >= 40 else 1

                # Explication en français
                reasons = []
                rsi  = ind.get("rsi")
                if rsi and rsi < 40:
                    reasons.append(f"RSI à {round(rsi)} (zone de survente)")
                if sma200 and price > sma200:
                    reasons.append("au-dessus de la SMA200")
                if cand["pb_status"] == "alert":
                    reasons.append("pullback fort (3 signaux)")
                elif cand["pb_status"] == "watch":
                    reasons.append("pullback léger")
                macd = ind.get("macd", {})
                if macd.get("bullish_cross"):
                    reasons.append("MACD en croix haussière")
                adx_val = (ind.get("adx") or {}).get("adx")
                if adx_val and adx_val > 25:
                    reasons.append(f"tendance forte (ADX {round(adx_val)})")
                if not reasons:
                    reasons.append("momentum technique favorable")

                proposals.append(clean_for_json({
                    "ticker":        ticker,
                    "explanation":   ticker + " : " + ", ".join(reasons) + ".",
                    "entry":         round(price, 2),
                    "stop_loss":     round(sl, 2),
                    "tp1":           tp1,
                    "tp2":           tp2,
                    "risk_pct":      round(risk_pct, 1),
                    "rr":            2.5,
                    "shares":         shares,
                    "total_risk_usd": total_risk_usd,
                    "stars":         stars,
                    "score":         round(cand["score"]),
                    "pb_status":     cand["pb_status"],
                    "convergence":   round(cand["convergence"]),
                    "above_sma200":  bool(sma200 and price > sma200),
                    "rules": {
                        "regime_ok":    regime in ("BULL", "NEUTRAL"),
                        "above_sma200": bool(sma200 and price > sma200),
                        "rr_ok":        True,
                    },
                }))
            except Exception as e:
                print(f"[Proposals] Erreur {ticker}: {e}")
                continue

        return clean_for_json({
            "proposals":    proposals,
            "regime":       regime,
            "capital":      capital,
            "generated_at": datetime.now().isoformat(),
        })

    except Exception as e:
        import traceback
        print(f"[Proposals] Erreur: {e}\n{traceback.format_exc()}")
        return {"proposals": [], "error": str(e), "generated_at": datetime.now().isoformat()}


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
    Params optionnels : status (OPEN/CLOSED_WIN/CLOSED_LOSS/CLOSED_BE), limit.
    """
    try:
        trades = get_all_trades(limit=limit, status=status)

        # Compter les trades clôturés (indépendamment du limit)
        total_closed = 0
        try:
            import sqlite3 as _sql3
            from database.models import DB_PATH as _DB
            with _sql3.connect(_DB) as _c:
                _row = _c.execute(
                    "SELECT COUNT(*) FROM trades WHERE status IN ('CLOSED_WIN','CLOSED_LOSS','CLOSED_BE')"
                ).fetchone()
                total_closed = _row[0] if _row else 0
        except Exception:
            pass


        return clean_for_json({
            "count":             len(trades),
            "trades":            trades,
            "total_closed":      total_closed,
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


@app.get("/api/performance/advanced")
def get_performance_advanced():
    """
    Métriques avancées de performance : Sharpe, Sortino, Calmar, Kelly, Monte Carlo.
    Monte Carlo est lent (1-3s) — appelé manuellement depuis le dashboard.
    """
    _empty_adv = {
        "n_trades": 0,
        "sharpe_ratio": None, "sortino_ratio": None, "calmar_ratio": None,
        "expectancy": {}, "kelly_criterion": None, "profit_factor": None,
        "max_consecutive_wins": None, "max_consecutive_losses": None,
        "monte_carlo": None, "r_distribution": {},
        "message": "Pas encore de trades clôturés.",
    }
    try:
        import sqlite3 as _sq
        from analysis.advanced_metrics import calculate_all_advanced_metrics

        with _sq.connect(DB_PATH) as conn:
            conn.row_factory = _sq.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status != 'OPEN' ORDER BY date_close ASC"
            ).fetchall()
        trades = [dict(r) for r in rows]

        if not trades:
            return clean_for_json(_empty_adv)

        result = calculate_all_advanced_metrics(trades)

        # Message explicatif si pas assez de données
        n = result["n_trades"]
        if n < 20:
            result["message"] = (
                f"{n} trade(s) clôturé(s). "
                "Accumule 10+ pour Sharpe/Sortino/Calmar, 20+ pour Monte Carlo."
            )
        else:
            result["message"] = None

        return clean_for_json(result)
    except Exception as e:
        return clean_for_json(dict(_empty_adv, error=str(e)))


# ── Backtesting ───────────────────────────────────────────────────────────────

@app.get("/api/backtest/{ticker}")
def get_backtest_ticker(
    ticker:   str,
    strategy: str = "ALL",
    period:   str = "3y",
):
    """
    Backtest mécanique sur un ticker.
    strategy : DISCOUNT_ZONE | SMA200_BOUNCE | VOLUME_MOMENTUM | ALL
    period   : 1y | 2y | 3y
    Attention : peut prendre 5-30s selon le ticker et la période.
    """
    try:
        from analysis.backtester import backtest_strategy, backtest_all_strategies, STRATEGIES
        ticker = ticker.upper().strip()

        if strategy == "ALL":
            result = backtest_all_strategies(ticker, period=period)
        elif strategy in STRATEGIES:
            result = backtest_strategy(ticker, strategy, period=period)
            # Envelopper dans le même format que ALL pour le dashboard
            result = {
                "ticker": ticker, "period": period,
                "results": {strategy: result},
                "best_strategy": strategy if result["total_trades"] > 0 else None,
                "summary": {
                    strategy: {
                        "total_trades":  result["total_trades"],
                        "winrate":       result["winrate"],
                        "profit_factor": result["profit_factor"],
                        "total_pnl":     result["total_pnl"],
                        "max_drawdown":  result["max_drawdown"],
                        "avg_hold_days": result["avg_hold_days"],
                    }
                },
            }
        else:
            return {"error": f"Stratégie inconnue : {strategy}. Valeurs : {STRATEGIES + ['ALL']}"}

        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@app.get("/api/backtest/report")
def get_backtest_report(period: str = "3y", top_n: int = 10):
    """
    Rapport complet : 3 stratégies × top N tickers (lent : 2-5 min).
    Retourne la meilleure stratégie globale + résultats par ticker.
    """
    try:
        from analysis.backtester import backtest_full_report
        tickers = _top_tickers_from_db_or_watchlist(top_n)
        result  = backtest_full_report(tickers, period=period)
        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e)}


def _top_tickers_from_db_or_watchlist(top_n: int) -> list:
    """Retourne les top N tickers par score DB, fallback sur WATCHLIST[:top_n]."""
    try:
        import sqlite3 as _sq
        with _sq.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT ticker FROM scores_history WHERE date=(SELECT MAX(date) FROM scores_history) ORDER BY total_score DESC LIMIT ?",
                (top_n,),
            ).fetchall()
        tickers = [r[0] for r in rows]
        return tickers if tickers else list(WATCHLIST)[:top_n]
    except Exception:
        return list(WATCHLIST)[:top_n]


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
