"""
Router: social, news, macro, positions, alerts.
Couvre: reddit, reddit/discoveries, watchlist/temp (x3),
        news, macro, positions/monitor, alerts, alerts/news.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Request

from config.settings import WATCHLIST
from scrapers.rss_news import fetch_and_filter
from scrapers.macro_calendar import (
    detect_recurring_events, check_earnings_today, get_trading_recommendation,
)
from scrapers.reddit import (
    find_scanner_dir, read_watchlist as read_reddit_csv,
    is_known_ticker, scan_reddit_direct,
)
from analysis.reddit_trend import get_reddit_trends, save_today_snapshot
from core.data_provider import get_history, get_fast_info
from analysis.technical_indicators import clean_for_json
from database.models import get_open_trades
from dashboard.state import _TEMP_WATCHLIST, _today_alerts, _seen_news_titles

try:
    import yfinance as _yf  # noqa: F401
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

router = APIRouter()

# ── Sentiment helpers ─────────────────────────────────────────────────────────

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


# ── Killzone helpers ──────────────────────────────────────────────────────────

def _is_killzone() -> bool:
    """True si on est lundi-vendredi entre 14h30 et 16h30 CET."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    now = datetime.now(ZoneInfo("Europe/Paris"))
    if now.weekday() >= 5:
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
    if now.weekday() < 5 and minutes < 14 * 60 + 30:
        return "aujourd'hui 14h30 CET"
    days_ahead = 1
    while True:
        candidate = (now.weekday() + days_ahead) % 7
        if candidate < 5:
            label = "demain" if days_ahead == 1 else ["lun", "mar", "mer", "jeu", "ven"][candidate]
            return f"{label} 14h30 CET"
        days_ahead += 1


def _scan_alerts() -> list:
    """Scanne la watchlist intraday et génère les alertes."""
    alerts = []
    now_str = datetime.now().strftime("%H:%M:%S")

    for ticker in WATCHLIST:
        try:
            fi = get_fast_info(ticker)
            current_price = float(fi.last_price)    if fi and fi.last_price    else None
            prev_close    = float(fi.previous_close) if fi and fi.previous_close else None

            hist = get_history(ticker, interval="1d", period="60d")
            if hist.empty or current_price is None:
                continue

            hist_1y = get_history(ticker, interval="1d", period="1y")
            sma200_series = hist_1y["Close"].rolling(200).mean() if not hist_1y.empty else None
            sma200 = float(sma200_series.dropna().iloc[-1]) if sma200_series is not None and len(sma200_series.dropna()) > 0 else None

            avg_vol_20 = float(hist["Volume"].tail(20).mean()) if len(hist) >= 20 else None
            vol_today  = float(hist["Volume"].iloc[-1]) if len(hist) > 0 else None

            if prev_close and current_price:
                chg_pct = (current_price - prev_close) / prev_close * 100
            elif len(hist) >= 2:
                chg_pct = (float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[-2])) / float(hist["Close"].iloc[-2]) * 100
            else:
                chg_pct = None

            if vol_today and avg_vol_20 and avg_vol_20 > 0:
                ratio = vol_today / avg_vol_20
                if ratio >= 2.0:
                    severity = "HIGH" if ratio >= 3.0 else "MEDIUM"
                    alerts.append({
                        "type": "VOLUME", "ticker": ticker,
                        "message": f"🔥 {ticker} volume ×{ratio:.1f} — activité institutionnelle",
                        "severity": severity, "timestamp": now_str,
                        "details": {"vol_today": round(vol_today), "avg_vol_20": round(avg_vol_20), "ratio": round(ratio, 2)},
                    })

            if sma200 and current_price and sma200 > 0:
                dist_pct = (current_price - sma200) / sma200 * 100
                if abs(dist_pct) <= 1.5:
                    severity = "HIGH" if abs(dist_pct) <= 0.5 else "MEDIUM"
                    direction = "approche SMA200" if dist_pct > 0 else "test SMA200 par en-dessous"
                    alerts.append({
                        "type": "SMA200", "ticker": ticker,
                        "message": f"📍 {ticker} {direction} ({current_price:.2f} → SMA: {sma200:.2f}, dist: {dist_pct:+.1f}%)",
                        "severity": severity, "timestamp": now_str,
                        "details": {"price": round(current_price, 2), "sma200": round(sma200, 2), "dist_pct": round(dist_pct, 2)},
                    })

            if chg_pct is not None and abs(chg_pct) >= 3.0:
                severity = "HIGH" if abs(chg_pct) >= 5.0 else "MEDIUM"
                icon = "🚀" if chg_pct > 0 else "⚠️"
                sign = "+" if chg_pct > 0 else ""
                alerts.append({
                    "type": "MOVE", "ticker": ticker,
                    "message": f"{icon} {ticker} {sign}{chg_pct:.1f}% intraday",
                    "severity": severity, "timestamp": now_str,
                    "details": {"change_pct": round(chg_pct, 2), "price": round(current_price, 2) if current_price else None},
                })

        except Exception:
            continue

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 2))
    return alerts


# ── Endpoints Reddit ──────────────────────────────────────────────────────────

@router.get("/reddit")
def get_reddit():
    """
    Données Reddit enrichies via scan_reddit_direct() (JSON public Reddit).
    Source principale : scrape live des 7 subreddits, cache 30 min.
    Fallback : lecture CSV RedditScanner si le scan direct échoue.
    """
    from core.cache import cache_get
    try:
        wl_rows, disc_rows = scan_reddit_direct(cache_ttl=1800)
        meta = cache_get("reddit_direct") or {}

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

        for r in wl_rows:
            r["is_temp"] = r["ticker"] in temp_tickers

        discoveries_count = len(disc_rows)
        from_cache = meta.get("from_cache", False)
        scanned_at = meta.get("scanned_at", datetime.now().isoformat())

        print(f"[/api/reddit] scan_reddit_direct → "
              f"{sum(1 for r in wl_rows if r.get('mentions', 0) > 0)} actifs, "
              f"{discoveries_count} trouvailles, cache={from_cache}")

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


@router.get("/reddit/discoveries")
def get_reddit_discoveries_endpoint():
    """
    Tickers hors watchlist détectés via scan_reddit_direct() + r/buzztickr.
    Source : discovery_results de scan_reddit_direct (cache 30 min) + buzztickr fusion.
    """
    try:
        from scrapers.reddit import scan_buzztickers, TICKER_BLACKLIST as _BL
        watchlist_set = set(t.upper() for t in WATCHLIST)

        _, disc_rows = scan_reddit_direct(cache_ttl=1800)

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

        if _YF_AVAILABLE:
            for d in disc_rows[:10]:
                if d.get("price") is not None:
                    continue
                try:
                    hist = get_history(d["ticker"], interval="1d", period="5d")
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

@router.get("/watchlist/temp")
def get_temp_watchlist():
    """Retourne la watchlist temporaire (tickers ajoutés depuis Reddit discoveries)."""
    return {"tickers": list(_TEMP_WATCHLIST.values()), "count": len(_TEMP_WATCHLIST)}


@router.post("/watchlist/temp")
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


@router.delete("/watchlist/temp/{ticker}")
def remove_temp_ticker(ticker: str):
    """Retire un ticker de la watchlist temporaire."""
    ticker = ticker.upper().strip()
    if ticker in _TEMP_WATCHLIST:
        del _TEMP_WATCHLIST[ticker]
        return {"success": True}
    return {"success": False, "error": "ticker non trouvé"}


# ── News & Macro ──────────────────────────────────────────────────────────────

@router.get("/news")
def get_news():
    """News filtrées par tickers et mots-clés, avec sentiment BULL/BEAR/NEUTRAL."""
    try:
        all_news, ticker_news, keyword_news, combined = fetch_and_filter(max_per_feed=5)

        def _enrich(news_list, news_type):
            result = []
            for n in news_list:
                result.append({
                    "title":            n.get("title", ""),
                    "source":           n.get("source", ""),
                    "link":             n.get("link", ""),
                    "summary":          n.get("summary", "")[:200],
                    "type":             news_type,
                    "matched_tickers":  n.get("matched_tickers", []),
                    "matched_keywords": n.get("matched_keywords", []),
                    "sentiment":        _news_sentiment(n.get("title", ""), n.get("summary", "")),
                })
            return result

        ticker_titles = {n["title"] for n in ticker_news}
        keyword_only  = [n for n in keyword_news if n["title"] not in ticker_titles]

        return clean_for_json({
            "total_fetched": len(all_news),
            "ticker_news":   _enrich(ticker_news, "TICKER"),
            "market_news":   _enrich(keyword_only, "MACRO"),
            "updated_at":    datetime.now().isoformat(),
        })
    except Exception as e:
        return {"error": str(e), "ticker_news": [], "market_news": []}


@router.get("/macro")
def get_macro():
    """Calendrier macro du jour : verdict + events récurrents + earnings."""
    try:
        events   = detect_recurring_events()
        earnings = check_earnings_today()
        reco     = get_trading_recommendation(events, earnings)

        return clean_for_json({
            "date":    datetime.now().strftime("%Y-%m-%d"),
            "verdict": reco["verdict"],
            "raison":  reco["raison"],
            "risque":  reco["risque"],
            "events":  [
                {"name": e["name"], "impact": e["impact"], "heure": e["heure"], "regle": e["regle"]}
                for e in events
            ],
            "earnings_today": earnings,
            "updated_at":     datetime.now().isoformat(),
        })
    except Exception as e:
        return {"error": str(e), "verdict": "INCONNU", "events": [], "earnings_today": []}


# ── Suivi positions ───────────────────────────────────────────────────────────

@router.get("/positions/monitor")
def monitor_positions():
    """
    Suivi temps réel des positions OPEN : prix actuel, PnL latent, alertes.
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

                fi      = get_fast_info(ticker)
                current = float(fi.last_price) if fi and fi.last_price else None
                if not current or current <= 0:
                    continue

                risk        = entry - stop
                pnl_latent  = round((current - entry) * shares, 2)
                pnl_pct     = round(pnl_latent / (entry * shares) * 100, 2) if entry * shares > 0 else 0.0
                r_current   = round((current - entry) / risk, 2) if risk > 0 else 0.0
                dist_target = round((target - current) / current * 100, 2) if current > 0 and target > current else 0.0
                dist_stop   = round((current - stop) / current * 100, 2)   if current > 0 else 0.0

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

                if status_alert and status_alert != "BREAKEVEN":
                    severity = "HIGH" if status_alert in ("TARGET_HIT", "STOP_HIT") else "MEDIUM"
                    pnl_str  = ("+" if pnl_latent >= 0 else "") + f"${pnl_latent:.0f}"
                    r_str    = ("+" if r_current  >= 0 else "") + f"{r_current:.1f}R"
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


# ── Alertes killzone ──────────────────────────────────────────────────────────

@router.get("/alerts")
def get_alerts(force: bool = False):
    """Alertes killzone intraday : volume breakout, approche SMA200, mouvement fort.
    Paramètre optionnel : force=true pour ignorer la vérification d'horaire (test mode).
    """
    try:
        in_kz      = force or _is_killzone()
        scanned_at = datetime.now().strftime("%H:%M:%S")

        if not in_kz:
            return clean_for_json({
                "in_killzone":  False,
                "test_mode":    False,
                "alerts":       [],
                "next_killzone": _next_killzone_str(),
                "scanned_at":   scanned_at,
            })

        alerts      = _scan_alerts()
        _alert_date = datetime.now().strftime("%Y-%m-%d")
        _seen_keys  = {(a.get("type"), a.get("ticker")) for a in _today_alerts}
        for _a in alerts:
            _k = (_a.get("type"), _a.get("ticker"))
            if _k not in _seen_keys:
                _today_alerts.append({"date": _alert_date, "type": _a.get("type"), "ticker": _a.get("ticker")})
                _seen_keys.add(_k)

        return clean_for_json({
            "in_killzone":  True,
            "test_mode":    bool(force),
            "alerts":       alerts,
            "next_killzone": _next_killzone_str(),
            "scanned_at":   scanned_at,
        })
    except Exception as e:
        return clean_for_json({
            "in_killzone":  False,
            "test_mode":    False,
            "alerts":       [],
            "next_killzone": "erreur",
            "scanned_at":   datetime.now().strftime("%H:%M:%S"),
            "error":        str(e),
        })


@router.get("/alerts/news")
def get_alerts_news():
    """Retourne uniquement les nouvelles news depuis le dernier appel (déduplication en mémoire)."""
    global _seen_news_titles
    try:
        all_news, ticker_news, keyword_news, _ = fetch_and_filter(max_per_feed=5)
        combined   = ticker_news + [n for n in keyword_news if n.get("title") not in {x["title"] for x in ticker_news}]
        fetched_at = datetime.now().isoformat()
        new_news   = []
        for n in combined:
            title = n.get("title", "")
            if title and title not in _seen_news_titles:
                _seen_news_titles.add(title)
                new_news.append({
                    "title":           title,
                    "source":          n.get("source", ""),
                    "link":            n.get("link", ""),
                    "summary":         n.get("summary", "")[:200],
                    "matched_tickers": n.get("matched_tickers", []),
                    "sentiment":       _news_sentiment(title, n.get("summary", "")),
                    "fetched_at":      fetched_at,
                })
        return clean_for_json({"new_news": new_news, "total_checked": len(combined)})
    except Exception as e:
        return {"new_news": [], "total_checked": 0, "error": str(e)}
