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
from dashboard.routers.analysis import router as analysis_router
app.include_router(analysis_router, prefix="/api")
from dashboard.routers.trading import router as trading_router
app.include_router(trading_router, prefix="/api")
from dashboard.routers.scanners import router as scanners_router
app.include_router(scanners_router, prefix="/api")
from dashboard.routers.social import router as social_router
app.include_router(social_router, prefix="/api")
# ── Helpers internes ────────────────────────────────────────────────────────

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
        from scrapers.market_data import get_market_context
        from dashboard.routers.market import _extract_scoring_ctx
        _raw_mkt = get_market_context()
        ctx = score_market_context(_extract_scoring_ctx(_raw_mkt))
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


@app.post("/api/pretrade/evaluate")
def pretrade_evaluate(payload: dict):
    """Gate pre-trade : verdict GO/NO-GO/GO-WARN + detail des checks.

    Body JSON attendu :
        capital, risk_pct, entry, stop, target  — obligatoires
        now                 str ISO  — datetime CET (defaut = maintenant)
        open_risk_amount    float    — dollars a risque sur positions ouvertes
        open_notional       float    — notionnel total positions ouvertes
        trades_today        int|null — override du comptage DB (null = auto)
    """
    try:
        from analysis.pretrade_gate import evaluate_trade
        from datetime import datetime as _dt

        now_raw = payload.get("now")
        now = _dt.fromisoformat(now_raw) if now_raw else None

        trades_today_raw = payload.get("trades_today")
        trades_today = int(trades_today_raw) if trades_today_raw is not None else None

        return evaluate_trade(
            capital=float(payload.get("capital", 10000)),
            risk_pct=float(payload.get("risk_pct", 1.0)),
            entry=float(payload.get("entry", 0)),
            stop=float(payload.get("stop", 0)),
            target=float(payload.get("target", 0)),
            now=now,
            open_risk_amount=float(payload.get("open_risk_amount", 0.0)),
            open_notional=float(payload.get("open_notional", 0.0)),
            trades_today=trades_today,
        )
    except Exception as e:
        return clean_for_json({"error": str(e), "verdict": "NO-GO", "checks": []})


@app.post("/api/risk/size")
def risk_size(payload: dict):
    """Valide et calcule la taille d'une position LONG via le moteur de risque autoritaire.

    Body JSON attendu :
        capital               float  — capital total du compte (USD)
        risk_pct              float  — risque en % du capital (ex. 1.0)
        entry                 float  — prix d'entrée
        stop                  float  — stop-loss (< entry)
        target                float  — cible (> entry)
        open_positions_value  float  — valeur positions ouvertes (défaut 0)
        trades_today          int    — trades déjà pris aujourd'hui (défaut 0)

    Retour : { verdict, violations, shares, risk_amount, rr, exposure_pct, position_value }
    """
    try:
        from analysis.risk_engine import validate_and_size
        result = validate_and_size(
            capital=float(payload.get("capital", 0)),
            risk_pct=float(payload.get("risk_pct", 1.0)),
            entry=float(payload.get("entry", 0)),
            stop=float(payload.get("stop", 0)),
            target=float(payload.get("target", 0)),
            open_positions_value=float(payload.get("open_positions_value", 0.0)),
            trades_today=int(payload.get("trades_today", 0)),
        )
        return result
    except Exception as e:
        return clean_for_json({"error": str(e), "verdict": "NO-GO", "violations": [str(e)]})


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
