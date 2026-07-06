"""
Data Provider centralisé — point d'entrée unique pour tous les appels yfinance.

Toutes les réponses sont cachées via core/cache.py pour éviter les appels
redondants au sein d'une même fenêtre temporelle.

Usage :
    from core.data_provider import get_history, get_price, get_fast_info

    df = get_history("NVDA", interval="1d", period="1y")
    price = get_price("NVDA")
    info  = get_fast_info("NVDA")
"""
from __future__ import annotations

import concurrent.futures
import logging
from typing import Optional

import pandas as pd

from core.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# TTL par défaut selon la fréquence de mise à jour des données
_TTL_INTRADAY  = 60        # 1 min  — données temps réel
_TTL_DAILY     = 300       # 5 min  — OHLCV journalier
_TTL_WEEKLY    = 3_600     # 1 h    — données hebdo / longue période
_TTL_FAST_INFO = 60        # 1 min  — last_price, previous_close

# Borne dure (wall-clock) sur tout appel réseau yfinance. yfinance 1.3.0
# n'expose pas de timeout sur Ticker.history()/fast_info ; un socket bloqué
# figerait le dashboard. Un executor dédié rend la main à l'appelant en
# _YF_TIMEOUT s au plus (le thread orphelin se termine seul).
_YF_TIMEOUT  = 15
_YF_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="yf-timeout"
)


def call_with_timeout(fn, *args, timeout: int = _YF_TIMEOUT, **kwargs):
    """Exécute fn(*args, **kwargs) avec une borne dure. Lève TimeoutError si dépassé."""
    return _YF_EXECUTOR.submit(fn, *args, **kwargs).result(timeout=timeout)


def get_history(
    ticker:   str,
    interval: str = "1d",
    period:   str = "1y",
    ttl:      Optional[int] = None,
) -> pd.DataFrame:
    """
    Historique OHLCV via yfinance, avec cache TTL.

    Params
    ------
    ticker   : symbole (ex: "NVDA", "^VIX", "SPY")
    interval : "1m","5m","15m","1h","1d","1wk","1mo"
    period   : "5d","1mo","3mo","6mo","1y","2y","5y"
    ttl      : TTL en secondes (auto-détecté si None)

    Retourne un DataFrame vide en cas d'erreur (jamais une exception).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("[DataProvider] yfinance non installé")
        return pd.DataFrame()

    cache_key = f"hist__{ticker}__{interval}__{period}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if ttl is None:
        if interval in ("1m", "2m", "5m", "15m", "30m"):
            ttl = _TTL_INTRADAY
        elif interval == "1h":
            ttl = _TTL_DAILY
        elif interval in ("1d",):
            ttl = _TTL_DAILY
        else:
            ttl = _TTL_WEEKLY

    try:
        df = call_with_timeout(
            lambda: yf.Ticker(ticker).history(
                period=period,
                interval=interval,
                auto_adjust=True,
            )
        )
        if df is None:
            df = pd.DataFrame()
    except Exception as exc:
        logger.warning("[DataProvider] get_history(%s, %s, %s) erreur: %s", ticker, interval, period, exc)
        df = pd.DataFrame()

    cache_set(cache_key, df, ttl_seconds=ttl)
    return df


def get_price(ticker: str) -> Optional[float]:
    """
    Prix actuel via fast_info.last_price (cache 1 min).
    Retourne None si indisponible.
    """
    info = get_fast_info(ticker)
    if info is None:
        return None
    try:
        val = info.last_price
        return float(val) if val else None
    except Exception:
        return None


def get_fast_info(ticker: str) -> object:
    """
    fast_info yfinance — last_price, previous_close, day_high, day_low, etc.
    Résultat brut yfinance mis en cache 1 min.
    Retourne None si yfinance indisponible ou ticker invalide.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    cache_key = f"fastinfo__{ticker}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        fi = call_with_timeout(lambda: yf.Ticker(ticker).fast_info)
        cache_set(cache_key, fi, ttl_seconds=_TTL_FAST_INFO)
        return fi
    except Exception as exc:
        logger.warning("[DataProvider] get_fast_info(%s) erreur: %s", ticker, exc)
        return None


def get_sma(ticker: str, window: int = 200, period: str = "1y") -> Optional[float]:
    """
    Dernière valeur de la SMA(window) sur données journalières.
    Cache 5 min (même TTL que les données quotidiennes).
    Retourne None si pas assez de données.
    """
    cache_key = f"sma{window}__{ticker}__{period}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    df = get_history(ticker, interval="1d", period=period)
    if df.empty or "Close" not in df.columns or len(df) < window:
        return None

    try:
        sma_series = df["Close"].rolling(window).mean().dropna()
        if sma_series.empty:
            return None
        val = float(sma_series.iloc[-1])
        cache_set(cache_key, val, ttl_seconds=_TTL_DAILY)
        return val
    except Exception as exc:
        logger.warning("[DataProvider] get_sma(%s, %d) erreur: %s", ticker, window, exc)
        return None
