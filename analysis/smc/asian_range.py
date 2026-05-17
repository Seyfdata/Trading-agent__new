"""
analysis.smc.asian_range — Sessions & Timezone, Asian Range, Liquidity Sweeps.

Détecte la plage de référence overnight et les sweeps de liquidité sur données intraday.
"""
from __future__ import annotations

from datetime import timedelta

from core.data_provider import get_history

_TZ_PARIS = "Europe/Paris"

try:
    import yfinance as _yf
    _YF_OK = True
except ImportError:
    _yf = None
    _YF_OK = False

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False


def detect_asian_range(ticker: str) -> dict:
    """
    Plage de reference overnight pour actions US (proxy session Asie).

    Les actions US ne tradent pas 01h-06h CET. On utilise donc :
    1. prepost=True : after-hours (>=22h CET) hier + pre-market (<10h CET) auj.
    2. Fallback : High/Low de la veille si pas de donnees overnight.
    """
    empty = {"high": None, "low": None, "date": None, "valid": False, "source_bars": 0}
    if not _YF_OK or not _PANDAS_OK:
        return empty
    try:
        # prepost=True nécessaire pour les données overnight — appel direct yfinance
        df = _yf.Ticker(ticker).history(period="5d", interval="1h", prepost=True)
        if df is None or df.empty:
            return empty

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(_TZ_PARIS)
        else:
            df.index = df.index.tz_convert(_TZ_PARIS)

        today = df.index[-1].date()

        for delta in range(0, 5):
            target_date = today - timedelta(days=delta)
            prev_date   = target_date - timedelta(days=1)
            overnight = df[
                ((df.index.date == prev_date) & (df.index.hour >= 22)) |
                ((df.index.date == target_date) & (df.index.hour < 10))
            ]
            if len(overnight) >= 1:
                h = round(float(overnight["High"].max()), 2)
                l = round(float(overnight["Low"].min()),  2)
                result = {"high": h, "low": l, "date": str(target_date), "valid": True, "source_bars": len(overnight)}
                print(f"[SMC-Logic] Asian Range {ticker}: H={h:.2f} L={l:.2f} ({target_date}, {len(overnight)} bars overnight)")
                return result

        # Fallback : plage J-1 via data_provider (cache 5 min)
        df_daily = get_history(ticker, interval="1d", period="5d")
        if df_daily is not None and len(df_daily) >= 2:
            prev = df_daily.iloc[-2]
            h = round(float(prev["High"]), 2)
            l = round(float(prev["Low"]),  2)
            d = str(df_daily.index[-2])[:10]
            result = {"high": h, "low": l, "date": d, "valid": True, "source_bars": 1}
            print(f"[SMC-Logic] Asian Range {ticker} (J-1 fallback): H={h:.2f} L={l:.2f}")
            return result

        return empty
    except Exception as exc:
        print(f"[SMC-Logic] detect_asian_range error {ticker}: {exc}")
        return empty


def detect_liquidity_sweeps(ticker: str, asian_range: dict) -> list:
    """
    Détecte les sweeps de liquidité sur données 1h post-session Asie.

    Sweep BSL (Buy-Side Liquidity) : High[i] > asian_high ET Close[i] < asian_high
    Sweep SSL (Sell-Side Liquidity) : Low[i]  < asian_low  ET Close[i] > asian_low
    """
    sweeps: list[dict] = []
    if not asian_range.get("valid") or not _PANDAS_OK:
        return sweeps

    asian_high = float(asian_range["high"])
    asian_low  = float(asian_range["low"])
    asia_date  = asian_range["date"]

    try:
        df = get_history(ticker, interval="1h", period="5d")
        if df is None or df.empty:
            return sweeps

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(_TZ_PARIS)
        else:
            df.index = df.index.tz_convert(_TZ_PARIS)

        # Bars AFTER the Asian session (hour >= 6 on the same day or later)
        post_asia = df[
            (df.index.strftime("%Y-%m-%d") >= str(asia_date)) &
            (df.index.hour >= 6)
        ]

        for i in range(len(post_asia)):
            bar      = post_asia.iloc[i]
            bar_time = post_asia.index[i]
            bar_h    = float(bar["High"])
            bar_l    = float(bar["Low"])
            bar_c    = float(bar["Close"])

            # BSL sweep : wick above Asian High, but closes below
            if bar_h > asian_high and bar_c < asian_high:
                rejection_pct = round((bar_h - bar_c) / bar_h * 100, 2)
                sweeps.append({
                    "type":           "BSL",
                    "price":          round(bar_h, 2),
                    "close":          round(bar_c, 2),
                    "asian_level":    asian_high,
                    "date":           bar_time.strftime("%Y-%m-%dT%H:%M"),
                    "bar_idx":        i,
                    "rejection_pct":  rejection_pct,
                })
                print(f"[SMC-Logic] Asian Sweep BSL detected for {ticker} at {bar_h:.2f} (close={bar_c:.2f}, rejection={rejection_pct}%)")

            # SSL sweep : wick below Asian Low, but closes above
            elif bar_l < asian_low and bar_c > asian_low:
                rejection_pct = round((bar_c - bar_l) / bar_c * 100, 2)
                sweeps.append({
                    "type":           "SSL",
                    "price":          round(bar_l, 2),
                    "close":          round(bar_c, 2),
                    "asian_level":    asian_low,
                    "date":           bar_time.strftime("%Y-%m-%dT%H:%M"),
                    "bar_idx":        i,
                    "rejection_pct":  rejection_pct,
                })
                print(f"[SMC-Logic] Asian Sweep SSL detected for {ticker} at {bar_l:.2f} (close={bar_c:.2f}, rejection={rejection_pct}%)")

    except Exception as exc:
        print(f"[SMC-Logic] detect_liquidity_sweeps error {ticker}: {exc}")

    return sweeps
