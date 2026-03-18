"""
Advanced Metrics — Métriques avancées de performance de trading.

Fonctions :
    calculate_sharpe_ratio(trades)         → float | None
    calculate_sortino_ratio(trades)        → float | None
    calculate_calmar_ratio(trades)         → float | None
    calculate_expectancy(trades)           → dict
    monte_carlo_simulation(trades)         → dict | None
    calculate_all_advanced_metrics(trades) → dict

Usage :
    from analysis.advanced_metrics import calculate_all_advanced_metrics
    result = calculate_all_advanced_metrics(trades)
"""

from __future__ import annotations

import math
import random
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trade_returns(trades: list[dict]) -> list[float]:
    """Retourne la liste des returns par trade (pnl / capital engagé)."""
    returns = []
    for t in trades:
        pnl   = t.get("pnl_dollars") or 0.0
        entry = t.get("entry_price") or 0.0
        shares = t.get("shares") or t.get("quantity") or 0.0
        capital = entry * shares
        if capital > 0:
            returns.append(pnl / capital)
    return returns


def _pnl_list(trades: list[dict]) -> list[float]:
    return [float(t.get("pnl_dollars") or 0.0) for t in trades]


def _max_drawdown_from_pnls(pnls: list[float]) -> float:
    """Max drawdown absolu (valeur négative) depuis une séquence de PnL."""
    peak = 0.0
    cum  = 0.0
    max_dd = 0.0
    for p in pnls:
        cum  += p
        peak  = max(peak, cum)
        dd    = cum - peak
        max_dd = min(max_dd, dd)
    return max_dd


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


# ── Sharpe Ratio ──────────────────────────────────────────────────────────────

def calculate_sharpe_ratio(
    trades: list[dict],
    risk_free_rate: float = 0.04,
) -> Optional[float]:
    """
    Sharpe annualisé = (mean(returns) - rf_daily) / std(returns) * sqrt(252)
    Retourne None si < 10 trades.
    """
    if len(trades) < 10:
        return None
    returns = _trade_returns(trades)
    if not returns:
        return None
    rf_daily = risk_free_rate / 252
    std = _std(returns)
    if std == 0:
        return None
    sharpe = (_mean(returns) - rf_daily) / std * math.sqrt(252)
    return round(sharpe, 2)


# ── Sortino Ratio ─────────────────────────────────────────────────────────────

def calculate_sortino_ratio(
    trades: list[dict],
    risk_free_rate: float = 0.04,
) -> Optional[float]:
    """
    Sortino annualisé = (mean(returns) - rf_daily) / downside_std * sqrt(252)
    Downside std = écart-type des returns négatifs uniquement.
    Retourne None si < 10 trades.
    """
    if len(trades) < 10:
        return None
    returns = _trade_returns(trades)
    if not returns:
        return None
    rf_daily = risk_free_rate / 252
    negative = [r for r in returns if r < 0]
    if not negative:
        return None
    downside_std = _std(negative)
    if downside_std == 0:
        return None
    sortino = (_mean(returns) - rf_daily) / downside_std * math.sqrt(252)
    return round(sortino, 2)


# ── Calmar Ratio ──────────────────────────────────────────────────────────────

def calculate_calmar_ratio(trades: list[dict]) -> Optional[float]:
    """
    Calmar = retour annualisé / |max drawdown absolu|
    Retourne None si < 10 trades ou max drawdown = 0.
    """
    if len(trades) < 10:
        return None
    returns = _trade_returns(trades)
    if not returns:
        return None
    annual_return = _mean(returns) * 252
    pnls = _pnl_list(trades)
    max_dd = _max_drawdown_from_pnls(pnls)
    if max_dd >= 0:
        return None
    calmar = annual_return / abs(max_dd)
    return round(calmar, 2)


# ── Expectancy ────────────────────────────────────────────────────────────────

def calculate_expectancy(trades: list[dict]) -> dict:
    """
    Retourne : avg_win, avg_loss, winrate, expectancy, expectancy_per_r, edge_ratio.
    """
    if not trades:
        return {}

    pnls   = _pnl_list(trades)
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    avg_win    = round(_mean(wins),          2) if wins   else 0.0
    avg_loss   = round(abs(_mean(losses)),   2) if losses else 0.0
    winrate    = round(len(wins) / len(pnls), 4)
    expectancy = round(winrate * avg_win - (1 - winrate) * avg_loss, 2)
    edge_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else None

    # Expectancy per R (normalisé par le risque moyen)
    rr_vals = [t.get("rr_realized") for t in trades if t.get("rr_realized") is not None]
    avg_r   = round(_mean([abs(r) for r in rr_vals]), 2) if rr_vals else None
    if avg_r and avg_r > 0:
        expectancy_per_r = round(expectancy / avg_r, 2)
    else:
        # Fallback : normalise par avg_loss comme proxy de 1R
        expectancy_per_r = round(expectancy / avg_loss, 2) if avg_loss > 0 else None

    return {
        "avg_win":          avg_win,
        "avg_loss":         avg_loss,
        "winrate":          round(winrate * 100, 1),
        "expectancy":       expectancy,
        "expectancy_per_r": expectancy_per_r,
        "edge_ratio":       edge_ratio,
    }


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def monte_carlo_simulation(
    trades: list[dict],
    n_simulations: int = 1000,
    n_trades: int = 100,
    capital: float = 10_000.0,
) -> Optional[dict]:
    """
    Simule n_simulations séquences de n_trades tirés au hasard (avec remplacement).
    Retourne None si < 20 trades.

    Retourne :
        median_pnl, pnl_5th, pnl_95th,
        median_dd, worst_dd,
        prob_profitable, prob_ruin,
        equity_curves (50 premières courbes pour graphique)
    """
    if len(trades) < 20:
        return None

    pnls = _pnl_list(trades)

    final_pnls = []
    max_dds    = []
    equity_curves = []

    for i in range(n_simulations):
        seq = random.choices(pnls, k=n_trades)
        # Equity curve de cette simulation
        curve  = []
        cum    = 0.0
        peak   = 0.0
        max_dd = 0.0
        for p in seq:
            cum  += p
            peak  = max(peak, cum)
            dd    = cum - peak
            max_dd = min(max_dd, dd)
            curve.append(round(cum, 2))
        final_pnls.append(cum)
        max_dds.append(max_dd)
        if i < 50:
            equity_curves.append(curve)

    # Trier pour percentiles
    sorted_pnls = sorted(final_pnls)
    sorted_dds  = sorted(max_dds)   # tous négatifs ou 0

    idx_5  = max(0, int(n_simulations * 0.05) - 1)
    idx_50 = int(n_simulations * 0.50) - 1
    idx_95 = min(n_simulations - 1, int(n_simulations * 0.95))

    median_pnl = round(sorted_pnls[idx_50], 2)
    pnl_5th    = round(sorted_pnls[idx_5],  2)
    pnl_95th   = round(sorted_pnls[idx_95], 2)

    # DD : le "worst" = 5th percentile (plus négatif)
    median_dd = round(sorted_dds[idx_50], 2)
    worst_dd  = round(sorted_dds[idx_5],  2)

    prob_profitable = round(sum(1 for p in final_pnls if p > 0) / n_simulations * 100, 1)
    prob_ruin       = round(sum(1 for d in max_dds if d < -capital * 0.5) / n_simulations * 100, 1)

    return {
        "median_pnl":      median_pnl,
        "pnl_5th":         pnl_5th,
        "pnl_95th":        pnl_95th,
        "median_dd":       median_dd,
        "worst_dd":        worst_dd,
        "prob_profitable": prob_profitable,
        "prob_ruin":       prob_ruin,
        "n_simulations":   n_simulations,
        "n_trades":        n_trades,
        "equity_curves":   equity_curves,
    }


# ── All Metrics ───────────────────────────────────────────────────────────────

def calculate_all_advanced_metrics(
    trades: list[dict],
    capital: float = 10_000.0,
) -> dict:
    """
    Calcule et retourne toutes les métriques avancées.

    En plus des ratios standards :
        kelly_criterion = winrate - (1-winrate) / edge_ratio
        profit_factor   = sum(gains) / sum(losses)
        max_consecutive_wins / losses
    """
    result: dict = {
        "n_trades":               len(trades),
        "sharpe_ratio":           None,
        "sortino_ratio":          None,
        "calmar_ratio":           None,
        "expectancy":             {},
        "kelly_criterion":        None,
        "profit_factor":          None,
        "max_consecutive_wins":   None,
        "max_consecutive_losses": None,
        "monte_carlo":            None,
        "r_distribution":         {},
    }

    if not trades:
        return result

    # ── Ratios ───────────────────────────────────────────────────────────────
    try:
        result["sharpe_ratio"]  = calculate_sharpe_ratio(trades)
    except Exception:
        pass
    try:
        result["sortino_ratio"] = calculate_sortino_ratio(trades)
    except Exception:
        pass
    try:
        result["calmar_ratio"]  = calculate_calmar_ratio(trades)
    except Exception:
        pass

    # ── Expectancy ───────────────────────────────────────────────────────────
    try:
        result["expectancy"] = calculate_expectancy(trades)
    except Exception:
        pass

    # ── Kelly ────────────────────────────────────────────────────────────────
    try:
        exp = result["expectancy"]
        wr  = (exp.get("winrate") or 0) / 100
        er  = exp.get("edge_ratio")
        if er and er > 0:
            kelly = wr - (1 - wr) / er
            result["kelly_criterion"] = round(kelly, 4)
    except Exception:
        pass

    # ── Profit Factor ────────────────────────────────────────────────────────
    try:
        pnls = _pnl_list(trades)
        gross_win  = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        result["profit_factor"] = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
    except Exception:
        pass

    # ── Séries consécutives ──────────────────────────────────────────────────
    try:
        max_wins = max_losses = cur_wins = cur_losses = 0
        for t in trades:
            if (t.get("pnl_dollars") or 0) > 0:
                cur_wins   += 1
                cur_losses  = 0
            elif (t.get("pnl_dollars") or 0) < 0:
                cur_losses += 1
                cur_wins    = 0
            else:
                cur_wins = cur_losses = 0
            max_wins   = max(max_wins,   cur_wins)
            max_losses = max(max_losses, cur_losses)
        result["max_consecutive_wins"]   = max_wins
        result["max_consecutive_losses"] = max_losses
    except Exception:
        pass

    # ── Distribution des R ───────────────────────────────────────────────────
    try:
        rr_vals = [t.get("rr_realized") for t in trades if t.get("rr_realized") is not None]
        if rr_vals:
            buckets = {"-2R": 0, "-1R": 0, "0R": 0, "+1R": 0, "+2R": 0, "+3R+": 0}
            for r in rr_vals:
                if r <= -1.5:
                    buckets["-2R"] += 1
                elif r <= -0.5:
                    buckets["-1R"] += 1
                elif r <= 0.5:
                    buckets["0R"]  += 1
                elif r <= 1.5:
                    buckets["+1R"] += 1
                elif r <= 2.5:
                    buckets["+2R"] += 1
                else:
                    buckets["+3R+"] += 1
            result["r_distribution"] = buckets
    except Exception:
        pass

    # ── Monte Carlo ──────────────────────────────────────────────────────────
    try:
        result["monte_carlo"] = monte_carlo_simulation(trades, capital=capital)
    except Exception:
        pass

    return result


# ── Test __main__ ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random as _rnd

    _rnd.seed(42)
    # Génère 50 trades fictifs : 60% winrate, avg win $150, avg loss $100
    fake_trades = []
    for i in range(50):
        is_win = _rnd.random() < 0.60
        pnl    = _rnd.gauss(150, 40) if is_win else -abs(_rnd.gauss(100, 30))
        entry  = _rnd.uniform(50, 200)
        shares = _rnd.randint(10, 50)
        rr     = round(pnl / (entry * 0.02 * shares), 2)  # approx 2% risk
        fake_trades.append({
            "pnl_dollars":  round(pnl, 2),
            "entry_price":  round(entry, 2),
            "shares":       shares,
            "rr_realized":  rr,
            "status":       "CLOSED_WIN" if is_win else "CLOSED_LOSS",
        })

    print("=== Advanced Metrics — 50 trades fictifs ===\n")
    m = calculate_all_advanced_metrics(fake_trades)

    print(f"Sharpe Ratio    : {m['sharpe_ratio']}")
    print(f"Sortino Ratio   : {m['sortino_ratio']}")
    print(f"Calmar Ratio    : {m['calmar_ratio']}")
    print(f"Profit Factor   : {m['profit_factor']}")

    exp = m["expectancy"]
    if exp:
        print(f"\nExpectancy")
        print(f"  Winrate       : {exp['winrate']}%")
        print(f"  Avg Win       : ${exp['avg_win']}")
        print(f"  Avg Loss      : ${exp['avg_loss']}")
        print(f"  Expectancy    : ${exp['expectancy']}/trade")
        print(f"  Exp/R         : {exp['expectancy_per_r']}R")
        print(f"  Edge Ratio    : {exp['edge_ratio']}")

    if m["kelly_criterion"] is not None:
        kelly_pct = round(m["kelly_criterion"] * 100, 1)
        safe_kelly = round(kelly_pct * 0.25, 1)
        print(f"\nKelly Criterion : {kelly_pct}% (recommandé : {safe_kelly}% = 25% du Kelly)")

    print(f"\nSéries        : {m['max_consecutive_wins']} wins consécutifs | {m['max_consecutive_losses']} losses consécutifs")

    if m["r_distribution"]:
        print(f"\nDistribution R : {m['r_distribution']}")

    mc = m["monte_carlo"]
    if mc:
        print(f"\n=== Monte Carlo ({mc['n_simulations']} simulations, {mc['n_trades']} trades) ===")
        print(f"  PnL médian    : ${mc['median_pnl']:,.0f}")
        print(f"  5e pct (pire) : ${mc['pnl_5th']:,.0f}")
        print(f"  95e pct (best): ${mc['pnl_95th']:,.0f}")
        print(f"  Max DD médian : ${mc['median_dd']:,.0f}")
        print(f"  Pire DD (5%)  : ${mc['worst_dd']:,.0f}")
        print(f"  Prob rentable : {mc['prob_profitable']}%")
        print(f"  Risque ruine  : {mc['prob_ruin']}%")
        print(f"  Courbes sauvegardées : {len(mc['equity_curves'])} (sur 50)")
