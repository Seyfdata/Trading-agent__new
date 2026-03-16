"""
Reddit Trend Analysis — Tendance 5 jours et vérification des tickers.

Ce module :
  1. Sauvegarde un snapshot journalier du CSV Reddit (RedditScanner/snapshots/)
  2. Calcule la tendance des mentions sur 5 jours pour chaque ticker
  3. Vérifie si un ticker est un vrai titre boursier via yfinance (cache mémoire)

Usage :
    from analysis.reddit_trend import get_reddit_trends, verify_ticker, save_today_snapshot
"""

import shutil
import threading
from datetime import date, timedelta
from pathlib import Path

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


# ── Cache vérification tickers (persistant pour la durée du process) ─────────
_verify_cache: dict = {}


# ── Snapshots ─────────────────────────────────────────────────────────────────

def save_today_snapshot(csv_path: Path, snapshots_dir: Path) -> bool:
    """
    Copie le CSV Reddit du jour dans snapshots/reddit_YYYY-MM-DD.csv.

    Ne copie pas si le snapshot du jour existe déjà.
    Crée le dossier snapshots/ si nécessaire.
    Retourne True si la copie a été effectuée.
    """
    if not csv_path.exists():
        return False
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    dest = snapshots_dir / f"reddit_{date.today().isoformat()}.csv"
    if not dest.exists():
        shutil.copy2(csv_path, dest)
        return True
    return False


def _read_snapshot(snapshots_dir: Path, day: date) -> dict:
    """
    Lit un snapshot daté et retourne {ticker: mentions}.
    Retourne {} si le fichier est absent ou si pandas n'est pas installé.
    """
    path = snapshots_dir / f"reddit_{day.isoformat()}.csv"
    if not path.exists() or not PANDAS_AVAILABLE:
        return {}
    try:
        df = pd.read_csv(path)
        result = {}
        for _, row in df.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            if ticker:
                result[ticker] = int(row.get("Mentions", 0))
        return result
    except Exception:
        return {}


def get_reddit_trends(snapshots_dir: Path) -> dict:
    """
    Calcule la tendance 5 jours pour chaque ticker présent dans le snapshot du jour.

    Paramètres
    ----------
    snapshots_dir : Path — dossier des snapshots (RedditScanner/snapshots/)

    Retourne
    --------
    dict {
        ticker: {
            "mentions_today":  int,
            "mentions_avg_5d": float | None,
            "trend":           "RISING" | "FALLING" | "STABLE" | "NEW",
            "trend_pct":       float | None,  # variation % vs moyenne 5j
        }
    }

    Règles :
        RISING  → today > avg * 1.5
        FALLING → today < avg * 0.5
        STABLE  → entre les deux
        NEW     → pas de données passées (avg = 0 ou < 1 snapshot)
    """
    today = date.today()
    today_data = _read_snapshot(snapshots_dir, today)

    past_days_data = []
    for i in range(1, 6):
        day_data = _read_snapshot(snapshots_dir, today - timedelta(days=i))
        if day_data:
            past_days_data.append(day_data)

    result = {}
    for ticker, mentions_today in today_data.items():
        if not past_days_data:
            result[ticker] = {
                "mentions_today": mentions_today,
                "mentions_avg_5d": None,
                "trend": "NEW",
                "trend_pct": None,
            }
            continue

        past_vals = [d.get(ticker, 0) for d in past_days_data]
        avg = sum(past_vals) / len(past_vals)

        if avg == 0:
            trend = "NEW"
            trend_pct = None
        elif mentions_today > avg * 1.5:
            trend = "RISING"
            trend_pct = round((mentions_today - avg) / avg * 100, 1)
        elif mentions_today < avg * 0.5:
            trend = "FALLING"
            trend_pct = round((mentions_today - avg) / avg * 100, 1)
        else:
            trend = "STABLE"
            trend_pct = round((mentions_today - avg) / avg * 100, 1)

        result[ticker] = {
            "mentions_today": mentions_today,
            "mentions_avg_5d": round(avg, 1),
            "trend": trend,
            "trend_pct": trend_pct,
        }

    return result


# ── Vérification ticker réel ──────────────────────────────────────────────────

def verify_ticker(ticker: str, timeout: int = 5) -> bool:
    """
    Vérifie si un ticker est un vrai titre boursier via yfinance.

    - Retourne False immédiatement si le ticker fait < 2 caractères.
    - Retourne False si le ticker (normalisé en majuscules) est dans
      TICKER_BLACKLIST (mots courants, acronymes, jargon Reddit).
    - Cache le résultat en mémoire (_verify_cache) pour la durée du process.
    - Timeout de `timeout` secondes via threading (compatible Windows).
    - Retourne True si marketCap > 0 OU regularMarketPrice > 0.
    - À n'utiliser que sur les tickers hors watchlist connue pour éviter la
      latence réseau sur chaque appel.
    - Nécessite : pip install yfinance
    """
    # Filtres rapides — pas de réseau
    if len(ticker) < 2:
        return False

    from scrapers.reddit import TICKER_BLACKLIST  # import local pour éviter circulaire
    if ticker.upper() in TICKER_BLACKLIST:
        _verify_cache[ticker] = False
        return False

    if ticker in _verify_cache:
        return _verify_cache[ticker]

    is_valid = False
    try:
        import yfinance as yf

        result_holder = [False]

        def _check():
            try:
                info = yf.Ticker(ticker).info
                mcap = info.get("marketCap") or 0
                price = info.get("regularMarketPrice") or 0
                result_holder[0] = bool(mcap > 0 or price > 0)
            except Exception:
                result_holder[0] = False

        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=timeout)
        is_valid = result_holder[0]

    except ImportError:
        pass  # yfinance non installé → non vérifié
    except Exception:
        pass

    _verify_cache[ticker] = is_valid
    return is_valid
