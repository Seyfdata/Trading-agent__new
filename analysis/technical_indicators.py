"""
Technical Indicators — Calculs RSI, Bollinger, Stochastique, ADX, MACD, MAs.

Fonctions pures recevant un DataFrame yfinance.
Pas d'effets de bord, pas d'appels réseau (sauf analyze_ticker).
Utilise pandas pur, sans dépendance 'ta'.
"""

from __future__ import annotations
import time
from functools import wraps
from datetime import datetime
from typing import Optional

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


# ── Cache maison TTL (évite lru_cache qui n'expire pas) ──────────────────────
_CACHE: dict = {}
_CACHE_TTL = 300  # 5 minutes

_SHORT_CACHE: dict = {}
_SHORT_TTL = 86400  # 24 heures


def _cache_get(key: str) -> Optional[dict]:
    entry = _CACHE.get(key)
    if entry and time.time() < entry["expires"]:
        return entry["data"]
    return None


def _cache_set(key: str, data: dict, ttl: int = _CACHE_TTL):
    _CACHE[key] = {"data": data, "expires": time.time() + ttl}


def _nan_to_none(v):
    if v is None:
        return None
    try:
        if _NUMPY_OK and isinstance(v, (float, int)):
            if _NUMPY_OK:
                import math
                if math.isnan(float(v)) or math.isinf(float(v)):
                    return None
        return round(float(v), 4)
    except Exception:
        return None


def clean_for_json(obj):
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_for_json(i) for i in obj]
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if _NUMPY_OK:
        import numpy as np_
        if isinstance(obj, np_.bool_):
            return bool(obj)
        if isinstance(obj, np_.integer):
            return int(obj)
        if isinstance(obj, np_.floating):
            f = float(obj)
            import math
            return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
        if isinstance(obj, np_.ndarray):
            return obj.tolist()
    if isinstance(obj, float):
        import math
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (int, str)):
        return obj
    return str(obj)


# ── Indicateurs techniques ────────────────────────────────────────────────────

def calc_rsi(df: "pd.DataFrame", period: int = 14) -> Optional[float]:
    """Calcule le RSI Wilder. Retourne la valeur actuelle (dernière ligne)."""
    try:
        close = df["Close"].dropna()
        if len(close) < period + 1:
            return None
        delta = close.diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs  = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return _nan_to_none(val)
    except Exception as e:
        print(f"[TechIndicators] calc_rsi error: {e}")
        return None


def calc_bollinger(df: "pd.DataFrame", period: int = 20, std: float = 2.0) -> dict:
    """Calcule les Bandes de Bollinger. Retourne upper/middle/lower/percent_b/width."""
    result = {"upper": None, "middle": None, "lower": None, "percent_b": None, "width": None}
    try:
        close = df["Close"].dropna()
        if len(close) < period:
            return result
        mid = close.rolling(period).mean()
        sd  = close.rolling(period).std(ddof=0)
        upper = mid + std * sd
        lower = mid - std * sd
        last_close = float(close.iloc[-1])
        u = float(upper.iloc[-1])
        m = float(mid.iloc[-1])
        l = float(lower.iloc[-1])
        pct_b = (last_close - l) / (u - l) if (u - l) != 0 else 0.5
        width = (u - l) / m if m != 0 else 0.0
        result = {
            "upper":     _nan_to_none(u),
            "middle":    _nan_to_none(m),
            "lower":     _nan_to_none(l),
            "percent_b": _nan_to_none(pct_b),
            "width":     _nan_to_none(width),
        }
    except Exception as e:
        print(f"[TechIndicators] calc_bollinger error: {e}")
    return result


def calc_stochastic(df: "pd.DataFrame", k_period: int = 14, d_period: int = 3) -> dict:
    """Calcule le Stochastique %K et %D."""
    result = {"k": None, "d": None}
    try:
        high  = df["High"].dropna()
        low   = df["Low"].dropna()
        close = df["Close"].dropna()
        if len(close) < k_period:
            return result
        lowest_low   = low.rolling(k_period).min()
        highest_high = high.rolling(k_period).max()
        denom = highest_high - lowest_low
        pct_k = 100 * (close - lowest_low) / denom.replace(0, float("nan"))
        pct_d = pct_k.rolling(d_period).mean()
        result = {
            "k": _nan_to_none(pct_k.iloc[-1]),
            "d": _nan_to_none(pct_d.iloc[-1]),
        }
    except Exception as e:
        print(f"[TechIndicators] calc_stochastic error: {e}")
    return result


def calc_adx(df: "pd.DataFrame", period: int = 14) -> dict:
    """Calcule ADX, +DI, -DI."""
    result = {"adx": None, "plus_di": None, "minus_di": None}
    try:
        high  = df["High"]
        low   = df["Low"]
        close = df["Close"]
        if len(close) < period * 2:
            return result
        # True Range
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs()
        ], axis=1).max(axis=1)
        # Directional movement
        up   = high.diff()
        down = -low.diff()
        plus_dm  = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        # Smoothed (Wilder)
        atr      = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        plus_di  = 100 * plus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr.replace(0, float("nan"))
        minus_di = 100 * minus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr.replace(0, float("nan"))
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
        adx = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        result = {
            "adx":      _nan_to_none(adx.iloc[-1]),
            "plus_di":  _nan_to_none(plus_di.iloc[-1]),
            "minus_di": _nan_to_none(minus_di.iloc[-1]),
        }
    except Exception as e:
        print(f"[TechIndicators] calc_adx error: {e}")
    return result


def calc_macd(df: "pd.DataFrame", fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """Calcule MACD, signal, histogramme et détecte le bullish cross récent."""
    result = {"macd": None, "signal": None, "histogram": None, "bullish_cross": False}
    try:
        close = df["Close"].dropna()
        if len(close) < slow + signal:
            return result
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line   = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram   = macd_line - signal_line
        # Bullish cross : MACD passe au-dessus du signal dans les 3 dernières bougies
        bullish = False
        try:
            for i in range(-3, 0):
                if macd_line.iloc[i] > signal_line.iloc[i] and macd_line.iloc[i-1] <= signal_line.iloc[i-1]:
                    bullish = True
                    break
        except Exception:
            pass
        result = {
            "macd":         _nan_to_none(macd_line.iloc[-1]),
            "signal":       _nan_to_none(signal_line.iloc[-1]),
            "histogram":    _nan_to_none(histogram.iloc[-1]),
            "bullish_cross": bool(bullish),
        }
    except Exception as e:
        print(f"[TechIndicators] calc_macd error: {e}")
    return result


def calc_moving_averages(df: "pd.DataFrame") -> dict:
    """Calcule SMA20, SMA50, SMA200 et la position du prix."""
    result = {"sma20": None, "sma50": None, "sma200": None, "price_vs_sma": "unknown"}
    try:
        close = df["Close"].dropna()
        price = float(close.iloc[-1])
        sma20  = _nan_to_none(close.rolling(20).mean().iloc[-1])
        sma50  = _nan_to_none(close.rolling(50).mean().iloc[-1])
        sma200 = _nan_to_none(close.rolling(200).mean().iloc[-1])
        # Position relative
        above = sum(1 for v in [sma20, sma50, sma200] if v is not None and price > v)
        below = sum(1 for v in [sma20, sma50, sma200] if v is not None and price < v)
        total = above + below
        if total == 0:
            pos = "unknown"
        elif above == total:
            pos = "above_all"
        elif below == total:
            pos = "below_all"
        else:
            pos = "mixed"
        result = {
            "sma20":       sma20,
            "sma50":       sma50,
            "sma200":      sma200,
            "price_vs_sma": pos,
        }
    except Exception as e:
        print(f"[TechIndicators] calc_moving_averages error: {e}")
    return result


def get_short_interest(ticker: str) -> dict:
    """Récupère le short interest via yfinance.info — cache 24h."""
    result = {"short_pct": None, "days_to_cover": None, "short_ratio": None}
    cache_key = f"short_{ticker}"
    cached = _SHORT_CACHE.get(cache_key)
    if cached and time.time() < cached["expires"]:
        return cached["data"]
    if not _YF_OK:
        return result
    try:
        info = yf.Ticker(ticker).info or {}
        shares_short   = info.get("sharesShort")
        shares_float   = info.get("floatShares")
        short_ratio    = info.get("shortRatio")
        short_pct_float = info.get("shortPercentOfFloat")
        pct = None
        if short_pct_float is not None:
            pct = round(float(short_pct_float) * 100, 2)
        elif shares_short and shares_float and shares_float > 0:
            pct = round(shares_short / shares_float * 100, 2)
        result = {
            "short_pct":    pct,
            "days_to_cover": _nan_to_none(short_ratio) if short_ratio else None,
            "short_ratio":   _nan_to_none(short_ratio) if short_ratio else None,
        }
    except Exception as e:
        print(f"[TechIndicators] get_short_interest({ticker}) error: {e}")
    _SHORT_CACHE[cache_key] = {"data": result, "expires": time.time() + _SHORT_TTL}
    return result


def analyze_ticker(ticker: str) -> dict:
    """
    Fonction principale — récupère 1 an de data et calcule tous les indicateurs.
    Cache interne 5 min.
    """
    ticker = ticker.upper()
    cached = _cache_get(ticker)
    if cached is not None:
        print(f"[TechIndicators] {ticker}: depuis cache")
        return cached

    if not _YF_OK or not _PANDAS_OK:
        return clean_for_json({"ticker": ticker, "error": "yfinance ou pandas non disponible"})

    print(f"[TechIndicators] Analyse {ticker}...")
    try:
        df = yf.Ticker(ticker).history(period="1y", interval="1d")
        if df is None or df.empty:
            return clean_for_json({"ticker": ticker, "error": "Pas de données yfinance"})

        df.index = pd.to_datetime(df.index)

        # Prix actuel + variation
        price      = float(df["Close"].iloc[-1])
        prev_price = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
        change_pct = round((price - prev_price) / prev_price * 100, 2) if prev_price else 0.0

        # Calcul de tous les indicateurs
        rsi         = calc_rsi(df)
        bollinger   = calc_bollinger(df)
        stochastic  = calc_stochastic(df)
        adx         = calc_adx(df)
        macd        = calc_macd(df)
        mas         = calc_moving_averages(df)

        # Signaux de survente
        oversold          = rsi is not None and rsi < 35
        below_bb_lower    = bollinger["percent_b"] is not None and bollinger["percent_b"] < 0
        stoch_oversold    = stochastic["k"] is not None and stochastic["k"] < 20
        conditions_met    = sum([oversold, below_bb_lower, stoch_oversold])

        result = {
            "ticker":      ticker,
            "price":       round(price, 2),
            "change_pct":  change_pct,
            "rsi":         rsi,
            "bollinger":   bollinger,
            "stochastic":  stochastic,
            "adx":         adx,
            "macd":        macd,
            "mas":         mas,
            "signals": {
                "oversold":               oversold,
                "below_bb_lower":         below_bb_lower,
                "stoch_oversold":         stoch_oversold,
                "pullback_conditions_met": conditions_met,
            },
            "analyzed_at": datetime.now().isoformat(),
        }
        result = clean_for_json(result)
        _cache_set(ticker, result)
        print(f"[TechIndicators] {ticker}: RSI={rsi} BB%B={bollinger.get('percent_b')} Stoch={stochastic.get('k')} cond={conditions_met}/3")
        return result

    except Exception as e:
        import traceback
        print(f"[TechIndicators] analyze_ticker({ticker}) ERREUR: {e}\n{traceback.format_exc()}")
        return clean_for_json({"ticker": ticker, "error": str(e)})
