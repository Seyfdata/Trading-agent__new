"""
Module Market Data PRO — Données de marché + analyse technique.

5 niveaux d'analyse pour le Morning Brief PRO :
  1. Market Context : SPY, QQQ, VIX, DXY, US10Y + verdict
  2. Watchlist Scanner : prix, variation, SMA200, volume relatif
  3. Technical Analysis : RSI, MACD, Bollinger, ADX par ticker
  4. Bullish Score : score composite 0-10 par ticker (inspiré staskh)
  5. Setup Candidates : tickers à regarder en priorité + earnings check

Prérequis :
  pip install yfinance pandas numpy

Note : pandas_ta est optionnel. Si non installé, on calcule
les indicateurs manuellement (RSI, SMA, EMA, MACD).
"""

import numpy as np

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

try:
    import pandas as pd
    PD_AVAILABLE = True
except ImportError:
    PD_AVAILABLE = False

from config.settings import (
    WATCHLIST, EMOJI_CHART, EMOJI_BULL, EMOJI_BEAR, EMOJI_NEUTRAL,
    EMOJI_WARNING, EMOJI_FIRE, EMOJI_CHECK, EMOJI_NO
)


# =============================================
# INDICATEURS TECHNIQUES (sans pandas_ta)
# =============================================

def calc_sma(series, period):
    """Simple Moving Average."""
    if len(series) < period:
        return None
    return series.rolling(window=period).mean().iloc[-1]


def calc_ema(series, period):
    """Exponential Moving Average."""
    if len(series) < period:
        return None
    return series.ewm(span=period, adjust=False).mean().iloc[-1]


def calc_rsi(series, period=14):
    """Relative Strength Index."""
    if len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else None


def calc_macd(series, fast=12, slow=26, signal=9):
    """MACD line, signal line, histogram."""
    if len(series) < slow + signal:
        return None, None, None, None
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float(histogram.iloc[-1]),
        float(histogram.iloc[-2]) if len(histogram) > 1 else None,
    )


def calc_bollinger(series, period=20, std_dev=2):
    """Bollinger Bands."""
    if len(series) < period:
        return None, None, None
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return float(lower.iloc[-1]), float(sma.iloc[-1]), float(upper.iloc[-1])


def calc_atr(high, low, close, period=14):
    """Average True Range."""
    if len(close) < period + 1:
        return None
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    val = atr.iloc[-1]
    return float(val) if pd.notna(val) else None


def calc_adx(high, low, close, period=14):
    """ADX + DI+ et DI-."""
    if len(close) < period * 2:
        return None, None, None

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(window=period).mean()

    adx_val = adx.iloc[-1]
    plus_val = plus_di.iloc[-1]
    minus_val = minus_di.iloc[-1]

    return (
        float(adx_val) if pd.notna(adx_val) else None,
        float(plus_val) if pd.notna(plus_val) else None,
        float(minus_val) if pd.notna(minus_val) else None,
    )


# =============================================
# NIVEAU 1 — MARKET CONTEXT
# =============================================

MACRO_TICKERS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "^VIX": "VIX",
    "DX-Y.NYB": "Dollar (DXY)",
    "^TNX": "US 10Y Yield",
}


def get_market_context():
    """Récupère SPY, QQQ, VIX, DXY, US10Y."""
    if not YF_AVAILABLE:
        return None

    context = {}
    for ticker, name in MACRO_TICKERS.items():
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="5d")
            if hist.empty or len(hist) < 2:
                continue
            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
            change_pct = ((current - prev) / prev) * 100
            context[ticker] = {
                "name": name,
                "price": round(current, 2),
                "change_pct": round(change_pct, 2),
            }
        except Exception:
            pass
    return context


def format_market_context(context):
    """Formate la section Market Context."""
    if context is None:
        return None

    lines = [f"{EMOJI_CHART} *MARKET CONTEXT*", ""]
    for ticker in ["SPY", "QQQ", "^VIX", "DX-Y.NYB", "^TNX"]:
        info = context.get(ticker)
        if not info:
            continue
        price = info["price"]
        change = info["change_pct"]
        name = info["name"]
        emoji = EMOJI_BULL if change > 0 else EMOJI_BEAR if change < 0 else EMOJI_NEUTRAL
        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
        lines.append(f"{emoji} *{name}* : {price} ({arrow}{change:+.2f}%)")

    # VIX interpretation
    vix = context.get("^VIX", {})
    if "price" in vix:
        v = vix["price"]
        if v < 15:
            lines.append(f"\n{EMOJI_CHECK} *VIX CALME* ({v:.1f}) — trading normal")
        elif v < 20:
            lines.append(f"\n{EMOJI_CHECK} *VIX NORMAL* ({v:.1f}) — GO")
        elif v < 25:
            lines.append(f"\n{EMOJI_WARNING} *VIX ÉLEVÉ* ({v:.1f}) — risque 0.5% max")
        elif v < 30:
            lines.append(f"\n{EMOJI_NO} *VIX HAUT* ({v:.1f}) — NO TRADE recommandé")
        else:
            lines.append(f"\n{EMOJI_NO} *VIX EXTRÊME* ({v:.1f}) — NE PAS TRADER")

    # Verdict global
    spy = context.get("SPY", {})
    vix_p = vix.get("price", 20)
    spy_c = spy.get("change_pct", 0)
    if vix_p > 25:
        lines.append(f"{EMOJI_NO} *MARCHÉ : DANGER*")
    elif vix_p > 20 and spy_c < -1:
        lines.append(f"{EMOJI_WARNING} *MARCHÉ : PRUDENCE*")
    elif spy_c > 0.5 and vix_p < 20:
        lines.append(f"{EMOJI_CHECK} *MARCHÉ : FAVORABLE*")
    else:
        lines.append(f"{EMOJI_NEUTRAL} *MARCHÉ : NEUTRE*")

    return "\n".join(lines)


# =============================================
# NIVEAU 2 — WATCHLIST SCANNER
# =============================================

def scan_watchlist(tickers=None):
    """Scanne chaque ticker : prix, variation, SMA200, volume."""
    if not YF_AVAILABLE:
        return None
    if tickers is None:
        tickers = WATCHLIST

    results = []
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="1y")
            if hist.empty or len(hist) < 10:
                continue

            current = hist["Close"].iloc[-1]
            prev_day = hist["Close"].iloc[-2]
            prev_week = hist["Close"].iloc[-6] if len(hist) > 6 else prev_day

            change_day = ((current - prev_day) / prev_day) * 100
            change_week = ((current - prev_week) / prev_week) * 100

            sma200 = calc_sma(hist["Close"], 200)
            dist_sma200 = ((current - sma200) / sma200) * 100 if sma200 else None
            above_sma200 = current > sma200 if sma200 else None

            vol_today = hist["Volume"].iloc[-1]
            vol_avg_20 = hist["Volume"].tail(20).mean()
            vol_relative = vol_today / vol_avg_20 if vol_avg_20 > 0 else 1.0

            results.append({
                "ticker": ticker,
                "price": round(current, 2),
                "change_day": round(change_day, 2),
                "change_week": round(change_week, 2),
                "sma200": round(sma200, 2) if sma200 else None,
                "dist_sma200": round(dist_sma200, 1) if dist_sma200 is not None else None,
                "above_sma200": above_sma200,
                "vol_relative": round(vol_relative, 2),
            })
        except Exception:
            pass
    return results


def format_watchlist_scanner(results):
    """Formate la section Watchlist Scanner."""
    if not results:
        return None

    lines = [f"{EMOJI_CHART} *WATCHLIST SCANNER*", ""]
    for r in results:
        t = r["ticker"]
        p = r["price"]
        d = r["change_day"]
        w = r["change_week"]
        vol = r["vol_relative"]
        dist = r.get("dist_sma200")
        above = r.get("above_sma200")

        emoji = EMOJI_BULL if d > 1 else EMOJI_BEAR if d < -1 else EMOJI_NEUTRAL
        sma_text = ""
        if dist is not None:
            sma_icon = "✅" if above else "⚠️"
            sma_text = f" | SMA200:{sma_icon}{dist:+.1f}%"
        vol_text = ""
        if vol > 1.5:
            vol_text = f" | Vol:🔥x{vol:.1f}"
        elif vol > 1.2:
            vol_text = f" | Vol:↑x{vol:.1f}"

        lines.append(f"{emoji} *{t}* {p}$ | J:{d:+.1f}% | S:{w:+.1f}%{sma_text}{vol_text}")

    return "\n".join(lines)


# =============================================
# NIVEAU 3 — TECHNICAL ANALYSIS
# =============================================

def analyze_technicals(ticker_symbol):
    """Analyse technique complète pour un ticker."""
    try:
        data = yf.Ticker(ticker_symbol)
        hist = data.history(period="3mo")
        if hist.empty or len(hist) < 30:
            return None

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]

        rsi = calc_rsi(close)
        macd_line, macd_signal, macd_hist, prev_hist = calc_macd(close)
        bb_lower, bb_mid, bb_upper = calc_bollinger(close)
        atr = calc_atr(high, low, close)
        adx, dmp, dmn = calc_adx(high, low, close)

        signals = []

        # RSI signals
        if rsi is not None:
            if rsi > 70:
                signals.append(("RSI", "SURACHAT", rsi))
            elif rsi < 30:
                signals.append(("RSI", "SURVENDU", rsi))
            elif 50 <= rsi <= 70:
                signals.append(("RSI", "BULLISH", rsi))

        # MACD signals
        if macd_hist is not None and prev_hist is not None:
            if prev_hist < 0 and macd_hist > 0:
                signals.append(("MACD", "CROSS HAUSSIER", macd_hist))
            elif prev_hist > 0 and macd_hist < 0:
                signals.append(("MACD", "CROSS BAISSIER", macd_hist))
            elif macd_hist > 0:
                signals.append(("MACD", "POSITIF", macd_hist))

        # Bollinger signals
        current = close.iloc[-1]
        if bb_lower is not None:
            if current < bb_lower:
                signals.append(("BB", "SOUS BANDE INF", current))
            elif current > bb_upper:
                signals.append(("BB", "AU-DESSUS BANDE SUP", current))

        # ADX signals
        if adx is not None:
            if adx > 25 and dmp > dmn:
                signals.append(("ADX", "TENDANCE HAUSSIÈRE FORTE", adx))
            elif adx > 25 and dmn > dmp:
                signals.append(("ADX", "TENDANCE BAISSIÈRE FORTE", adx))
            elif adx < 20:
                signals.append(("ADX", "PAS DE TENDANCE", adx))

        return {
            "ticker": ticker_symbol,
            "rsi": round(rsi, 1) if rsi else None,
            "macd": round(macd_line, 4) if macd_line else None,
            "macd_signal": round(macd_signal, 4) if macd_signal else None,
            "macd_hist": round(macd_hist, 4) if macd_hist else None,
            "bb_lower": round(bb_lower, 2) if bb_lower else None,
            "bb_upper": round(bb_upper, 2) if bb_upper else None,
            "atr": round(atr, 2) if atr else None,
            "adx": round(adx, 1) if adx else None,
            "signals": signals,
        }
    except Exception:
        return None


# =============================================
# NIVEAU 4 — BULLISH SCORE (inspiré staskh)
# =============================================

def compute_bullish_score(ticker_symbol, scan_result=None):
    """
    Score composite bullish 0-10 pour un ticker.
    Inspiré de staskh/trading_skills/scanner_bullish.py

    Composantes :
    - Prix > SMA20 : +1 | Prix > SMA50 : +1
    - RSI 50-70 (bullish healthy) : +1
    - MACD > signal : +1 | histogram en hausse : +0.5
    - ADX > 25 avec DI+ > DI- : +1.5
    - Momentum (% change 3 mois) : jusqu'à +2
    - Prix > SMA200 : +1
    - Volume relatif > 1.5 : +0.5
    """
    try:
        data = yf.Ticker(ticker_symbol)
        hist = data.history(period="3mo")
        if hist.empty or len(hist) < 30:
            return None

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        current = close.iloc[-1]

        score = 0.0
        signals = []

        # SMA
        sma20 = calc_sma(close, 20)
        sma50 = calc_sma(close, 50)

        if sma20 and current > sma20:
            score += 1.0
            signals.append("Above SMA20")
        if sma50 and current > sma50:
            score += 1.0
            signals.append("Above SMA50")

        # SMA200 (from scan_result if available)
        if scan_result and scan_result.get("above_sma200"):
            score += 1.0
            signals.append("Above SMA200")

        # RSI
        rsi = calc_rsi(close)
        if rsi is not None:
            if 50 <= rsi <= 70:
                score += 1.0
                signals.append(f"RSI bullish ({rsi:.0f})")
            elif 30 <= rsi < 50:
                score += 0.5
                signals.append(f"RSI neutral ({rsi:.0f})")
            elif rsi < 30:
                score += 0.25
                signals.append(f"RSI oversold ({rsi:.0f})")

        # MACD
        macd_line, macd_signal, macd_hist, prev_hist = calc_macd(close)
        if macd_line is not None and macd_signal is not None:
            if macd_line > macd_signal:
                score += 1.0
                signals.append("MACD > signal")
        if macd_hist is not None and prev_hist is not None:
            if macd_hist > prev_hist:
                score += 0.5
                signals.append("MACD momentum ↑")

        # ADX
        adx, dmp, dmn = calc_adx(high, low, close)
        if adx is not None and dmp is not None and dmn is not None:
            if adx > 25 and dmp > dmn:
                score += 1.5
                signals.append(f"Strong trend (ADX={adx:.0f})")
            elif dmp > dmn:
                score += 0.5
                signals.append("Bullish direction")

        # Momentum
        period_return = (current / close.iloc[0] - 1) * 100
        momentum_bonus = min(max(period_return / 20, -1), 2)
        score += momentum_bonus

        # Volume bonus
        if scan_result and scan_result.get("vol_relative", 0) > 1.5:
            score += 0.5
            signals.append("High volume")

        # Earnings check
        earnings_date = None
        try:
            cal = data.calendar
            if cal and isinstance(cal, dict):
                e_list = cal.get("Earnings Date")
                if e_list and len(e_list) > 0:
                    earnings_date = str(e_list[0])[:10]
        except Exception:
            pass

        return {
            "ticker": ticker_symbol,
            "score": round(min(score, 10), 1),
            "signals": signals,
            "rsi": round(rsi, 1) if rsi else None,
            "adx": round(adx, 1) if adx else None,
            "momentum_3m": round(period_return, 1),
            "earnings_date": earnings_date,
        }
    except Exception:
        return None


# =============================================
# NIVEAU 5 — SETUP CANDIDATES
# =============================================

def find_setup_candidates(scan_results, bullish_scores=None):
    """Identifie les tickers à regarder EN PRIORITÉ."""
    if not scan_results:
        return None

    candidates = []
    scores_dict = {}
    if bullish_scores:
        scores_dict = {b["ticker"]: b for b in bullish_scores if b}

    for r in scan_results:
        reasons = []
        priority = 0
        ticker = r["ticker"]
        bs = scores_dict.get(ticker, {})

        # Bullish score élevé
        bull_score = bs.get("score", 0)
        if bull_score >= 6:
            reasons.append(f"Score bullish {bull_score}/10")
            priority += 3
        elif bull_score >= 4:
            reasons.append(f"Score bullish {bull_score}/10")
            priority += 1

        # Discount
        if r["change_week"] < -3:
            reasons.append(f"Discount {r['change_week']:.1f}% semaine")
            priority += 2

        # Volume anormal
        if r["vol_relative"] > 1.5:
            reasons.append(f"Volume x{r['vol_relative']:.1f}")
            priority += 2

        # RSI oversold
        rsi = bs.get("rsi")
        if rsi and rsi < 35:
            reasons.append(f"RSI oversold ({rsi:.0f})")
            priority += 2

        # Proche SMA200
        dist = r.get("dist_sma200")
        if dist is not None and abs(dist) < 3 and r.get("above_sma200"):
            reasons.append(f"Proche SMA200 ({dist:+.1f}%)")
            priority += 1

        # Sous SMA200
        if r.get("above_sma200") is False:
            reasons.append(f"Sous SMA200 ({dist:+.1f}%)")
            priority += 1

        # Earnings warning
        earn = bs.get("earnings_date")
        if earn:
            reasons.append(f"Earnings: {earn}")

        if reasons:
            candidates.append({
                "ticker": ticker,
                "price": r["price"],
                "priority": priority,
                "bull_score": bull_score,
                "reasons": reasons,
            })

    candidates.sort(key=lambda x: x["priority"], reverse=True)
    return candidates


def format_setup_candidates(candidates):
    """Formate les Setup Candidates."""
    if not candidates:
        return None

    high = [c for c in candidates if c["priority"] >= 3]
    medium = [c for c in candidates if 1 <= c["priority"] < 3]

    lines = [f"{EMOJI_FIRE} *SETUP CANDIDATES*", ""]

    if not high and not medium:
        lines.append("Aucun candidat aujourd'hui.")
        lines.append("Patience = edge.")
        return "\n".join(lines)

    if high:
        lines.append("*PRIORITÉ HAUTE :*")
        for c in high[:3]:
            score_text = f" | Bull:{c['bull_score']}/10" if c['bull_score'] > 0 else ""
            lines.append(f"  {EMOJI_FIRE} *{c['ticker']}* ({c['price']}$){score_text}")
            for reason in c["reasons"][:3]:
                lines.append(f"    → {reason}")
        lines.append("")

    if medium:
        lines.append("*À SURVEILLER :*")
        for c in medium[:3]:
            reasons_short = c["reasons"][0]
            lines.append(f"  👀 *{c['ticker']}* — {reasons_short}")

    lines.extend([
        "",
        f"{EMOJI_WARNING} *Ouvre TradingView → analyse SMC → setup valide = trade*",
    ])
    return "\n".join(lines)


# =============================================
# TOUT-EN-UN
# =============================================

def get_full_market_brief():
    """Lance les 5 niveaux et retourne les textes formatés."""
    if not YF_AVAILABLE:
        print("  [Market] yfinance non installé. Lance : pip install yfinance")
        return None, None, None

    # Niveau 1
    print("     Niveau 1 : Market Context...")
    context = get_market_context()
    market_text = format_market_context(context)

    # Niveau 2
    print("     Niveau 2 : Watchlist Scanner...")
    scan = scan_watchlist()
    watchlist_text = format_watchlist_scanner(scan)

    # Niveau 3+4 : Technical + Bullish Score (combiné)
    print("     Niveau 3-4 : Technical Analysis + Bullish Scores...")
    bullish_scores = []
    if scan:
        for r in scan:
            bs = compute_bullish_score(r["ticker"], scan_result=r)
            if bs:
                bullish_scores.append(bs)
                score_emoji = EMOJI_BULL if bs["score"] >= 6 else EMOJI_NEUTRAL if bs["score"] >= 3 else EMOJI_BEAR
                print(f"       {score_emoji} {bs['ticker']}: {bs['score']}/10 — {', '.join(bs['signals'][:3])}")

    # Niveau 5
    print("     Niveau 5 : Setup Candidates...")
    candidates = find_setup_candidates(scan, bullish_scores)
    candidates_text = format_setup_candidates(candidates)

    return market_text, watchlist_text, candidates_text


# === TEST ===
if __name__ == "__main__":
    print("=== TEST MARKET DATA PRO ===\n")
    if not YF_AVAILABLE:
        print("yfinance non installé")
    else:
        market, watchlist, candidates = get_full_market_brief()
        if market:
            print("\n" + market)
        if watchlist:
            print("\n" + watchlist)
        if candidates:
            print("\n" + candidates)
