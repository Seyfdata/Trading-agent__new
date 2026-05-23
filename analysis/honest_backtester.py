"""
Backtester honnête — juge de paix sur l'edge réel des 3 stratégies mécaniques.

AVERTISSEMENTS IMPORTANTS — LIRE AVANT D'INTERPRÉTER LES RÉSULTATS
════════════════════════════════════════════════════════════════════
1. BIAIS DE SURVIE NON CORRIGÉ : l'univers est limité aux tickers actuellement
   cotés en Bourse. Les titres délistés, en faillite ou rachetés sur la période
   testée sont absents par construction. Tous les résultats (IS et OOS) sont des
   BORNES HAUTES OPTIMISTES — le vrai edge est probablement inférieur.

2. SPLIT OOS SIMPLE (pas un walk-forward complet) : le découpage 70 % IS / 30 %
   OOS chronologique évite le regard vers le futur sur la période OOS. MAIS les
   seuils des stratégies ont été choisis intuitivement sur l'historique global.
   L'OOS ici est "meilleur que in-sample pur, mais pas pur". Walk-Forward Analysis
   (WFA avec re-optimisation par fenêtre) est prévu en itération 2.

3. RÈGLES DE SIGNAL INCHANGÉES : les 3 générateurs de signaux sont importés tels
   quels depuis analysis/backtester.py. Seule la couche d'exécution est rendue
   honnête (entrée open[i+1], slippage, commission).

4. INDICATEURS CALCULÉS SUR L'HISTORIQUE COMPLET : les MAs (SMA200, SMA50, etc.)
   sont backward-looking — aucun look-ahead bias. Le calcul sur le df complet avant
   split est correct et préserve la continuité des indicateurs au passage IS→OOS.

Améliorations vs analysis/backtester.py :
  ✓ Entrée à l'open[i+1], jamais au close du signal
  ✓ Slippage adverse sur chaque fill (achat et vente)
  ✓ Commission IBKR (max 1 $, 0.005 $/action) sur chaque côté
  ✓ Split IS / OOS chronologique (70 / 30)
  ✓ Sharpe annualisé + Deflated Sharpe Ratio (DSR)
  ✗ Market impact non modélisé (positions trop larges = impact sous-estimé)
  ✗ Biais de survie non corrigé
  ✗ Walk-forward non implémenté
"""

from __future__ import annotations

import math
import warnings
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Paramètres d'exécution ─────────────────────────────────────────────────────

SLIPPAGE_PCT: float = 0.001
# 10 bps par côté — conservateur pour mid-caps US liquides.
# Monter à 0.002 (20 bps) pour petites capitalisations.

COMMISSION_PER_SHARE: float = 0.005   # $ par action — modèle IBKR Tiered
COMMISSION_MIN: float = 1.00          # $ minimum par ordre / côté

OOS_SPLIT: float = 0.70
# 70 % premières barres = in-sample ; 30 % dernières = out-of-sample.
# Le verdict de validité se lit UNIQUEMENT sur l'OOS.

MAX_HOLD_DAYS: int = 20               # sortie temps max (identique au backtester)
MIN_STOP_PCT: float = 0.01            # stop < 1 % du prix → signal ignoré

CAPITAL: float = 10_000.0             # capital de départ par ticker ($)
RISK_PCT: float = 1.0                 # % du capital risqué par trade

# ── Import des générateurs de signaux existants (règles inchangées) ────────────

from analysis.backtester import (      # noqa: E402
    _load_data,
    _signals_discount_zone,
    _signals_sma200_bounce,
    _signals_volume_momentum,
    STRATEGIES,
)

_SIGNAL_GENERATORS: dict = {
    "DISCOUNT_ZONE":   _signals_discount_zone,
    "SMA200_BOUNCE":   _signals_sma200_bounce,
    "VOLUME_MOMENTUM": _signals_volume_momentum,
}

# ── CDF / PPF normale standard (sans scipy) ────────────────────────────────────

def _norm_cdf(z: float) -> float:
    """CDF de la loi normale standard via math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """
    Inverse CDF normale standard — approximation rationnelle (Acklam, 2002).
    Erreur max < 1.15 × 10⁻⁹ sur [10⁻¹⁰, 1 − 10⁻¹⁰].
    """
    p = max(1e-10, min(1.0 - 1e-10, p))

    a = [-3.969683028665376e+01,  2.209460984245205e+02, -2.759285104469687e+02,
          1.383577518672690e+02, -3.066479806614716e+01,  2.506628277459239e+00]
    b = [-5.447609879822406e+01,  1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00,  4.374664141464968e+00,  2.938163982698783e+00]
    d = [ 7.784695709041462e-03,  3.224671290700398e-01,  2.445134137142996e+00,
          3.754408661907416e+00]

    p_lo, p_hi = 0.02425, 1.0 - 0.02425

    if p < p_lo:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    elif p <= p_hi:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)

# ── Helpers exécution ──────────────────────────────────────────────────────────

def _commission(shares: int) -> float:
    """Commission IBKR Tiered : max(1 $, shares × 0.005 $) par côté."""
    return max(COMMISSION_MIN, shares * COMMISSION_PER_SHARE)


def _fill_buy(price: float) -> float:
    """Prix d'achat réel après slippage adverse (achat = plus cher)."""
    return price * (1.0 + SLIPPAGE_PCT)


def _fill_sell(price: float) -> float:
    """Prix de vente réel après slippage adverse (vente = moins cher)."""
    return price * (1.0 - SLIPPAGE_PCT)

# ── Simulation honnête ─────────────────────────────────────────────────────────

def simulate_honest(
    df: pd.DataFrame,
    signals: list[dict],
    capital: float = CAPITAL,
    risk_pct: float = RISK_PCT,
) -> list[dict]:
    """
    Simule les trades avec exécution réaliste.

    Différences vs simulate_trades() du backtester existant :
    - Entrée à df.iloc[i+1]["Open"] × (1 + SLIPPAGE_PCT) — jamais au close du signal
    - Stop / target / time-exit avec slippage adverse sur la sortie
    - Commission déduite du PnL à l'entrée ET à la sortie

    Chaque trade retourné contient :
      pnl_gross  : PnL brut (sans frictions) en $
      pnl_net    : PnL net (après slippage + commission) en $
      r_multiple : pnl_net / risque initial en R
    """
    trades: list[dict] = []
    in_position = False
    cur_entry_fill = 0.0
    cur_stop = 0.0
    cur_target_raw = 0.0
    cur_shares = 0
    cur_open_i = 0
    cur_date_open = ""
    cur_comm_entry = 0.0
    cur_risk_initial = 0.0

    signal_by_i: dict[int, dict] = {s["i"]: s for s in signals}
    n = len(df)

    for i in range(n):
        row = df.iloc[i]

        # ── Gestion de la position ouverte ─────────────────────────────────────
        if in_position:
            hold_days = i - cur_open_i
            result: Optional[str] = None
            exit_raw = 0.0

            if float(row["Low"]) <= cur_stop:
                result, exit_raw = "LOSS", cur_stop
            elif float(row["High"]) >= cur_target_raw:
                result, exit_raw = "WIN", cur_target_raw
            elif hold_days >= MAX_HOLD_DAYS:
                result, exit_raw = "TIME", float(row["Close"])

            if result:
                exit_fill = _fill_sell(exit_raw)
                comm_exit = _commission(cur_shares)
                pnl_gross = (exit_raw - cur_entry_fill) * cur_shares
                pnl_net = (
                    (exit_fill - cur_entry_fill) * cur_shares
                    - cur_comm_entry - comm_exit
                )
                r_mult = pnl_net / cur_risk_initial if cur_risk_initial > 0 else 0.0
                date_close = str(row["date_str"]) if "date_str" in row.index else str(i)

                trades.append({
                    "date_open":  cur_date_open,
                    "date_close": date_close,
                    "entry":      round(cur_entry_fill, 2),
                    "stop":       round(cur_stop, 2),
                    "target":     round(cur_target_raw, 2),
                    "exit":       round(exit_fill, 2),
                    "shares":     cur_shares,
                    "pnl_gross":  round(pnl_gross, 2),
                    "pnl_net":    round(pnl_net, 2),
                    "r_multiple": round(r_mult, 2),
                    "result":     result,
                    "hold_days":  hold_days,
                })
                in_position = False

        # ── Ouverture d'un nouveau trade ───────────────────────────────────────
        if not in_position and i in signal_by_i:
            next_i = i + 1
            if next_i >= n:
                continue                           # signal sur dernière barre → ignore

            sig = signal_by_i[i]
            next_row = df.iloc[next_i]
            entry_raw = float(next_row["Open"])
            if entry_raw <= 0:
                continue

            entry_fill = _fill_buy(entry_raw)
            stop_price = sig["stop"]
            rps = entry_fill - stop_price          # risk per share après slippage

            if rps <= 0 or rps / entry_fill < MIN_STOP_PCT:
                continue

            shares = max(1, math.floor(capital * risk_pct / 100.0 / rps))
            comm_entry = _commission(shares)
            risk_initial = shares * rps + comm_entry
            target_raw = entry_fill + 2.5 * rps    # target recalculé sur fill réel

            date_open = str(next_row["date_str"]) if "date_str" in next_row.index else str(next_i)

            in_position = True
            cur_open_i = next_i
            cur_entry_fill = entry_fill
            cur_stop = stop_price
            cur_target_raw = target_raw
            cur_shares = shares
            cur_comm_entry = comm_entry
            cur_risk_initial = risk_initial
            cur_date_open = date_open

    return trades

# ── Métriques ──────────────────────────────────────────────────────────────────

def _sharpe_annualised(pnl_nets: list[float], periods_per_year: int = 252) -> float:
    """
    Sharpe annualisé calculé sur les PnL nets par trade.

    Approximation : on suppose un trade ≈ une période de holding moyenne.
    Pour un Sharpe journalier exact il faudrait les rendements du capital chaque jour.
    """
    if len(pnl_nets) < 2:
        return 0.0
    arr = np.array(pnl_nets, dtype=float)
    mu, sigma = arr.mean(), arr.std(ddof=1)
    if sigma == 0.0:
        return 0.0
    return float(mu / sigma * math.sqrt(periods_per_year))


def deflated_sharpe(
    sr_observed: float,
    n_trials: int,
    sr_variance_across_trials: float,
    skew: float,
    kurtosis_total: float,
    n_returns: int,
) -> float:
    """
    Deflated Sharpe Ratio (DSR) — Bailey & López de Prado (2014).

    Répond à : "Quelle est la probabilité que l'edge observé soit réel,
    une fois corrigé pour le nombre de stratégies × tickers testés ?"

    ── Étape 1 : benchmark SR* (maximum espéré sur K trials indépendants)
       SR* = √V[SR] × { (1−γ)·Φ⁻¹(1−1/K) + γ·Φ⁻¹(1−1/(K·e)) }
       γ = constante d'Euler-Mascheroni ≈ 0.5772
       V[SR] = variance empirique des Sharpe observés sur les K trials

    ── Étape 2 : Probabilistic Sharpe Ratio évalué au benchmark SR*
       PSR(SR*) = Φ{ (ŜR − SR*)·√(T−1) / √(1 − sk·ŜR + (ku−1)/4·ŜR²) }
       sk = skewness des rendements
       ku = kurtosis TOTAL (= kurtosis Pearson, soit excess kurtosis + 3)
       T  = nombre de rendements (trades)

    ── Convention de retour : DSR = PSR(SR*) − 0.5 (centré sur 0)
       DSR > 0   → edge statistiquement au-delà du hasard
       DSR ≤ 0   → probablement du bruit ou surajustement

    Paramètres
    ──────────
    sr_observed              : Sharpe annualisé observé sur ce trial
    n_trials                 : K = nombre total de (stratégie × ticker) testés
    sr_variance_across_trials: V[SR] = variance des Sharpe observés sur tous les K trials
    skew                     : skewness des rendements par trade
    kurtosis_total           : kurtosis TOTAL (pandas.kurtosis() + 3)
    n_returns                : T = nombre de trades / rendements sur ce trial
    """
    EULER = 0.5772156649015328

    if n_trials <= 0 or sr_variance_across_trials <= 0.0 or n_returns < 2:
        return 0.0

    # 1. SR*
    sqrt_v = math.sqrt(sr_variance_across_trials)
    z1 = _norm_ppf(max(1e-10, 1.0 - 1.0 / n_trials))
    z2 = _norm_ppf(max(1e-10, 1.0 - 1.0 / (n_trials * math.e)))
    sr_star = sqrt_v * ((1.0 - EULER) * z1 + EULER * z2)

    # 2. PSR(SR*)
    denom_sq = (
        1.0
        - skew * sr_observed
        + (kurtosis_total - 1.0) / 4.0 * sr_observed ** 2
    )
    if denom_sq <= 0.0:
        return 0.0

    z = (sr_observed - sr_star) * math.sqrt(max(0.0, n_returns - 1)) / math.sqrt(denom_sq)
    psr = _norm_cdf(z)
    return round(psr - 0.5, 4)


def _compute_metrics(
    trades: list[dict],
    capital: float,
    all_sharpes_for_dsr: Optional[list[float]] = None,
    n_trials: int = 1,
) -> dict:
    """Calcule toutes les métriques sur une liste de trades nets."""
    _empty: dict = {
        "n_trades": 0, "wins": 0, "losses": 0, "time_exits": 0,
        "winrate": 0.0, "profit_factor": None, "total_return_pct": 0.0,
        "avg_R": 0.0, "max_drawdown_pct": 0.0,
        "sharpe_annualise": 0.0, "deflated_sharpe": None,
    }
    if not trades:
        return _empty

    pnl_nets = [t["pnl_net"] for t in trades]
    r_mults  = [t["r_multiple"] for t in trades]
    wins     = [t for t in trades if t["result"] == "WIN"]
    losses   = [t for t in trades if t["result"] == "LOSS"]
    times    = [t for t in trades if t["result"] == "TIME"]

    gross_win  = sum(t["pnl_net"] for t in wins)
    gross_loss = abs(sum(t["pnl_net"] for t in losses))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else None

    total_pnl        = sum(pnl_nets)
    total_return_pct = round(total_pnl / capital * 100, 2) if capital > 0 else 0.0

    # Max drawdown en % du capital
    cum = peak = max_dd = 0.0
    for p in pnl_nets:
        cum += p
        peak = max(peak, cum)
        dd = (peak - cum) / capital * 100 if capital > 0 else 0.0
        max_dd = max(max_dd, dd)

    sharpe = _sharpe_annualised(pnl_nets)

    # DSR — calcul uniquement si assez de données cross-trials
    dsr: Optional[float] = None
    if all_sharpes_for_dsr is not None and len(all_sharpes_for_dsr) >= 2:
        arr_sr = np.array(all_sharpes_for_dsr, dtype=float)
        sr_var = float(arr_sr.var(ddof=1))
        pnl_arr = np.array(pnl_nets, dtype=float)
        skew_v = float(pd.Series(pnl_arr).skew()) if len(pnl_nets) >= 3 else 0.0
        # kurtosis total = excess kurtosis (pandas) + 3
        kurt_v = (float(pd.Series(pnl_arr).kurtosis()) + 3.0) if len(pnl_nets) >= 4 else 3.0
        dsr = deflated_sharpe(
            sr_observed=sharpe,
            n_trials=n_trials,
            sr_variance_across_trials=sr_var,
            skew=skew_v,
            kurtosis_total=kurt_v,
            n_returns=len(pnl_nets),
        )

    return {
        "n_trades":         len(trades),
        "wins":             len(wins),
        "losses":           len(losses),
        "time_exits":       len(times),
        "winrate":          round(len(wins) / len(trades) * 100, 1),
        "profit_factor":    pf,
        "total_return_pct": total_return_pct,
        "avg_R":            round(sum(r_mults) / len(r_mults), 2) if r_mults else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_annualise": round(sharpe, 3),
        "deflated_sharpe":  dsr,
    }

# ── Backtest honnête par (ticker, stratégie) ───────────────────────────────────

def backtest_honest(
    ticker: str,
    strategy: str,
    period: str = "10y",
    capital: float = CAPITAL,
    risk_pct: float = RISK_PCT,
) -> dict:
    """
    Backtest honnête sur un (ticker, stratégie).
    Retourne is_trades et oos_trades séparément.

    Les indicateurs sont calculés sur l'historique complet (backward-looking, sans
    look-ahead bias) puis le df est découpé chronologiquement avant la simulation.
    """
    empty: dict = {
        "ticker": ticker, "strategy": strategy,
        "is_trades": [], "oos_trades": [], "error": None,
    }
    if strategy not in _SIGNAL_GENERATORS:
        return dict(empty, error=f"Stratégie inconnue : {strategy}")

    try:
        df = _load_data(ticker, period)
        if df is None or len(df) < 250:
            n = len(df) if df is not None else 0
            return dict(empty, error=f"Données insuffisantes ({n} barres)")

        split_idx = int(len(df) * OOS_SPLIT)
        # reset_index(drop=True) → index positionnel 0..N pour compatibilité iloc
        df_is  = df.iloc[:split_idx].reset_index(drop=True)
        df_oos = df.iloc[split_idx:].reset_index(drop=True)

        gen = _SIGNAL_GENERATORS[strategy]
        trades_is  = simulate_honest(df_is,  gen(df_is),  capital, risk_pct)
        trades_oos = simulate_honest(df_oos, gen(df_oos), capital, risk_pct)

        return dict(empty, is_trades=trades_is, oos_trades=trades_oos, df_oos=df_oos)

    except Exception as exc:
        return dict(empty, error=str(exc), df_oos=None)

# ── Buy-and-hold OOS ──────────────────────────────────────────────────────────

def buy_and_hold(df_oos: pd.DataFrame, capital: float = CAPITAL) -> float:
    """
    Achète à l'open de la 1re barre OOS, vend au close de la dernière barre OOS.
    Net d'un aller-retour de frictions identiques à simulate_honest (slippage + commission).

    Représente le coût d'opportunité : rester investi sur toute la période OOS
    sans aucun timing. C'est l'étalon passif à battre.

    BIAIS DE SURVIE NON CORRIGÉ : même univers de tickers vivants.
    """
    if df_oos is None or len(df_oos) < 2:
        return 0.0
    entry_raw = float(df_oos.iloc[0]["Open"])
    exit_raw  = float(df_oos.iloc[-1]["Close"])
    if entry_raw <= 0:
        return 0.0
    entry_fill = _fill_buy(entry_raw)
    shares     = max(1, int(capital / entry_fill))
    cost       = shares * entry_fill + _commission(shares)
    proceeds   = shares * _fill_sell(exit_raw) - _commission(shares)
    return round((proceeds - cost) / capital * 100, 2)


# ── Monte Carlo — test de permutation par entrées aléatoires ──────────────────

def _simulate_random_run(
    df: pd.DataFrame,
    entry_bars: list,
    avg_risk_pct: float,
    capital: float,
    risk_pct: float,
) -> float:
    """
    Un run MC : simule les trades depuis des barres d'entrée aléatoires (déjà triées).

    Même moteur de sortie et mêmes frictions que simulate_honest.
    Une seule position à la fois : entrée ignorée si position déjà ouverte.
    """
    n = len(df)
    total_pnl = 0.0
    blocked_until = -1

    for ei in entry_bars:
        if ei <= blocked_until:
            continue
        next_i = ei + 1
        if next_i >= n:
            continue
        next_row   = df.iloc[next_i]
        entry_raw  = float(next_row["Open"])
        if entry_raw <= 0:
            continue
        entry_fill = _fill_buy(entry_raw)
        rps        = entry_fill * avg_risk_pct
        if rps <= 0:
            continue
        stop_price = entry_fill - rps
        target_raw = entry_fill + 2.5 * rps
        shares     = max(1, math.floor(capital * risk_pct / 100.0 / rps))
        comm_entry = _commission(shares)

        trade_pnl = 0.0
        closed_at = min(next_i + MAX_HOLD_DAYS, n - 1)

        for j in range(next_i, min(next_i + MAX_HOLD_DAYS + 1, n)):
            row  = df.iloc[j]
            hold = j - next_i
            result = None
            exit_raw = 0.0
            if float(row["Low"]) <= stop_price:
                result, exit_raw = "LOSS", stop_price
            elif float(row["High"]) >= target_raw:
                result, exit_raw = "WIN", target_raw
            elif hold >= MAX_HOLD_DAYS:
                result, exit_raw = "TIME", float(row["Close"])
            if result:
                comm_exit = _commission(shares)
                trade_pnl = (
                    (_fill_sell(exit_raw) - entry_fill) * shares
                    - comm_entry - comm_exit
                )
                closed_at = j
                break

        total_pnl    += trade_pnl
        blocked_until = closed_at

    return round(total_pnl / capital * 100, 2)


def random_entry_montecarlo(
    df_oos: pd.DataFrame,
    n_trades: int,
    real_return_pct: float,
    avg_risk_pct: float = 0.02,
    n_runs: int = 500,
    seed: int = 42,
    capital: float = CAPITAL,
    risk_pct: float = RISK_PCT,
) -> dict:
    """
    Test de permutation par entrées aléatoires — méthode Aronson.

    Principe : randomise UNIQUEMENT l'entrée (date). Logique de sortie, stop %,
    frictions et nombre de trades sont IDENTIQUES à simulate_honest. Isole ainsi
    la compétence de timing en contrôlant l'exposition et les conditions de marché.

    Paramètres
    ──────────
    df_oos         : données OOS (même df que simulate_honest)
    n_trades       : nombre de trades par run (= trades réels sur l'OOS)
    real_return_pct: rendement net réel de la stratégie sur l'OOS
    avg_risk_pct   : risque moyen par trade en % du prix (calculé depuis les trades réels)
    n_runs         : nombre de runs MC (défaut 500 pour perf acceptable)
    seed           : graine NumPy pour reproductibilité

    Retourne
    ────────
    pvalue     : fraction des runs dont rendement >= rendement réel
                 p < 0.05 -> stratégie bat le hasard à 95 %
    percentile : centile du rendement réel dans la distribution MC
    mean_random, median_random : statistiques de la distribution nulle

    BIAIS DE SURVIE NON CORRIGÉ : même univers de tickers vivants.
    """
    empty_mc = {
        "pvalue": 1.0, "percentile": 0.0,
        "mean_random": 0.0, "median_random": 0.0, "n_runs": 0,
    }
    if n_trades <= 0 or df_oos is None or len(df_oos) < MAX_HOLD_DAYS + 2:
        return empty_mc

    rng = np.random.default_rng(seed)
    n   = len(df_oos)
    candidates = np.arange(0, max(1, n - MAX_HOLD_DAYS - 1))

    if len(candidates) < n_trades:
        return empty_mc

    dist = np.empty(n_runs)
    for k in range(n_runs):
        chosen = np.sort(rng.choice(candidates, size=n_trades, replace=False))
        dist[k] = _simulate_random_run(
            df_oos, chosen.tolist(), avg_risk_pct, capital, risk_pct
        )

    pvalue     = float(np.mean(dist >= real_return_pct))
    percentile = float(np.mean(dist < real_return_pct) * 100)
    return {
        "pvalue":        round(pvalue, 4),
        "percentile":    round(percentile, 1),
        "mean_random":   round(float(dist.mean()), 2),
        "median_random": round(float(np.median(dist)), 2),
        "n_runs":        n_runs,
    }


# ── Verdict ────────────────────────────────────────────────────────────────────

def _verdict(m_oos: dict) -> str:
    """MORTE si OOS profit_factor < 1.1 OU DSR <= 0, sinon A CREUSER."""
    pf  = m_oos.get("profit_factor")
    dsr = m_oos.get("deflated_sharpe")
    if pf is None or pf < 1.1:
        return "MORTE"
    if dsr is not None and dsr <= 0.0:
        return "MORTE"
    return "A CREUSER"

# ── run_all ────────────────────────────────────────────────────────────────────

MC_RUNS: int = 500             # nombre de runs Monte Carlo par (ticker, stratégie)
MIN_TRADES_FOR_BENCH: int = 2  # trades OOS minimum pour calculer les benchmarks


def run_all(
    tickers: Optional[list[str]] = None,
    period: str = "10y",
    capital: float = CAPITAL,
    risk_pct: float = RISK_PCT,
) -> dict:
    """
    Lance les 3 stratégies sur la watchlist complète (ou tickers fournis).

    Pour chaque (stratégie, ticker) en OOS :
      - rendement net de la stratégie
      - rendement buy-and-hold (coût d'opportunité)
      - test de permutation MC (p-value : la stratégie bat-elle le hasard ?)

    Affiche un tableau agrégé par stratégie avec verdict global.
    """
    from config.settings import WATCHLIST

    if tickers is None:
        tickers = list(WATCHLIST)

    n_trials = len(tickers) * len(STRATEGIES)
    print(
        f"[HonestBT] {len(tickers)} tickers x {len(STRATEGIES)} strats = {n_trials} backtests"
        f" | period={period} | slip={SLIPPAGE_PCT*10000:.0f}bps"
        f" | OOS={int((1.0 - OOS_SPLIT) * 100)}% | MC={MC_RUNS} runs/trial"
    )

    # ── 1. Backtest honnête pour chaque (stratégie, ticker) ───────────────────
    raw: dict[str, dict[str, dict]] = {s: {} for s in STRATEGIES}
    for strategy in STRATEGIES:
        print(f"[HonestBT] {strategy}...", end=" ", flush=True)
        for ticker in tickers:
            r = backtest_honest(ticker, strategy, period=period, capital=capital, risk_pct=risk_pct)
            if r["error"]:
                print(f"\n[HonestBT]   ! {ticker}: {r['error']}", end="")
            raw[strategy][ticker] = r
        print("OK")

    # ── 2. Sharpe OOS cross-trials pour DSR ───────────────────────────────────
    MIN_TRADES_DSR = 5
    all_sharpes_oos: list[float] = []
    for strategy in STRATEGIES:
        for ticker in tickers:
            r = raw[strategy][ticker]
            if not r["error"] and len(r["oos_trades"]) >= MIN_TRADES_DSR:
                sh = _sharpe_annualised([t["pnl_net"] for t in r["oos_trades"]])
                all_sharpes_oos.append(sh)

    # ── 3. Benchmarks (buy-and-hold + Monte Carlo) par (stratégie, ticker) ────
    bench: dict[str, dict[str, dict]] = {s: {} for s in STRATEGIES}
    for strategy in STRATEGIES:
        for ticker in tickers:
            r = raw[strategy][ticker]
            df_oos = r.get("df_oos")
            oos_trades = r.get("oos_trades", [])

            bh = buy_and_hold(df_oos, capital) if df_oos is not None else 0.0
            strat_ret = sum(t["pnl_net"] for t in oos_trades) / capital * 100

            mc: dict = {"pvalue": 1.0, "percentile": 0.0,
                        "mean_random": 0.0, "median_random": 0.0, "n_runs": 0}
            if len(oos_trades) >= MIN_TRADES_FOR_BENCH and df_oos is not None:
                risks = [
                    abs(t["entry"] - t["stop"]) / t["entry"]
                    for t in oos_trades if t["entry"] > 0 and t["stop"] > 0
                ]
                avg_rp = float(np.mean(risks)) if risks else 0.02
                mc = random_entry_montecarlo(
                    df_oos=df_oos,
                    n_trades=len(oos_trades),
                    real_return_pct=strat_ret,
                    avg_risk_pct=avg_rp,
                    n_runs=MC_RUNS,
                    seed=42,
                    capital=capital,
                    risk_pct=risk_pct,
                )
            bench[strategy][ticker] = {
                "strat_return":   round(strat_ret, 2),
                "bh_return":      bh,
                "beats_bh":       strat_ret > bh,
                "mc_pvalue":      mc["pvalue"],
                "mc_percentile":  mc["percentile"],
                "mc_mean_random": mc["mean_random"],
                "verdict_ticker": (
                    "EDGE PLAUSIBLE"
                    if mc["pvalue"] < 0.05 and strat_ret > 0
                    else "PAS DE TIMING"
                ),
            }

    # ── 4. Métriques agrégées par stratégie ───────────────────────────────────
    metrics: dict[str, dict] = {}
    for strategy in STRATEGIES:
        all_is: list[dict] = []
        all_oos: list[dict] = []
        for ticker in tickers:
            r = raw[strategy][ticker]
            if not r["error"]:
                all_is.extend(r["is_trades"])
                all_oos.extend(r["oos_trades"])

        agg_cap = capital * len(tickers)
        m_is  = _compute_metrics(all_is, agg_cap)
        m_oos = _compute_metrics(
            all_oos, agg_cap,
            all_sharpes_for_dsr=all_sharpes_oos if len(all_sharpes_oos) >= 2 else None,
            n_trials=n_trials,
        )
        metrics[strategy] = {"is": m_is, "oos": m_oos}

    _print_full_report(metrics, bench, tickers, period)
    return {"raw": raw, "metrics": metrics, "bench": bench, "n_trials": n_trials}


def _print_full_report(
    metrics: dict,
    bench: dict[str, dict[str, dict]],
    tickers: list[str],
    period: str,
) -> None:
    """
    Tableau agrégé par stratégie (OOS uniquement) avec :
      n_trades, PF_net, Sharpe, DSR, rendement strat moyen, rendement B&H moyen,
      % tickers qui battent B&H, % tickers p<0.05 (MC), verdict global.
    """
    W = 128
    sep  = "=" * W
    line = "-" * W

    hdr = (
        f"{'Strategie':<22} {'N':>5} {'PF':>5} {'Sharpe':>7} {'DSR':>7}"
        f" {'Strat%':>7} {'B&H%':>6} {'BtBH%':>6} {'p<.05':>6}  Verdict"
    )
    print(f"\n{sep}")
    print(
        f"  HONEST BACKTEST (OOS uniquement) | {len(tickers)} tickers"
        f" | period={period} | slip={SLIPPAGE_PCT*10000:.0f}bps | MC={MC_RUNS} runs"
    )
    print(sep)
    print(hdr)
    print(line)

    for strategy in STRATEGIES:
        mm = metrics.get(strategy, {}).get("oos", {})
        b  = bench.get(strategy, {})

        valid_tickers = [t for t in tickers if not bench.get(strategy, {}).get(t, {}).get("error")]
        strat_rets  = [b[t]["strat_return"]  for t in tickers if t in b]
        bh_rets     = [b[t]["bh_return"]     for t in tickers if t in b]
        beats_bh    = [b[t]["beats_bh"]      for t in tickers if t in b]
        pvalues     = [b[t]["mc_pvalue"]     for t in tickers if t in b and b[t]["mc_pvalue"] < 1.0]
        p05_count   = sum(1 for p in pvalues if p < 0.05)
        p05_frac    = p05_count / len(pvalues) * 100 if pvalues else 0.0
        beats_frac  = sum(beats_bh) / len(beats_bh) * 100 if beats_bh else 0.0
        mean_strat  = float(np.mean(strat_rets)) if strat_rets else 0.0
        mean_bh     = float(np.mean(bh_rets))    if bh_rets    else 0.0

        pf_s  = f"{mm['profit_factor']:.2f}" if mm.get("profit_factor") else "  N/A"
        dsr_v = mm.get("deflated_sharpe")
        dsr_s = f"{dsr_v:+.3f}" if dsr_v is not None else "   N/A"

        # Verdict global stratégie : edge plausible si >= 25% des tickers p<0.05 ET strat > 0
        global_verdict = (
            "EDGE PLAUSIBLE"
            if p05_frac >= 25.0 and mean_strat > 0.0
            else "PAS D'EDGE"
        )
        icon = "[OK]" if global_verdict == "EDGE PLAUSIBLE" else "[X] "

        print(
            f"{strategy:<22} {mm.get('n_trades',0):>5} {pf_s:>5}"
            f" {mm.get('sharpe_annualise',0):>7.3f} {dsr_s:>7}"
            f" {mean_strat:>6.1f}% {mean_bh:>5.1f}% {beats_frac:>5.0f}%"
            f" {p05_frac:>5.0f}%  {icon} {global_verdict}"
        )

    print(line)
    print(f"\n  COLONNES")
    print(f"  N       : trades OOS (agregat)")
    print(f"  Strat%  : rendement moyen par ticker (net frictions)")
    print(f"  B&H%    : rendement buy-and-hold moyen par ticker (net frictions)")
    print(f"  BtBH%   : % de tickers ou la strategie bat le buy-and-hold")
    print(f"  p<.05   : % de tickers avec pvalue MC < 0.05 (timing non aleatoire)")
    print(f"  VERDICT : EDGE PLAUSIBLE si p<.05 >= 25% ET Strat% > 0, sinon PAS D'EDGE")
    print(f"\n  [!] Biais de survie non corrige -- resultats = bornes hautes")
    print(f"  [!] OOS simple (pas walk-forward) -- WFA prevu iteration 2")
    print(f"  [!] MC base sur risque % moyen des vrais trades -- approximation du timing pur")
    print(f"{sep}\n")

# ── Point d'entrée ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_all(period="10y")
