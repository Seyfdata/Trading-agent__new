"""
Router: endpoints analyse technique et SMC.
Couvre: indicators, alpha, deep-analysis, analysis/{ticker}, analysis,
        unified/{ticker}, unified.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from config.settings import WATCHLIST
from analysis.technical_indicators import clean_for_json

router = APIRouter()


@router.get("/indicators/{ticker}")
def get_indicators(ticker: str):
    """Indicateurs techniques complets pour un ticker (RSI, BB, Stoch, ADX, MACD, MAs)."""
    try:
        from analysis.technical_indicators import analyze_ticker
        return clean_for_json(analyze_ticker(ticker.upper()))
    except Exception as e:
        print(f"[API] /api/indicators/{ticker} error: {e}")
        return {"error": str(e), "ticker": ticker}


@router.get("/alpha/{ticker}")
def get_alpha(ticker: str):
    """Alpha vs SPY sur 1w/1m/3m pour un ticker."""
    try:
        from analysis.relative_strength import calc_alpha
        return calc_alpha(ticker.upper())
    except Exception as e:
        print(f"[API] /api/alpha/{ticker} error: {e}")
        return {"error": str(e), "ticker": ticker}


@router.get("/deep-analysis/{ticker}")
def get_deep_analysis(ticker: str):
    """Analyse technique approfondie + labels narratifs pour un ticker."""
    try:
        from analysis.relative_strength import deep_analysis
        return deep_analysis(ticker.upper())
    except Exception as e:
        print(f"[API] /api/deep-analysis/{ticker} error: {e}")
        return {"error": str(e), "ticker": ticker}


@router.get("/analysis/{ticker}")
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


@router.get("/analysis")
def get_smc_analysis_watchlist():
    """Analyse SMC des top 5 tickers de la watchlist (peut prendre ~30s)."""
    try:
        from analysis.smc_analyzer import analyze_ticker, format_smc_report

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


@router.get("/unified/{ticker}")
def get_unified(ticker: str):
    """Score de conviction unifié (setup_detector × SMC) pour un ticker."""
    try:
        from analysis.unified_scorer import unified_analysis
        result = unified_analysis(ticker.upper().strip())
        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e), "ticker": ticker, "unified_score": 0, "grade": "NO TRADE"}


@router.get("/unified")
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
