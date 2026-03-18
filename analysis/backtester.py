"""
Backtester — Simule les 3 stratégies de trading sur données historiques yfinance.

Stratégies :
    DISCOUNT_ZONE    — prix dans zone discount 20j + au-dessus SMA200
    SMA200_BOUNCE    — rebond sur SMA200 en uptrend
    VOLUME_MOMENTUM  — volume 2x + bougie verte + breakout

Usage :
    from analysis.backtester import backtest_strategy, backtest_all_strategies
    result = backtest_strategy("NVDA", "SMA200_BOUNCE", period="3y")
    all3   = backtest_all_strategies("NVDA")
"""

from __future__ import annotations

import math
import warnings
from typing import Optional

warnings.filterwarnings("ignore")

STRATEGIES = ["DISCOUNT_ZONE", "SMA200_BOUNCE", "VOLUME_MOMENTUM"]
MAX_HOLD_DAYS = 20
MIN_STOP_PCT = 0.01   # stop < 1% du prix → skip


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sma(series, n: int):
    return series.rolling(n, min_periods=n).mean()


def _rolling_min(series, n: int):
    return series.rolling(n, min_periods=n).min()


def _rolling_max(series, n: int):
    return series.rolling(n, min_periods=n).max()


def _rolling_mean(series, n: int):
    return series.rolling(n, min_periods=n).mean()


def _max_drawdown(pnl_list: list[float]) -> float:
    peak = cum = 0.0
    max_dd = 0.0
    for p in pnl_list:
        cum  += p
        peak  = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return round(max_dd, 2)


def _profit_factor(pnls: list[float]) -> Optional[float]:
    gross_win  = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    return round(gross_win / gross_loss, 2) if gross_loss > 0 else None


def _expectancy_r(trades_list: list[dict]) -> Optional[float]:
    wins   = [t for t in trades_list if t["result"] == "WIN"]
    losses = [t for t in trades_list if t["result"] == "LOSS"]
    if not trades_list:
        return None
    risk_list = [abs(t["entry"] - t["stop"]) for t in trades_list if t["entry"] and t["stop"]]
    if not risk_list:
        return None
    avg_risk = sum(risk_list) / len(risk_list)
    if avg_risk == 0:
        return None
    total_pnl = sum(t["pnl"] for t in trades_list)
    return round(total_pnl / len(trades_list) / avg_risk, 2)


# ── Téléchargement + indicateurs ─────────────────────────────────────────────

def _load_data(ticker: str, period: str):
    """Télécharge l'historique et calcule tous les indicateurs nécessaires."""
    import yfinance as yf
    import pandas as pd

    df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    if df is None or len(df) < 50:
        return None

    df = df.dropna(subset=["Close", "Open", "High", "Low", "Volume"]).copy()

    df["sma200"]     = _sma(df["Close"], 200)
    df["sma50"]      = _sma(df["Close"], 50)
    df["vol_avg20"]  = _rolling_mean(df["Volume"], 20)
    df["high20"]     = _rolling_max(df["High"], 20)
    df["low20"]      = _rolling_min(df["Low"],  20)
    df["low5"]       = _rolling_min(df["Low"],  5)
    df["chg_pct"]    = df["Close"].pct_change() * 100

    # Date string pour les trades
    df["date_str"]   = df.index.strftime("%Y-%m-%d")

    return df


# ── Générateur de signaux ─────────────────────────────────────────────────────

def _signals_discount_zone(df) -> list[dict]:
    signals = []
    for i in range(200, len(df)):
        row = df.iloc[i]
        sma200 = row["sma200"]
        high20 = row["high20"]
        low20  = row["low20"]
        close  = row["Close"]

        if any(v != v or v is None for v in [sma200, high20, low20]):
            continue
        if high20 == low20:
            continue

        # Zone discount = 30% inférieurs du range 20j
        discount_threshold = low20 + 0.30 * (high20 - low20)
        if close > discount_threshold:
            continue
        if close <= sma200:
            continue

        entry = close
        stop  = row["low5"] * 0.995 if row["low5"] == row["low5"] else low20 * 0.995
        risk  = entry - stop

        if risk <= 0 or risk / entry < MIN_STOP_PCT:
            continue

        target = entry + 2.5 * risk
        signals.append({"i": i, "entry": entry, "stop": stop, "target": target, "date": row["date_str"]})

    return signals


def _signals_sma200_bounce(df) -> list[dict]:
    signals = []
    for i in range(200, len(df)):
        row   = df.iloc[i]
        sma200 = row["sma200"]
        sma50  = row["sma50"]
        close  = row["Close"]
        low    = row["Low"]

        if any(v != v for v in [sma200, sma50]):
            continue

        # Uptrend : SMA50 > SMA200
        if sma50 <= sma200:
            continue
        # Touche SMA200 (low <= SMA200 * 1.02) mais clôture au-dessus
        if low > sma200 * 1.02 or close <= sma200:
            continue

        entry = close
        stop  = sma200 * 0.985
        risk  = entry - stop

        if risk <= 0 or risk / entry < MIN_STOP_PCT:
            continue

        target = entry + 2.5 * risk
        signals.append({"i": i, "entry": entry, "stop": stop, "target": target, "date": row["date_str"]})

    return signals


def _signals_volume_momentum(df) -> list[dict]:
    signals = []
    for i in range(200, len(df)):
        row     = df.iloc[i]
        close   = row["Close"]
        open_   = row["Open"]
        volume  = row["Volume"]
        vol_avg = row["vol_avg20"]
        sma50   = row["sma50"]
        sma200  = row["sma200"]
        chg     = row["chg_pct"]
        low     = row["Low"]

        if any(v != v for v in [vol_avg, sma50, sma200, chg]):
            continue
        if vol_avg == 0:
            continue

        # Volume 2x + bougie verte + variation > 1.5% + au-dessus SMA50
        if volume < vol_avg * 2.0:
            continue
        if close <= open_:
            continue
        if chg < 1.5:
            continue
        if close <= sma50:
            continue
        # Pas trop étendu
        if close > sma200 * 1.15:
            continue

        entry = close
        stop  = low * 0.995
        risk  = entry - stop

        if risk <= 0 or risk / entry < MIN_STOP_PCT:
            continue

        target = entry + 2.5 * risk
        signals.append({"i": i, "entry": entry, "stop": stop, "target": target, "date": row["date_str"]})

    return signals


_SIGNAL_GENERATORS = {
    "DISCOUNT_ZONE":   _signals_discount_zone,
    "SMA200_BOUNCE":   _signals_sma200_bounce,
    "VOLUME_MOMENTUM": _signals_volume_momentum,
}


# ── Simulation de position ────────────────────────────────────────────────────

def _simulate_trades(df, signals: list[dict], capital: float, risk_pct: float) -> list[dict]:
    """
    Simule les trades en avançant jour par jour.
    Une seule position à la fois. Si un signal arrive pendant une position ouverte, on l'ignore.
    """
    trades      = []
    in_position = False
    cur_entry   = 0.0
    cur_stop    = 0.0
    cur_target  = 0.0
    cur_shares  = 0
    cur_open_i  = 0
    cur_date_open = ""

    # Index des signaux pour lookup rapide
    signal_by_i = {s["i"]: s for s in signals}

    for i in range(len(df)):
        row = df.iloc[i]

        if in_position:
            hold_days  = i - cur_open_i
            result     = None
            exit_price = 0.0

            if row["Low"] <= cur_stop:
                result     = "LOSS"
                exit_price = cur_stop
            elif row["High"] >= cur_target:
                result     = "WIN"
                exit_price = cur_target
            elif hold_days >= MAX_HOLD_DAYS:
                result     = "TIME"
                exit_price = float(row["Close"])

            if result:
                pnl = round((exit_price - cur_entry) * cur_shares, 2)
                trades.append({
                    "date_open":  cur_date_open,
                    "date_close": row["date_str"],
                    "entry":      round(cur_entry,  2),
                    "stop":       round(cur_stop,   2),
                    "target":     round(cur_target, 2),
                    "exit":       round(exit_price, 2),
                    "shares":     cur_shares,
                    "pnl":        pnl,
                    "result":     result,
                    "hold_days":  hold_days,
                })
                in_position = False

        if not in_position and i in signal_by_i:
            sig  = signal_by_i[i]
            risk = sig["entry"] - sig["stop"]
            if risk > 0:
                shares        = max(1, math.floor(capital * risk_pct / 100 / risk))
                in_position   = True
                cur_open_i    = i
                cur_entry     = sig["entry"]
                cur_stop      = sig["stop"]
                cur_target    = sig["target"]
                cur_shares    = shares
                cur_date_open = sig["date"]

    return trades


# ── Backtest principal ────────────────────────────────────────────────────────

def backtest_strategy(
    ticker:    str,
    strategy:  str,
    period:    str  = "3y",
    capital:   float = 10_000.0,
    risk_pct:  float = 1.0,
) -> dict:
    """
    Backtest mécanique d'une stratégie sur un ticker.
    Retourne les métriques complètes + liste des trades + equity curve.
    """
    _empty = {
        "ticker": ticker, "strategy": strategy, "period": period,
        "total_trades": 0, "wins": 0, "losses": 0, "time_exits": 0,
        "winrate": 0.0, "profit_factor": None, "total_pnl": 0.0,
        "avg_pnl": 0.0, "max_drawdown": 0.0, "avg_hold_days": 0.0,
        "best_trade": 0.0, "worst_trade": 0.0, "expectancy_r": None,
        "trades": [], "equity_curve": [],
        "error": None,
    }

    if strategy not in _SIGNAL_GENERATORS:
        return dict(_empty, error=f"Stratégie inconnue : {strategy}")

    try:
        df = _load_data(ticker, period)
        if df is None:
            return dict(_empty, error=f"Impossible de charger les données pour {ticker}")

        gen  = _SIGNAL_GENERATORS[strategy]
        sigs = gen(df)
        trades_list = _simulate_trades(df, sigs, capital, risk_pct)

        if not trades_list:
            return dict(_empty, error=None)  # 0 trades — pas une erreur

        wins       = [t for t in trades_list if t["result"] == "WIN"]
        losses     = [t for t in trades_list if t["result"] == "LOSS"]
        time_exits = [t for t in trades_list if t["result"] == "TIME"]
        pnls       = [t["pnl"] for t in trades_list]

        total_pnl  = round(sum(pnls), 2)
        winrate    = round(len(wins) / len(trades_list) * 100, 1)
        avg_pnl    = round(total_pnl / len(trades_list), 2)
        avg_hold   = round(sum(t["hold_days"] for t in trades_list) / len(trades_list), 1)

        # Equity curve
        cum = 0.0
        equity_curve = []
        for t in trades_list:
            cum += t["pnl"]
            equity_curve.append({"date": t["date_close"], "pnl": round(cum, 2)})

        return {
            "ticker":        ticker,
            "strategy":      strategy,
            "period":        period,
            "total_trades":  len(trades_list),
            "wins":          len(wins),
            "losses":        len(losses),
            "time_exits":    len(time_exits),
            "winrate":       winrate,
            "profit_factor": _profit_factor(pnls),
            "total_pnl":     total_pnl,
            "avg_pnl":       avg_pnl,
            "max_drawdown":  _max_drawdown(pnls),
            "avg_hold_days": avg_hold,
            "best_trade":    round(max(pnls), 2),
            "worst_trade":   round(min(pnls), 2),
            "expectancy_r":  _expectancy_r(trades_list),
            "trades":        trades_list,
            "equity_curve":  equity_curve,
            "error":         None,
        }

    except Exception as e:
        return dict(_empty, error=str(e))


# ── 3 stratégies sur 1 ticker ────────────────────────────────────────────────

def backtest_all_strategies(ticker: str, period: str = "3y", capital: float = 10_000.0) -> dict:
    """Lance les 3 stratégies sur le même ticker et retourne le comparatif."""
    results = {}
    for s in STRATEGIES:
        results[s] = backtest_strategy(ticker, s, period=period, capital=capital)

    # Meilleure stratégie par PnL total
    valid = {k: v for k, v in results.items() if not v.get("error") and v["total_trades"] > 0}
    best  = max(valid, key=lambda k: valid[k]["total_pnl"]) if valid else None

    return {
        "ticker":    ticker,
        "period":    period,
        "results":   results,
        "best_strategy": best,
        "summary": {
            s: {
                "total_trades":  results[s]["total_trades"],
                "winrate":       results[s]["winrate"],
                "profit_factor": results[s]["profit_factor"],
                "total_pnl":     results[s]["total_pnl"],
                "max_drawdown":  results[s]["max_drawdown"],
                "avg_hold_days": results[s]["avg_hold_days"],
            }
            for s in STRATEGIES
        },
    }


# ── 1 stratégie sur la watchlist ─────────────────────────────────────────────

def backtest_watchlist(
    tickers:  list[str],
    strategy: str,
    period:   str   = "3y",
    capital:  float = 10_000.0,
) -> dict:
    """Lance une stratégie sur tous les tickers et agrège les résultats."""
    by_ticker = {}
    all_trades = []

    for ticker in tickers:
        r = backtest_strategy(ticker, strategy, period=period, capital=capital)
        by_ticker[ticker] = r
        all_trades.extend(r.get("trades", []))

    total_trades  = sum(r["total_trades"]  for r in by_ticker.values())
    wins          = sum(r["wins"]          for r in by_ticker.values())
    total_pnl     = round(sum(r["total_pnl"]   for r in by_ticker.values()), 2)
    all_pnls      = [t["pnl"] for t in all_trades]

    return {
        "strategy":      strategy,
        "period":        period,
        "tickers_count": len(tickers),
        "by_ticker":     by_ticker,
        "aggregate": {
            "total_trades":  total_trades,
            "wins":          wins,
            "losses":        total_trades - wins,
            "winrate":       round(wins / total_trades * 100, 1) if total_trades else 0.0,
            "profit_factor": _profit_factor(all_pnls),
            "total_pnl":     total_pnl,
            "avg_pnl_trade": round(total_pnl / total_trades, 2) if total_trades else 0.0,
            "max_drawdown":  _max_drawdown(all_pnls),
        },
    }


# ── Rapport complet ──────────────────────────────────────────────────────────

def backtest_full_report(tickers: list[str], period: str = "3y", capital: float = 10_000.0) -> dict:
    """
    Lance les 3 stratégies sur tous les tickers.
    Identifie la meilleure stratégie globalement et les meilleurs tickers par stratégie.
    """
    by_strategy = {}
    by_ticker   = {t: {} for t in tickers}

    print(f"[Backtest] {len(tickers)} tickers × 3 stratégies = {len(tickers)*3} backtests...")

    for strategy in STRATEGIES:
        print(f"[Backtest] Stratégie {strategy}...")
        wl = backtest_watchlist(tickers, strategy, period=period, capital=capital)
        by_strategy[strategy] = wl["aggregate"]
        for ticker in tickers:
            r = wl["by_ticker"].get(ticker, {})
            by_ticker[ticker][strategy] = {
                "total_trades":  r.get("total_trades", 0),
                "winrate":       r.get("winrate", 0.0),
                "profit_factor": r.get("profit_factor"),
                "total_pnl":     r.get("total_pnl", 0.0),
                "equity_curve":  r.get("equity_curve", []),
            }

    # Meilleure stratégie globale par PnL
    best_strategy = max(
        STRATEGIES,
        key=lambda s: by_strategy[s]["total_pnl"] if by_strategy.get(s) else -99999,
    )

    # Meilleur ticker par stratégie
    best_ticker_per_strategy = {}
    for strategy in STRATEGIES:
        best = max(
            tickers,
            key=lambda t: by_ticker[t][strategy]["total_pnl"],
        )
        best_ticker_per_strategy[strategy] = best

    # Recommandation
    bs = by_strategy[best_strategy]
    rec = (
        f"Meilleure stratégie : {best_strategy} — "
        f"WR {bs['winrate']}%, PF {bs['profit_factor']}, "
        f"PnL total +${bs['total_pnl']:,.0f} sur {period}"
    )

    return {
        "period":                    period,
        "tickers":                   tickers,
        "by_strategy":               by_strategy,
        "by_ticker":                 by_ticker,
        "best_strategy":             best_strategy,
        "best_ticker_per_strategy":  best_ticker_per_strategy,
        "recommendation":            rec,
    }


# ── Test __main__ ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Backtest NVDA — 3 stratégies sur 3 ans ===\n")
    report = backtest_all_strategies("NVDA", period="3y")

    print(f"{'Stratégie':<20} {'Trades':>6} {'WR%':>6} {'PF':>6} {'PnL':>10} {'MaxDD':>10} {'Hold':>6}")
    print("-" * 68)
    for s in STRATEGIES:
        r = report["summary"][s]
        pf   = f"{r['profit_factor']:.2f}" if r["profit_factor"] else "N/A"
        pnl  = f"+${r['total_pnl']:,.0f}" if r["total_pnl"] >= 0 else f"-${abs(r['total_pnl']):,.0f}"
        dd   = f"-${abs(r['max_drawdown']):,.0f}"
        mark = " <-- MEILLEURE" if s == report["best_strategy"] else ""
        print(f"{s:<20} {r['total_trades']:>6} {r['winrate']:>5.1f}% {pf:>6} {pnl:>10} {dd:>10} {r['avg_hold_days']:>5.1f}j{mark}")

    print(f"\nMeilleure stratégie : {report['best_strategy']}")
