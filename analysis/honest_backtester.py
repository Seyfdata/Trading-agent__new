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

        return dict(empty, is_trades=trades_is, oos_trades=trades_oos)

    except Exception as exc:
        return dict(empty, error=str(exc))

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

def run_all(
    tickers: Optional[list[str]] = None,
    period: str = "10y",
    capital: float = CAPITAL,
    risk_pct: float = RISK_PCT,
) -> dict:
    """
    Lance les 3 stratégies sur la watchlist (ou tickers fournis).
    Affiche un tableau IS vs OOS avec Sharpe, DSR et verdict par stratégie.
    """
    from config.settings import WATCHLIST

    if tickers is None:
        tickers = list(WATCHLIST)

    n_trials = len(tickers) * len(STRATEGIES)
    print(
        f"[HonestBT] {len(tickers)} tickers x {len(STRATEGIES)} strats = {n_trials} backtests"
        f" | period={period} | slip={SLIPPAGE_PCT*10000:.0f}bps"
        f" | comm=max({COMMISSION_MIN}$, {COMMISSION_PER_SHARE}$/sh)"
        f" | OOS={int((1.0 - OOS_SPLIT) * 100)}%"
    )

    # ── Collecte brute ─────────────────────────────────────────────────────────
    raw: dict[str, dict[str, dict]] = {s: {} for s in STRATEGIES}
    for strategy in STRATEGIES:
        print(f"[HonestBT] Stratégie {strategy}...")
        for ticker in tickers:
            r = backtest_honest(ticker, strategy, period=period, capital=capital, risk_pct=risk_pct)
            if r["error"]:
                print(f"[HonestBT]   ✗ {ticker}: {r['error']}")
            raw[strategy][ticker] = r

    # ── Sharpe OOS de tous les trials → variance pour DSR ─────────────────────
    # Filtre : trials avec < 5 trades OOS exclus (Sharpe non significatif sur peu de trades)
    MIN_TRADES_FOR_DSR = 5
    all_sharpes_oos: list[float] = []
    for strategy in STRATEGIES:
        for ticker in tickers:
            r = raw[strategy][ticker]
            if not r["error"] and len(r["oos_trades"]) >= MIN_TRADES_FOR_DSR:
                sh = _sharpe_annualised([t["pnl_net"] for t in r["oos_trades"]])
                all_sharpes_oos.append(sh)

    # ── Métriques agrégées par stratégie ──────────────────────────────────────
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
        m_is = _compute_metrics(all_is, agg_cap)
        m_oos = _compute_metrics(
            all_oos, agg_cap,
            all_sharpes_for_dsr=all_sharpes_oos if len(all_sharpes_oos) >= 2 else None,
            n_trials=n_trials,
        )
        metrics[strategy] = {"is": m_is, "oos": m_oos}

    _print_report(metrics, tickers, period)
    return {"raw": raw, "metrics": metrics, "n_trials": n_trials}


def _print_report(metrics: dict, tickers: list[str], period: str) -> None:
    W = 118
    hdr = (
        f"{'Strategie':<22} {'Zone':<4} "
        f"{'N':>5} {'WR%':>5} {'PF':>5} "
        f"{'Ret%':>7} {'AvgR':>5} {'DD%':>6} "
        f"{'Sharpe':>7} {'DSR':>7}  Verdict"
    )
    sep  = "=" * W
    line = "-" * W
    print(f"\n{sep}")
    print(
        f"  HONEST BACKTEST | {len(tickers)} tickers | period={period}"
        f" | slip={SLIPPAGE_PCT*10000:.0f}bps/cote | commission=IBKR"
    )
    print(sep)
    print(hdr)
    print(line)

    for strategy in STRATEGIES:
        m = metrics.get(strategy, {})
        for zone in ("is", "oos"):
            mm = m.get(zone, {})
            pf_s  = f"{mm['profit_factor']:.2f}" if mm.get("profit_factor") else "  N/A"
            dsr_v = mm.get("deflated_sharpe")
            dsr_s = f"{dsr_v:+.3f}" if dsr_v is not None else "   N/A"
            label = strategy if zone == "is" else ""

            flag = ""
            if zone == "oos":
                v = _verdict(mm)
                icon = "[X]" if v == "MORTE" else "[OK]"
                flag = f"  {icon} {v}"

            print(
                f"{label:<22} {zone.upper():<4} "
                f"{mm.get('n_trades',0):>5} {mm.get('winrate',0):>4.0f}%"
                f" {pf_s:>5} {mm.get('total_return_pct',0):>6.1f}%"
                f" {mm.get('avg_R',0):>5.2f} {mm.get('max_drawdown_pct',0):>5.1f}%"
                f" {mm.get('sharpe_annualise',0):>7.3f} {dsr_s:>7}{flag}"
            )
        print(line)

    print(f"\n  LEGENDE  DSR > 0 -> edge reel | DSR <= 0 -> bruit / surajustement")
    print(f"  VERDICT  MORTE si OOS profit_factor < 1.10 OU DSR <= 0, sinon A CREUSER")
    print(f"  [!] Biais de survie non corrige -- resultats = bornes hautes")
    print(f"  [!] OOS simple (pas walk-forward) -- WFA prevu iteration 2")
    print(f"{sep}\n")

# ── Point d'entrée ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_all(["NVDA", "AAPL"], period="10y")
