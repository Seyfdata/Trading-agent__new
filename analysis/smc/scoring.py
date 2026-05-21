"""
analysis.smc.scoring — Confluences, Setup et Raisons de non-trade.

Calcule le score de confluences (0-6), construit le setup LONG avec R:R >= 2.5,
et génère la raison textuelle de rejet quand les conditions ne sont pas réunies.
"""
from __future__ import annotations

try:
    import pandas as pd  # noqa: F401
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False


def _no_trade_reason(structure: dict, dp: dict, confluences: dict) -> str:
    parts = []
    if structure.get("bias") != "BULL":
        parts.append(f"biais {structure.get('bias', 'RANGE')}")
    if dp.get("current_zone") == "PREMIUM":
        parts.append("prix en PREMIUM (attendre pullback en discount)")
    if confluences.get("count", 0) < 3:
        parts.append(f"seulement {confluences.get('count', 0)}/6 confluences")
    return "Pas de setup : " + ", ".join(parts) if parts else "Conditions non réunies"


def _count_confluences(
    current_price: float,
    dp:            dict,
    obs:           list[dict],
    fvgs:          list[dict],
    df:            "pd.DataFrame",
    structure:     dict,
) -> dict:
    """
    Calcule le score de confluences pour un setup LONG (0–6).

    +1 Prix en DISCOUNT
    +1 Prix dans la zone OTE
    +1 Bull OB non mitigé à moins de 3 % du prix
    +1 FVG haussier non comblé à moins de 3 % du prix
    +1 Volume au-dessus de la moyenne 20j
    +1 Biais HTF BULL
    """
    count   = 0
    details = []

    zone = dp.get("current_zone", "")
    if zone in ("DISCOUNT", "OTE"):
        count += 1
        details.append(f"✅ Prix en {zone}")
    else:
        details.append("❌ Prix en PREMIUM")

    if zone == "OTE":
        count += 1
        details.append("✅ Zone OTE (62–79 % Fibonacci)")

    bull_obs_active = [
        o for o in obs
        if o["type"] == "BULL" and (not o["mitigated"] or o.get("partially_mitigated", False))
    ]
    near_ob = any(
        (o.get("distance_pct") or abs(current_price - (o["high"] + o["low"]) / 2) / current_price * 100) <= 5.0
        for o in bull_obs_active
    )
    if near_ob:
        best = min(bull_obs_active, key=lambda o: o.get("distance_pct") or 999)
        tag  = "partiel" if best.get("partially_mitigated") else "frais"
        count += 1
        details.append(f"✅ Bull OB {tag} à {best.get('distance_pct', '?')}% (${best['low']:.2f}–${best['high']:.2f})")
    else:
        details.append("❌ Pas de Bull OB proche (<5%)")

    bull_fvgs_active = [
        f for f in fvgs
        if f["type"] == "BULL" and (not f["filled"] or f.get("partially_filled", False))
    ]
    near_fvg = any(
        (f.get("distance_pct") or abs(current_price - (f["high"] + f["low"]) / 2) / current_price * 100) <= 3.0
        for f in bull_fvgs_active
    )
    if near_fvg:
        best_f = min(bull_fvgs_active, key=lambda f: f.get("distance_pct") or 999)
        tag_f  = "partiel" if best_f.get("partially_filled") else "actif"
        count += 1
        details.append(f"✅ FVG Bull {tag_f} à {best_f.get('distance_pct', '?')}% (${best_f['low']:.2f}–${best_f['high']:.2f})")
    else:
        details.append("❌ Pas de FVG proche (<3%)")

    if len(df) > 20:
        avg_vol  = float(df["Volume"].tail(20).mean())
        last_vol = float(df["Volume"].iloc[-1])
        if avg_vol > 0 and last_vol > avg_vol * 1.1:
            count += 1
            details.append(f"✅ Volume > moyenne 20j ({last_vol/avg_vol:.1f}×)")
        else:
            details.append("❌ Volume normal")

    if structure.get("bias") == "BULL":
        count += 1
        details.append("✅ Biais HTF BULL")
    else:
        details.append(f"❌ Biais HTF {structure.get('bias', 'RANGE')}")

    if count >= 5:
        conviction = "HIGH"
    elif count >= 3:
        conviction = "MEDIUM"
    else:
        conviction = "LOW"

    return {"count": count, "details": details, "conviction": conviction}


def _build_setup(
    current_price: float,
    structure:     dict,
    obs:           list[dict],
    fvgs:          list[dict],
    liquidity:     dict,
    dp:            dict,
    confluences:   dict,
) -> dict:
    """Construit le setup de trade si les conditions sont réunies. Enforce R:R >= 2.5."""
    _reason_no = _no_trade_reason(structure, dp, confluences)
    no_trade = {
        "has_setup":        False,
        "direction":        "NO TRADE",
        "entry":            None,
        "stop":             None,
        "target":           None,
        "rr_ratio":         None,
        "rr":               None,
        "rr_valid":         False,
        "rr_rule":          "min_2.5",
        "target_adjusted":  False,
        "rejection_reason": _reason_no,
        "invalidation":     None,
        "reasoning":        _reason_no,
    }

    if structure.get("bias") != "BULL":
        return no_trade
    if dp.get("current_zone") not in ("DISCOUNT", "OTE"):
        return no_trade
    if confluences.get("count", 0) < 3:
        return no_trade

    bull_obs_active = [o for o in obs if o["type"] == "BULL" and not o["mitigated"]]
    if bull_obs_active:
        ob    = bull_obs_active[-1]
        entry = round((ob["high"] + ob["low"]) / 2, 2)
    else:
        entry = round(current_price, 2)

    stop_ref = dp.get("range_low") or current_price * 0.97
    stop     = round(float(stop_ref) * 0.99, 2)

    bsl    = [lv for lv in liquidity.get("bsl_levels", []) if lv > entry]
    if bsl:
        target = round(min(bsl), 2)
    else:
        target = round(dp.get("range_high") or entry * 1.06, 2)

    risk   = entry - stop
    reward = target - entry
    rr_raw = round(reward / risk, 2) if risk > 0 else 0.0  # noqa: F841

    _MIN_RR        = 2.5
    target_adjusted = False

    if risk > 0:
        min_target = round(entry + _MIN_RR * risk, 2)
        if target < min_target:
            target          = min_target
            target_adjusted = True
            reward          = target - entry

    rr = round(reward / risk, 2) if risk > 0 else 0.0

    if rr < _MIN_RR:
        rejection = f"R:R {rr:.2f} < 2.5 minimum"
        return {
            **no_trade,
            "rr":               rr,
            "rr_valid":         False,
            "rr_rule":          "min_2.5",
            "target_adjusted":  False,
            "rejection_reason": rejection,
            "reasoning":        f"R:R insuffisant ({rr:.2f}x < {_MIN_RR}x minimum)",
        }

    parts = []
    if structure.get("bias") == "BULL":
        parts.append("Biais HTF haussier confirmé")
    if dp.get("current_zone") == "OTE":
        parts.append("prix dans la zone OTE optimale (62–79 %)")
    elif dp.get("current_zone") == "DISCOUNT":
        parts.append("prix en discount (<50 % du range)")
    if bull_obs_active:
        parts.append(f"Bull OB non mitigé @ ${bull_obs_active[-1]['high']:.2f}")
    if target_adjusted:
        parts.append(f"target ajusté pour R:R >= {_MIN_RR}")
    reasoning = " — ".join(parts) + f" ({confluences['count']}/6 confluences)"

    return {
        "has_setup":        True,
        "direction":        "LONG",
        "entry":            entry,
        "stop":             stop,
        "target":           target,
        "rr_ratio":         rr,
        "rr":               rr,
        "rr_valid":         True,
        "rr_rule":          "min_2.5",
        "target_adjusted":  target_adjusted,
        "rejection_reason": None,
        "invalidation":     f"Clôture sous ${stop:.2f}",
        "reasoning":        reasoning,
    }
