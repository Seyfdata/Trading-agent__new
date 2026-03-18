"""
Options Flow Analyzer — Sentiment via yfinance (gratuit).

Fonctions exposées :
    get_options_sentiment(ticker) → dict complet (PCR, unusual activity, max pain, smart money)
    options_sentiment_summary(ticker) → résumé compact pour dashboard

Usage :
    from analysis.options_flow import get_options_sentiment
    result = get_options_sentiment("NVDA")
"""

from __future__ import annotations

import warnings
from typing import Optional

warnings.filterwarnings("ignore")


# ── Constantes ────────────────────────────────────────────────────────────────

PCR_BULLISH_THRESHOLD  = 0.7   # PCR < 0.7 → BULLISH
PCR_BEARISH_THRESHOLD  = 1.0   # PCR > 1.0 → BEARISH
UNUSUAL_RATIO_MIN      = 3.0   # volume > 3× open interest = "unusual"
TOP_UNUSUAL_COUNT      = 5


# ── Helpers internes ──────────────────────────────────────────────────────────

def _pcr_direction(pcr: float) -> str:
    if pcr < PCR_BULLISH_THRESHOLD:
        return "BULLISH"
    if pcr <= PCR_BEARISH_THRESHOLD:
        return "NEUTRAL"
    return "BEARISH"


def _moneyness(strike: float, spot: float, option_type: str) -> str:
    """ITM / ATM / OTM selon type et strike."""
    if spot <= 0:
        return "UNKNOWN"
    ratio = strike / spot
    if abs(ratio - 1.0) < 0.02:  # ±2% → ATM
        return "ATM"
    if option_type == "CALL":
        return "ITM" if strike < spot else "OTM"
    else:  # PUT
        return "ITM" if strike > spot else "OTM"


def _compute_max_pain(calls_df, puts_df) -> Optional[float]:
    """
    Max Pain = strike qui minimise la douleur totale des options (valeur intrinsèque totale).
    Pour chaque strike possible, calcule : Σ max(0, strike - K) × OI_calls + Σ max(0, K - strike) × OI_puts
    """
    import pandas as pd

    try:
        all_strikes = sorted(
            set(calls_df["strike"].dropna().tolist() + puts_df["strike"].dropna().tolist())
        )
        if not all_strikes:
            return None

        min_pain   = float("inf")
        max_pain_k = None

        for test_strike in all_strikes:
            # Douleur calls : si prix expire > strike, call vaut (test_strike - K)
            call_pain = (
                calls_df.apply(
                    lambda row: max(0.0, test_strike - row["strike"]) * (row["openInterest"] or 0),
                    axis=1,
                )
                .sum()
            )
            # Douleur puts : si prix expire < strike, put vaut (K - test_strike)
            put_pain = (
                puts_df.apply(
                    lambda row: max(0.0, row["strike"] - test_strike) * (row["openInterest"] or 0),
                    axis=1,
                )
                .sum()
            )
            total_pain = call_pain + put_pain
            if total_pain < min_pain:
                min_pain   = total_pain
                max_pain_k = test_strike

        return float(max_pain_k) if max_pain_k is not None else None
    except Exception:
        return None


def _unusual_options(calls_df, puts_df, spot: float, expiry: str) -> list[dict]:
    """Top 5 options avec volume > 3× openInterest (toutes expirations confondues)."""
    import pandas as pd

    unusual = []

    for opt_type, df in [("CALL", calls_df), ("PUT", puts_df)]:
        for _, row in df.iterrows():
            try:
                vol = float(row.get("volume") or 0)
                oi  = float(row.get("openInterest") or 0)
            except (TypeError, ValueError):
                continue
            import math
            if math.isnan(vol) or math.isnan(oi):
                continue
            if oi <= 0 or vol <= 0:
                continue
            ratio = vol / oi
            if ratio >= UNUSUAL_RATIO_MIN:
                unusual.append({
                    "type":          opt_type,
                    "strike":        float(row["strike"]),
                    "expiry":        expiry,
                    "volume":        int(vol),
                    "openInterest":  int(oi),
                    "ratio":         round(ratio, 1),
                    "moneyness":     _moneyness(float(row["strike"]), spot, opt_type),
                })

    unusual.sort(key=lambda x: -x["ratio"])
    return unusual[:TOP_UNUSUAL_COUNT]


def _smart_money_signals(calls_df, puts_df, spot: float) -> dict:
    """
    Analyse le flux smart money sur les options :
    - Calls ITM gros volume → achat institutionnel
    - Puts ITM gros volume  → vente institutionnelle
    - Calls OTM gros volume → spéculation haussière
    - Puts OTM gros volume  → couverture (hedging)
    """
    itm_call_vol  = 0
    itm_put_vol   = 0
    otm_call_vol  = 0
    otm_put_vol   = 0

    if spot <= 0:
        return {}

    import math

    for _, row in calls_df.iterrows():
        try:
            vol = float(row.get("volume") or 0)
        except (TypeError, ValueError):
            continue
        if math.isnan(vol) or vol <= 0:
            continue
        m = _moneyness(float(row["strike"]), spot, "CALL")
        if m == "ITM":
            itm_call_vol += vol
        elif m == "OTM":
            otm_call_vol += vol

    for _, row in puts_df.iterrows():
        try:
            vol = float(row.get("volume") or 0)
        except (TypeError, ValueError):
            continue
        if math.isnan(vol) or vol <= 0:
            continue
        m = _moneyness(float(row["strike"]), spot, "PUT")
        if m == "ITM":
            itm_put_vol += vol
        elif m == "OTM":
            otm_put_vol += vol

    signals = []
    if itm_call_vol > 0 and itm_call_vol > otm_call_vol:
        signals.append({"type": "INSTITUTIONAL_BUY",   "detail": f"Calls ITM : {itm_call_vol:,} vol"})
    if itm_put_vol > 0 and itm_put_vol > otm_put_vol:
        signals.append({"type": "INSTITUTIONAL_SELL",  "detail": f"Puts ITM : {itm_put_vol:,} vol"})
    if otm_call_vol > itm_call_vol and otm_call_vol > 0:
        signals.append({"type": "BULLISH_SPECULATION",  "detail": f"Calls OTM : {otm_call_vol:,} vol"})
    if otm_put_vol > itm_put_vol and otm_put_vol > 0:
        signals.append({"type": "HEDGING",              "detail": f"Puts OTM : {otm_put_vol:,} vol"})

    # Direction globale smart money
    bull_vol = itm_call_vol + otm_call_vol
    bear_vol = itm_put_vol  + otm_put_vol
    if bull_vol + bear_vol == 0:
        direction = "NEUTRAL"
    elif bull_vol > bear_vol * 1.5:
        direction = "BULLISH"
    elif bear_vol > bull_vol * 1.5:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {
        "direction":     direction,
        "signals":       signals,
        "itm_call_vol":  int(round(itm_call_vol)),
        "itm_put_vol":   int(round(itm_put_vol)),
        "otm_call_vol":  int(round(otm_call_vol)),
        "otm_put_vol":   int(round(otm_put_vol)),
    }


# ── Fonction principale ───────────────────────────────────────────────────────

def get_options_sentiment(ticker: str) -> dict:
    """
    Analyse le sentiment via les options (yfinance, gratuit).

    Retourne :
    {
        "ticker":           str,
        "current_price":    float,
        "expirations_used": [str, ...],

        "pcr": {
            "value":      float,
            "direction":  "BULLISH" | "NEUTRAL" | "BEARISH",
            "call_volume": int,
            "put_volume":  int,
        },

        "unusual_activity": [
            {"type", "strike", "expiry", "volume", "openInterest", "ratio", "moneyness"},
            ...
        ],

        "max_pain": {
            "level":     float | None,
            "vs_price":  "ABOVE" | "BELOW" | "AT" | None,
            "bias":      "BULLISH" | "BEARISH" | "NEUTRAL" | None,
        },

        "smart_money": {
            "direction":    "BULLISH" | "BEARISH" | "NEUTRAL",
            "signals":      [...],
            "itm_call_vol": int,
            "itm_put_vol":  int,
            "otm_call_vol": int,
            "otm_put_vol":  int,
        },

        "overall_direction":  "BULLISH" | "NEUTRAL" | "BEARISH",
        "conviction":         "HIGH" | "MEDIUM" | "LOW",
        "summary":            str,
        "error":              str | None,
    }
    """
    base = {
        "ticker":           ticker,
        "current_price":    None,
        "expirations_used": [],
        "pcr":              {},
        "unusual_activity": [],
        "max_pain":         {},
        "smart_money":      {},
        "overall_direction": "NEUTRAL",
        "conviction":       "LOW",
        "summary":          f"Impossible d'analyser les options de {ticker}",
        "error":            None,
    }

    try:
        import yfinance as yf
        import pandas as pd

        tk = yf.Ticker(ticker)

        # ── Prix spot ────────────────────────────────────────────────────────
        hist = tk.history(period="2d", interval="1d")
        if hist is None or len(hist) == 0:
            base["error"] = "Impossible de récupérer le prix"
            return base
        spot = float(hist["Close"].iloc[-1])
        base["current_price"] = round(spot, 2)

        # ── Dates d'expiration (2 prochaines) ────────────────────────────────
        expirations = tk.options
        if not expirations:
            base["error"] = "Pas de données d'options disponibles"
            return base
        expirations = list(expirations)[:2]
        base["expirations_used"] = expirations

        # ── Agrégation des données sur les 2 expirations ─────────────────────
        all_calls = []
        all_puts  = []
        unusual_all = []

        for exp in expirations:
            try:
                chain = tk.option_chain(exp)
                calls = chain.calls.copy()
                puts  = chain.puts.copy()
                all_calls.append(calls)
                all_puts.append(puts)
                # Unusual activity par expiration
                unusual_all.extend(_unusual_options(calls, puts, spot, exp))
            except Exception:
                continue

        if not all_calls:
            base["error"] = "Chaîne d'options vide"
            return base

        calls_agg = pd.concat(all_calls, ignore_index=True)
        puts_agg  = pd.concat(all_puts,  ignore_index=True)

        # ── PCR ──────────────────────────────────────────────────────────────
        total_call_vol = int(calls_agg["volume"].fillna(0).astype(float).sum())
        total_put_vol  = int(puts_agg["volume"].fillna(0).astype(float).sum())

        if total_call_vol > 0:
            pcr = round(total_put_vol / total_call_vol, 2)
        else:
            pcr = None

        base["pcr"] = {
            "value":       pcr,
            "direction":   _pcr_direction(pcr) if pcr is not None else "UNKNOWN",
            "call_volume": total_call_vol,
            "put_volume":  total_put_vol,
        }

        # ── Unusual activity ─────────────────────────────────────────────────
        unusual_all.sort(key=lambda x: -x["ratio"])
        base["unusual_activity"] = unusual_all[:TOP_UNUSUAL_COUNT]

        # ── Max pain (première expiration) ───────────────────────────────────
        if all_calls and all_puts:
            mp = _compute_max_pain(all_calls[0], all_puts[0])
            if mp is not None:
                if spot > mp * 1.01:
                    vs = "ABOVE"
                    mp_bias = "BEARISH"  # MM vont pousser vers le bas
                elif spot < mp * 0.99:
                    vs = "BELOW"
                    mp_bias = "BULLISH"  # MM vont pousser vers le haut
                else:
                    vs = "AT"
                    mp_bias = "NEUTRAL"
                base["max_pain"] = {
                    "level":    round(mp, 2),
                    "vs_price": vs,
                    "bias":     mp_bias,
                }
            else:
                base["max_pain"] = {"level": None, "vs_price": None, "bias": None}

        # ── Smart money ──────────────────────────────────────────────────────
        base["smart_money"] = _smart_money_signals(calls_agg, puts_agg, spot)

        # ── Direction globale + conviction ───────────────────────────────────
        votes = {
            "BULLISH": 0,
            "BEARISH": 0,
            "NEUTRAL": 0,
        }

        pcr_dir = base["pcr"].get("direction", "NEUTRAL")
        sm_dir  = base["smart_money"].get("direction", "NEUTRAL")
        mp_bias = base["max_pain"].get("bias") or "NEUTRAL"

        for d in [pcr_dir, sm_dir, mp_bias]:
            if d in votes:
                votes[d] += 1

        if votes["BULLISH"] > votes["BEARISH"]:
            overall = "BULLISH"
        elif votes["BEARISH"] > votes["BULLISH"]:
            overall = "BEARISH"
        else:
            overall = "NEUTRAL"

        # Conviction : haute si 3/3 ou 2/3 avec unusual haussier
        bullish_unusual = sum(1 for u in base["unusual_activity"] if u["type"] == "CALL")
        bearish_unusual = sum(1 for u in base["unusual_activity"] if u["type"] == "PUT")
        unanimous = votes[overall] == 3
        majority  = votes[overall] == 2

        if unanimous:
            conviction = "HIGH"
        elif majority and (
            (overall == "BULLISH" and bullish_unusual >= bearish_unusual) or
            (overall == "BEARISH" and bearish_unusual >= bullish_unusual)
        ):
            conviction = "MEDIUM"
        else:
            conviction = "LOW"

        base["overall_direction"] = overall
        base["conviction"]        = conviction

        # ── Summary texte ─────────────────────────────────────────────────────
        pcr_str = f"PCR {pcr:.2f} ({pcr_dir})" if pcr else "PCR N/A"
        mp_str  = (
            f"Max Pain ${base['max_pain']['level']:.0f} ({mp_bias})"
            if base["max_pain"].get("level") else "Max Pain N/A"
        )
        sm_str  = f"Smart Money {sm_dir}"
        unu_str = (
            f"{len(base['unusual_activity'])} activités inhabituelles"
            if base["unusual_activity"]
            else "pas d'activité inhabituelle"
        )

        base["summary"] = (
            f"{ticker} @ ${spot:.2f} — {overall} ({conviction}) | "
            f"{pcr_str} | {mp_str} | {sm_str} | {unu_str}"
        )

    except Exception as e:
        base["error"]   = str(e)
        base["summary"] = f"Erreur options {ticker} : {e}"

    return base


# ── Résumé compact pour dashboard ─────────────────────────────────────────────

def options_sentiment_summary(ticker: str) -> dict:
    """
    Version légère de get_options_sentiment pour affichage dashboard.
    Retourne seulement les champs clés.
    """
    full = get_options_sentiment(ticker)
    return {
        "ticker":            full["ticker"],
        "current_price":     full["current_price"],
        "overall_direction": full["overall_direction"],
        "conviction":        full["conviction"],
        "pcr":               full["pcr"].get("value"),
        "pcr_direction":     full["pcr"].get("direction"),
        "max_pain_level":    full["max_pain"].get("level"),
        "max_pain_bias":     full["max_pain"].get("bias"),
        "smart_money_dir":   full["smart_money"].get("direction"),
        "unusual_count":     len(full["unusual_activity"]),
        "top_unusual":       full["unusual_activity"][:3],
        "summary":           full["summary"],
        "error":             full["error"],
    }


# ── Test __main__ ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    for t in ["NVDA", "AMD"]:
        print(f"\n{'='*60}")
        print(f"Options Flow — {t}")
        print('='*60)
        r = get_options_sentiment(t)
        if r["error"]:
            print(f"  ERREUR : {r['error']}")
            continue
        print(f"  Prix actuel    : ${r['current_price']}")
        print(f"  Expirations    : {r['expirations_used']}")
        print(f"  Direction      : {r['overall_direction']} ({r['conviction']})")
        print(f"\n  PCR")
        print(f"    Valeur       : {r['pcr'].get('value')}")
        print(f"    Direction    : {r['pcr'].get('direction')}")
        print(f"    Call vol     : {r['pcr'].get('call_volume'):,}")
        print(f"    Put vol      : {r['pcr'].get('put_volume'):,}")
        print(f"\n  Max Pain")
        print(f"    Niveau       : ${r['max_pain'].get('level')}")
        print(f"    vs Prix      : {r['max_pain'].get('vs_price')}")
        print(f"    Biais        : {r['max_pain'].get('bias')}")
        print(f"\n  Smart Money")
        print(f"    Direction    : {r['smart_money'].get('direction')}")
        for sig in r["smart_money"].get("signals", []):
            print(f"    • {sig['type']:<25} {sig['detail']}")
        print(f"\n  Activités inhabituelles ({len(r['unusual_activity'])}) :")
        for u in r["unusual_activity"]:
            print(f"    • {u['type']:<4} strike={u['strike']:<8} vol={u['volume']:>6,}  OI={u['openInterest']:>6,}  ratio={u['ratio']}×  {u['moneyness']}  expiry={u['expiry']}")
        print(f"\n  Résumé : {r['summary']}")
