"""
Relative Strength Scout — Classe les tickers par alpha vs SPY sur 1W/1M/3M.
Analyse technique approfondie (ADX, short interest) sur les top N.
Cache 5 min. Zéro coût API — yfinance uniquement.
"""

from __future__ import annotations
import time
from datetime import datetime
from typing import Optional

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

try:
    from config.settings import WATCHLIST as _DEFAULT_WATCHLIST
except Exception:
    _DEFAULT_WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "META", "AMZN", "GOOGL",
        "AMD", "AVGO", "QCOM", "INTC", "MU", "ASML", "TSM", "MRVL",
        "PLTR", "SMCI", "CRM", "SNOW", "TWLO", "ZS", "BABA",
    ]

from analysis.technical_indicators import analyze_ticker, clean_for_json
from core.cache import cache_get, cache_set

_PERIOD_SESSIONS = {"1w": 5, "1m": 21, "3m": 63}



def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        import math
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return None


def calc_alpha(ticker: str, benchmark: str = "SPY", periods: list | None = None) -> dict:
    """
    Calcule le retour et l'alpha vs benchmark pour chaque période.
    Utilise un seul appel yf.download en batch.
    Cache 5 min.
    """
    if periods is None:
        periods = ["1w", "1m", "3m"]

    ticker = ticker.upper()
    cache_key = f"alpha_{ticker}_{benchmark}"
    cached = cache_get(cache_key)
    if cached is not None:
        print(f"[RelStrength] {ticker}: depuis cache")
        return cached

    result = {
        "ticker": ticker,
        "benchmark": benchmark,
        "returns": {p: {"ticker": None, "benchmark": None} for p in periods},
        "alpha": {p: None for p in periods},
        "error": None,
    }

    if not _YF_OK or not _PANDAS_OK:
        result["error"] = "yfinance ou pandas non disponible"
        return result

    try:
        print(f"[RelStrength] Téléchargement batch {ticker} + {benchmark}...")
        raw = yf.download(
            [ticker, benchmark],
            period="1y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw is None or raw.empty:
            result["error"] = "Pas de données yfinance"
            return result

        # Extraire la colonne Close pour chaque ticker
        if "Close" in raw.columns:
            close_df = raw["Close"]
        else:
            try:
                close_df = raw.xs("Close", axis=1, level=0)
            except Exception:
                result["error"] = "Structure Close inattendue"
                return result

        if ticker not in close_df.columns or benchmark not in close_df.columns:
            result["error"] = f"Ticker ou benchmark absent des données"
            return result

        t_series = close_df[ticker].dropna()
        b_series = close_df[benchmark].dropna()

        if len(t_series) < 5 or len(b_series) < 5:
            result["error"] = "Pas assez de données"
            return result

        for period in periods:
            n = _PERIOD_SESSIONS.get(period, 21)
            if len(t_series) < n + 1 or len(b_series) < n + 1:
                continue
            try:
                t_now  = float(t_series.iloc[-1])
                t_prev = float(t_series.iloc[-(n + 1)])
                b_now  = float(b_series.iloc[-1])
                b_prev = float(b_series.iloc[-(n + 1)])

                t_ret = (t_now - t_prev) / t_prev * 100 if t_prev else None
                b_ret = (b_now - b_prev) / b_prev * 100 if b_prev else None
                alpha = (t_ret - b_ret) if (t_ret is not None and b_ret is not None) else None

                result["returns"][period] = {
                    "ticker":    _safe_float(t_ret),
                    "benchmark": _safe_float(b_ret),
                }
                result["alpha"][period] = _safe_float(alpha)
            except Exception as e:
                print(f"[RelStrength] {ticker} period={period} error: {e}")
                continue

        cache_set(cache_key, result, 300)
        print(f"[RelStrength] {ticker}: alpha 1w={result['alpha'].get('1w')} 1m={result['alpha'].get('1m')} 3m={result['alpha'].get('3m')}")
        return result

    except Exception as e:
        import traceback
        print(f"[RelStrength] calc_alpha({ticker}) ERREUR: {e}\n{traceback.format_exc()}")
        result["error"] = str(e)
        return result


def _verdict(alpha_1m: Optional[float]) -> str:
    if alpha_1m is None:
        return "unknown"
    if alpha_1m >= 2.0:
        return "outperforming"
    if alpha_1m <= -2.0:
        return "underperforming"
    return "in_line"


def rank_watchlist_by_alpha(tickers: list | None = None, ranking_period: str = "1m") -> list:
    """
    Classe les tickers par alpha décroissant sur ranking_period.
    Retourne liste triée avec rank, ticker, alphas, verdict.
    Cache 5 min.
    """
    if tickers is None:
        tickers = list(_DEFAULT_WATCHLIST)

    cache_key = f"rank_{ranking_period}_{'_'.join(sorted(tickers))}"
    cached = cache_get(cache_key)
    if cached is not None:
        print(f"[RelStrength] Ranking depuis cache ({ranking_period})")
        return cached

    print(f"[RelStrength] Classement {len(tickers)} tickers sur {ranking_period}...")
    rows = []
    for t in tickers:
        try:
            a = calc_alpha(t)
            alpha_1w = a["alpha"].get("1w")
            alpha_1m = a["alpha"].get("1m")
            alpha_3m = a["alpha"].get("3m")
            ret_1m   = a["returns"].get("1m", {}).get("ticker")
            bm_1m    = a["returns"].get("1m", {}).get("benchmark")
            rows.append({
                "ticker":             t,
                "alpha_1w":           alpha_1w,
                "alpha_1m":           alpha_1m,
                "alpha_3m":           alpha_3m,
                "return_1m":          ret_1m,
                "benchmark_return_1m": bm_1m,
                "verdict":            _verdict(alpha_1m),
                "error":              a.get("error"),
            })
        except Exception as e:
            print(f"[RelStrength] rank {t}: {e}")
            rows.append({"ticker": t, "alpha_1w": None, "alpha_1m": None, "alpha_3m": None,
                         "return_1m": None, "benchmark_return_1m": None, "verdict": "unknown", "error": str(e)})

    # Tri par alpha sur ranking_period, None en dernier
    key_map = {"1w": "alpha_1w", "1m": "alpha_1m", "3m": "alpha_3m"}
    sort_key = key_map.get(ranking_period, "alpha_1m")
    rows.sort(key=lambda x: (x[sort_key] is None, -(x[sort_key] or 0)))

    ranked = []
    for i, row in enumerate(rows):
        row["rank"] = i + 1
        ranked.append(row)

    cache_set(cache_key, ranked, 300)
    print(f"[RelStrength] Classement terminé. #1: {ranked[0]['ticker'] if ranked else 'N/A'}")
    return ranked


def _rsi_label(rsi: Optional[float]) -> str:
    if rsi is None:
        return "N/A"
    if rsi > 70:
        return "Surachat"
    if rsi > 60:
        return "Approche surachat"
    if rsi >= 40:
        return "Neutre"
    if rsi < 30:
        return "Survente"
    return "Bas"


def _adx_label(adx: Optional[float]) -> tuple[str, bool]:
    if adx is None:
        return "N/A", False
    if adx > 25:
        return "Tendance forte", True
    if adx >= 20:
        return "Tendance modérée", False
    return "Pas de tendance", False


def _short_label(pct: Optional[float]) -> tuple[str, str]:
    if pct is None:
        return "N/A", "unknown"
    if pct < 3:
        return "Faible", "low"
    if pct <= 10:
        return "Modérée", "medium"
    return "Élevée", "high"


def _bb_label(percent_b: Optional[float]) -> str:
    if percent_b is None:
        return "N/A"
    if percent_b > 1:
        return "Cassure bande supérieure"
    if percent_b > 0.8:
        return "Proche bande supérieure"
    if percent_b < 0:
        return "Sous bande inférieure"
    if percent_b < 0.2:
        return "Proche bande inférieure"
    return "Milieu des bandes"


def _macd_label(macd_data: dict) -> tuple[str, str]:
    if not macd_data:
        return "N/A", "neutral"
    hist = macd_data.get("histogram")
    cross = macd_data.get("bullish_cross", False)
    if cross:
        return "Croisement haussier confirmé", "bullish"
    if hist is not None:
        if hist > 0:
            return "Haussier", "bullish"
        if hist < 0:
            return "Baissier", "bearish"
    return "Neutre", "neutral"


def _mas_label(mas_data: dict) -> str:
    pos = (mas_data or {}).get("price_vs_sma", "unknown")
    if pos == "above_all":
        return "Au-dessus SMA 20/50/200"
    if pos == "below_all":
        return "Sous SMA 20/50/200"
    if pos == "mixed":
        return "Position mixte (SMA)"
    return "N/A"


def _build_conclusion(ticker: str, alpha_1m: Optional[float], adx_val: Optional[float],
                      short_level: str, rsi: Optional[float], percent_b: Optional[float]) -> str:
    parts = []
    if alpha_1m is not None and alpha_1m > 5 and adx_val is not None and adx_val > 25 and short_level == "low":
        parts.append("Momentum intact, tendance forte, pression vendeuse faible")
    elif alpha_1m is not None and alpha_1m > 2:
        parts.append("Surperformance confirmée")
    elif alpha_1m is not None and alpha_1m < -2:
        parts.append("Sous-performance vs marché")

    if rsi is not None and rsi > 70:
        parts.append("Risque de repli court terme élevé (RSI surachat)")
    if percent_b is not None and percent_b > 1:
        parts.append("Extension au-delà de la bande supérieure — possible consolidation")
    if adx_val is not None and adx_val < 20:
        parts.append("Absence de tendance directionnelle")

    return ". ".join(parts) + "." if parts else "Analyse en cours."


def deep_analysis(ticker: str) -> dict:
    """
    Analyse technique approfondie : indicateurs + labels narratifs + conclusion.
    Réutilise analyze_ticker() du module technical_indicators.
    Cache 5 min.
    """
    ticker = ticker.upper()
    cache_key = f"deep_{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        print(f"[RelStrength] deep_analysis {ticker}: depuis cache")
        return cached

    print(f"[RelStrength] Analyse approfondie {ticker}...")
    base = analyze_ticker(ticker)
    if base.get("error"):
        result = {"ticker": ticker, "error": base["error"]}
        cache_set(cache_key, result, 300)
        return result

    rsi        = base.get("rsi")
    bollinger  = base.get("bollinger") or {}
    stochastic = base.get("stochastic") or {}
    adx_data   = base.get("adx") or {}
    macd_data  = base.get("macd") or {}
    mas_data   = base.get("mas") or {}
    price      = base.get("price")
    change_pct = base.get("change_pct")

    # Short interest
    from analysis.technical_indicators import get_short_interest
    si = get_short_interest(ticker)
    short_pct   = si.get("short_pct")
    days_cover  = si.get("days_to_cover")
    short_lbl, short_lvl = _short_label(short_pct)

    adx_val             = adx_data.get("adx")
    adx_lbl, adx_strong = _adx_label(adx_val)

    percent_b  = bollinger.get("percent_b")
    macd_lbl, macd_dir = _macd_label(macd_data)

    # Snapshot 1 ligne
    if rsi is not None and rsi > 65 and adx_val is not None and adx_val > 25:
        snapshot = "Forte tendance haussière"
    elif rsi is not None and rsi > 55:
        snapshot = "Haussier"
    elif rsi is not None and rsi < 40:
        snapshot = "Zone de survente"
    else:
        snapshot = "Neutre / consolidation"

    # Conclusion auto
    alpha_1m = None
    try:
        a = calc_alpha(ticker)
        alpha_1m = a["alpha"].get("1m")
    except Exception:
        pass

    conclusion = _build_conclusion(ticker, alpha_1m, adx_val, short_lvl, rsi, percent_b)

    result = {
        "ticker":   ticker,
        "price":    price,
        "change_pct": change_pct,
        "snapshot": snapshot,
        "alpha_1m": alpha_1m,
        "signals": {
            "rsi": {
                "value": rsi,
                "label": _rsi_label(rsi),
                "warning": rsi is not None and rsi > 70,
            },
            "macd": {
                "value":     macd_data.get("histogram"),
                "bullish_cross": macd_data.get("bullish_cross", False),
                "direction": macd_dir,
                "label":     macd_lbl,
            },
            "mas": {
                "value": mas_data.get("price_vs_sma"),
                "label": _mas_label(mas_data),
                "sma20": mas_data.get("sma20"),
                "sma50": mas_data.get("sma50"),
                "sma200": mas_data.get("sma200"),
            },
            "bollinger": {
                "value":   percent_b,
                "label":   _bb_label(percent_b),
                "warning": percent_b is not None and percent_b > 1,
                "upper":   bollinger.get("upper"),
                "lower":   bollinger.get("lower"),
            },
            "adx": {
                "value":  adx_val,
                "label":  adx_lbl,
                "strong": adx_strong,
                "plus_di":  adx_data.get("plus_di"),
                "minus_di": adx_data.get("minus_di"),
            },
            "short_interest": {
                "pct":          short_pct,
                "days_to_cover": days_cover,
                "label":        short_lbl,
                "level":        short_lvl,
            },
        },
        "conclusion": conclusion,
        "analyzed_at": datetime.now().isoformat(),
    }

    result = clean_for_json(result)
    cache_set(cache_key, result, 300)
    print(f"[RelStrength] {ticker}: snapshot='{snapshot}' alpha_1m={alpha_1m}")
    return result


def scan_relative_strength(tickers: list | None = None, ranking_period: str = "1m", top_n: int = 2) -> dict:
    """
    Point d'entrée principal : classement alpha + deep analysis top N.
    """
    if tickers is None:
        tickers = list(_DEFAULT_WATCHLIST)

    print(f"[RelStrength] Scan RS {len(tickers)} tickers, period={ranking_period}, top_n={top_n}...")

    ranking = rank_watchlist_by_alpha(tickers, ranking_period)

    # Deep analysis sur les top_n (sans erreur)
    top_tickers = [r["ticker"] for r in ranking if not r.get("error")][:top_n]
    deep_analyses = []
    for t in top_tickers:
        try:
            da = deep_analysis(t)
            deep_analyses.append(da)
        except Exception as e:
            print(f"[RelStrength] deep_analysis {t}: {e}")

    # Verdict comparatif
    comparative = ""
    if len(deep_analyses) >= 2:
        d0, d1 = deep_analyses[0], deep_analyses[1]
        rsi0 = (d0.get("signals") or {}).get("rsi", {}).get("value")
        rsi1 = (d1.get("signals") or {}).get("rsi", {}).get("value")
        adx0 = (d0.get("signals") or {}).get("adx", {}).get("value")
        adx1 = (d1.get("signals") or {}).get("adx", {}).get("value")

        # Celui avec RSI plus bas ET ADX > 25 -> meilleure zone d'entrée
        t0_ok = rsi0 is not None and rsi0 < 65 and adx0 is not None and adx0 > 25
        t1_ok = rsi1 is not None and rsi1 < 65 and adx1 is not None and adx1 > 25

        if t1_ok and not t0_ok:
            comparative = f"{d1['ticker']} offre une zone d'entrée plus favorable ({d1['ticker']}: RSI {rsi1:.0f} vs {d0['ticker']}: RSI {rsi0:.0f})" if rsi0 else f"{d1['ticker']}: zone d'entrée plus favorable"
        elif t0_ok and not t1_ok:
            comparative = f"{d0['ticker']} : alpha fort + tendance confirmée. {d1['ticker']} : alpha plus modéré."
        elif t0_ok and t1_ok:
            # Celui avec RSI le plus bas
            if rsi0 is not None and rsi1 is not None:
                best = d1['ticker'] if rsi1 < rsi0 else d0['ticker']
                comparative = f"{best} : zone d'entrée techniquement plus favorable (RSI moins tendu)."
            else:
                comparative = f"{d0['ticker']} et {d1['ticker']} : deux candidats valides, analyser les niveaux de support."
        else:
            comparative = f"{d0['ticker']} : meilleur alpha. Attendre confirmation technique avant entrée."
    elif len(deep_analyses) == 1:
        comparative = f"{deep_analyses[0]['ticker']} : seul candidat analysé en profondeur."

    result = {
        "date":            datetime.now().strftime("%Y-%m-%d"),
        "scanned_at":      datetime.now().isoformat(),
        "benchmark":       "SPY",
        "ranking_period":  ranking_period,
        "tickers_scanned": len(tickers),
        "ranking":         ranking,
        "deep_analyses":   deep_analyses,
        "comparative_verdict": comparative,
        "summary": {
            "outperforming":  sum(1 for r in ranking if r.get("verdict") == "outperforming"),
            "in_line":        sum(1 for r in ranking if r.get("verdict") == "in_line"),
            "underperforming": sum(1 for r in ranking if r.get("verdict") == "underperforming"),
        },
    }
    return clean_for_json(result)