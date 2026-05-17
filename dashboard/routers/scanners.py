"""
Router: scanners de marché.
Couvre: pullbacks, relative-strength, options/{ticker},
        backtest/{ticker}, backtest/report.
"""
from __future__ import annotations

from fastapi import APIRouter

from config.settings import WATCHLIST
from analysis.technical_indicators import clean_for_json
from database.models import DB_PATH

router = APIRouter()


@router.get("/pullbacks")
def get_pullbacks():
    """Scan de survente sur la watchlist (RSI<35, BB%B<0, Stoch<20) + contexte marché."""
    try:
        from analysis.pullback_scanner import scan_pullbacks
        return clean_for_json(scan_pullbacks())
    except Exception as e:
        print(f"[API] /api/pullbacks error: {e}")
        return {"error": str(e), "alerts": [], "watches": [], "no_alerts": []}


@router.get("/relative-strength")
def get_relative_strength(period: str = "1m", top: int = 2):
    """Classement alpha vs SPY sur 1w/1m/3m + deep analysis top N."""
    try:
        from analysis.relative_strength import scan_relative_strength
        top = max(1, min(5, top))
        return scan_relative_strength(ranking_period=period, top_n=top)
    except Exception as e:
        print(f"[API] /api/relative-strength error: {e}")
        return {"error": str(e), "ranking": [], "deep_analyses": []}


@router.get("/options/{ticker}")
def get_options(ticker: str):
    """Analyse du flux options (PCR, max pain, unusual activity, smart money) pour un ticker."""
    try:
        from analysis.options_flow import get_options_sentiment
        result = get_options_sentiment(ticker.upper().strip())
        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@router.get("/backtest/{ticker}")
def get_backtest_ticker(
    ticker:   str,
    strategy: str = "ALL",
    period:   str = "3y",
):
    """
    Backtest mécanique sur un ticker.
    strategy : DISCOUNT_ZONE | SMA200_BOUNCE | VOLUME_MOMENTUM | ALL
    period   : 1y | 2y | 3y
    """
    try:
        from analysis.backtester import backtest_strategy, backtest_all_strategies, STRATEGIES
        ticker = ticker.upper().strip()

        if strategy == "ALL":
            result = backtest_all_strategies(ticker, period=period)
        elif strategy in STRATEGIES:
            result = backtest_strategy(ticker, strategy, period=period)
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
            return {"error": f"Strategie inconnue : {strategy}. Valeurs : {STRATEGIES + ['ALL']}"}

        return clean_for_json(result)
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@router.get("/backtest/report")
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
                "SELECT ticker FROM scores_history"
                " WHERE date=(SELECT MAX(date) FROM scores_history)"
                " ORDER BY total_score DESC LIMIT ?",
                (top_n,),
            ).fetchall()
        tickers = [r[0] for r in rows]
        return tickers if tickers else list(WATCHLIST)[:top_n]
    except Exception:
        return list(WATCHLIST)[:top_n]
