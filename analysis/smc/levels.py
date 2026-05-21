"""
analysis.smc.levels — Liquidité, Discount/Premium, Equal Levels, Inducement.

Détecte BSL/SSL, zones Discount/Premium/OTE, Equal Highs/Lows et Inducement traps.
"""
from __future__ import annotations

from analysis.smc.structure import _detect_swings

try:
    import pandas as pd  # noqa: F401
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False


def _detect_equal_levels(df: "pd.DataFrame", threshold: float = 0.0005) -> dict:
    """
    Détecte Equal Highs (EQH) et Equal Lows (EQL) avec tolérance 0.05%.
    Utilisé pour identifier les pièges institutionnels (Inducement).
    """
    recent = df.tail(63).copy()
    sh_list, sl_list = _detect_swings(recent, pivot=2)

    eqh_levels: list[dict] = []
    eql_levels: list[dict] = []

    sh_used: set[int] = set()
    for i, sh_i in enumerate(sh_list):
        if i in sh_used:
            continue
        group = [sh_i]
        for j, sh_j in enumerate(sh_list):
            if j != i and j not in sh_used:
                if abs(sh_i["price"] - sh_j["price"]) / max(sh_i["price"], 1e-9) <= threshold:
                    group.append(sh_j)
                    sh_used.add(j)
        if len(group) >= 2:
            avg_price = sum(g["price"] for g in group) / len(group)
            eqh_levels.append({
                "price":    round(avg_price, 2),
                "count":    len(group),
                "dates":    [g["date"] for g in group],
                "last_idx": max(g["idx"] for g in group),
            })

    sl_used: set[int] = set()
    for i, sl_i in enumerate(sl_list):
        if i in sl_used:
            continue
        group = [sl_i]
        for j, sl_j in enumerate(sl_list):
            if j != i and j not in sl_used:
                if abs(sl_i["price"] - sl_j["price"]) / max(sl_i["price"], 1e-9) <= threshold:
                    group.append(sl_j)
                    sl_used.add(j)
        if len(group) >= 2:
            avg_price = sum(g["price"] for g in group) / len(group)
            eql_levels.append({
                "price":    round(avg_price, 2),
                "count":    len(group),
                "dates":    [g["date"] for g in group],
                "last_idx": max(g["idx"] for g in group),
            })

    return {"eqh": eqh_levels, "eql": eql_levels}


def _flag_inducement(obs: list, eq_levels: dict, threshold_pct: float = 0.02) -> list:
    """
    Flags les OBs qui sont des pièges institutionnels (Inducement).

    Bull OB avec EQH juste au-dessus (< 2%) = stops retail ciblés → Danger.
    Bear OB avec EQL juste en-dessous (< 2%) = acheteurs piégés → Danger.
    """
    eqh_prices = [e["price"] for e in eq_levels.get("eqh", [])]
    eql_prices = [e["price"] for e in eq_levels.get("eql", [])]

    for ob in obs:
        ob["inducement"]        = False
        ob["inducement_detail"] = None

        if ob["type"] == "BULL":
            for eqh_p in eqh_prices:
                if eqh_p > ob["high"]:
                    dist = (eqh_p - ob["high"]) / ob["high"]
                    if dist <= threshold_pct:
                        ob["inducement"]        = True
                        ob["inducement_detail"] = f"EQH ${eqh_p:.2f} au-dessus — stops retail ciblés"
                        break
        elif ob["type"] == "BEAR":
            for eql_p in eql_prices:
                if eql_p < ob["low"]:
                    dist = (ob["low"] - eql_p) / ob["low"]
                    if dist <= threshold_pct:
                        ob["inducement"]        = True
                        ob["inducement_detail"] = f"EQL ${eql_p:.2f} en-dessous — puits de liquidité"
                        break
    return obs


def _detect_liquidity(df: "pd.DataFrame", eq_threshold: float = 0.003) -> dict:
    """
    Détecte BSL (Buy-side) et SSL (Sell-side) via swing levels et equal highs/lows.

    Equal highs : 2+ swing highs à moins de 0.3 % l'un de l'autre.
    Equal lows  : 2+ swing lows  à moins de 0.3 % l'un de l'autre.
    """
    recent = df.tail(63)
    sh_list, sl_list = _detect_swings(recent, pivot=2)

    sh_prices = [s["price"] for s in sh_list]
    sl_prices = [s["price"] for s in sl_list]

    def cluster(prices: list[float], threshold: float) -> list[float]:
        result: list[float] = []
        used = set()
        for i, p in enumerate(prices):
            if i in used:
                continue
            group = [p]
            for j, q in enumerate(prices):
                if j != i and j not in used:
                    if abs(p - q) / max(p, 1e-9) <= threshold:
                        group.append(q)
                        used.add(j)
            result.append(round(sum(group) / len(group), 2))
        return sorted(set(result), reverse=True)

    bsl = cluster(sh_prices, eq_threshold) if sh_prices else []
    ssl = cluster(sl_prices, eq_threshold) if sl_prices else []

    return {
        "bsl_levels": bsl[:5],
        "ssl_levels": ssl[:5],
    }


def _discount_premium(
    swing_highs: list[dict],
    swing_lows:  list[dict],
    current_price: float,
) -> dict:
    """
    Calcule les zones Discount / Premium et l'OTE (Optimal Trade Entry).

    OTE (pour LONG) = 62 %–79 % de retracement depuis le swing high :
        ote_high = range_high - 0.62 × range
        ote_low  = range_high - 0.79 × range
    """
    empty = {
        "range_high": None, "range_low": None,
        "midpoint":   None, "ote_high":  None, "ote_low": None,
        "current_zone": "RANGE",
    }

    if not swing_highs or not swing_lows:
        return empty

    range_high = max(s["price"] for s in swing_highs)
    range_low  = min(s["price"] for s in swing_lows)
    rng        = range_high - range_low

    if rng <= 0:
        return empty

    midpoint = range_low + 0.50 * rng
    ote_high = round(range_high - 0.62 * rng, 2)
    ote_low  = round(range_high - 0.79 * rng, 2)

    if current_price >= midpoint:
        zone = "PREMIUM"
    elif ote_low <= current_price <= ote_high:
        zone = "OTE"
    else:
        zone = "DISCOUNT"

    return {
        "range_high":   round(range_high, 2),
        "range_low":    round(range_low,  2),
        "midpoint":     round(midpoint,   2),
        "ote_high":     ote_high,
        "ote_low":      ote_low,
        "current_zone": zone,
    }
