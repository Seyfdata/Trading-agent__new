"""
analysis.smc.blocks — Order Blocks & Fair Value Gaps.

Détecte les zones d'intérêt institutionnelles (OB) et les déséquilibres de prix (FVG).
"""
from __future__ import annotations


try:
    import pandas as pd  # noqa: F401
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False


def _fmt_date(ts) -> str:
    try:
        return str(ts)[:10]
    except Exception:
        return "?"


def _detect_order_blocks(df: "pd.DataFrame", current_price: float) -> list[dict]:
    """
    Détecte les Order Blocks récents (fenêtre : 3 derniers mois, ~63 bougies).

    Critères de validation :
      - Corps bougie OB > 0.3 % du prix (institution significative)
      - Mouvement impulsif sur 1–3 bougies max (pas de rampe lente)
      - Displacement >= 1.5× la taille du corps OB (vrai déséquilibre)

    Zones :
      Bull OB zone = [low, open]  — corps institutionnel baissier
      Bear OB zone = [open, high] — corps institutionnel haussier

    Mitigation (via prix actuel) :
      non mitigé      : prix n'a pas encore touché la zone
      partially_mitigated : prix a touché le haut de zone mais pas le milieu
      mitigated       : prix a dépassé le milieu (zone absorbée)
    """
    recent = df.tail(63).copy().reset_index()
    opens  = recent["Open"].values
    closes = recent["Close"].values
    highs  = recent["High"].values
    lows   = recent["Low"].values

    if "Date" in recent.columns:
        dates = recent["Date"].tolist()
    elif "index" in recent.columns:
        dates = recent["index"].tolist()
    else:
        dates = recent.index.tolist()

    obs: list[dict] = []
    MIN_BODY_PCT  = 0.003
    MIN_MOVE_PCT  = 2.0
    MIN_DISPLACE  = 1.5

    for i in range(1, len(recent) - 3):
        if opens[i] <= 0:
            continue

        candle_body = abs(closes[i] - opens[i])
        bearish     = closes[i] < opens[i]
        bullish     = closes[i] > opens[i]

        if candle_body / opens[i] < MIN_BODY_PCT:
            continue

        impulse_ok = False
        for end_offset in range(1, 4):
            end_i = i + end_offset
            if end_i >= len(recent):
                break
            move_pct   = (closes[end_i] - closes[i]) / closes[i] * 100
            impulse_sz = abs(closes[end_i] - closes[i])

            if bearish and move_pct >= MIN_MOVE_PCT and impulse_sz >= MIN_DISPLACE * candle_body:
                impulse_ok = True
                break
            if bullish and move_pct <= -MIN_MOVE_PCT and impulse_sz >= MIN_DISPLACE * candle_body:
                impulse_ok = True
                break

        if not impulse_ok:
            continue

        if bearish:
            ob_high = float(opens[i])
            ob_low  = float(lows[i])
            ob_mid  = (ob_low + ob_high) / 2

            if current_price <= ob_mid:
                mitigated, partially = True,  False
            elif current_price <= ob_high:
                mitigated, partially = False, True
            else:
                mitigated, partially = False, False

            dist = round(abs(current_price - ob_mid) / current_price * 100, 2) if current_price > 0 else None
            obs.append({
                "type":                "BULL",
                "high":                round(ob_high, 2),
                "low":                 round(ob_low,  2),
                "date":                _fmt_date(dates[i]),
                "mitigated":           bool(mitigated),
                "partially_mitigated": bool(partially),
                "distance_pct":        dist,
            })

        elif bullish:
            ob_low  = float(opens[i])
            ob_high = float(highs[i])
            ob_mid  = (ob_low + ob_high) / 2

            if current_price >= ob_mid:
                mitigated, partially = True,  False
            elif current_price >= ob_low:
                mitigated, partially = False, True
            else:
                mitigated, partially = False, False

            dist = round(abs(current_price - ob_mid) / current_price * 100, 2) if current_price > 0 else None
            obs.append({
                "type":                "BEAR",
                "high":                round(ob_high, 2),
                "low":                 round(ob_low,  2),
                "date":                _fmt_date(dates[i]),
                "mitigated":           bool(mitigated),
                "partially_mitigated": bool(partially),
                "distance_pct":        dist,
            })

    def _ob_priority(o: dict) -> int:
        if not o["mitigated"] and not o["partially_mitigated"]:
            return 0
        if o["partially_mitigated"]:
            return 1
        return 2

    bull_obs = sorted([o for o in obs if o["type"] == "BULL"][-4:], key=_ob_priority)[:3]
    bear_obs = sorted([o for o in obs if o["type"] == "BEAR"][-4:], key=_ob_priority)[:3]
    return bull_obs + bear_obs


def _detect_fvg(
    df: "pd.DataFrame",
    current_price: float,
    range_midpoint: "float | None" = None,
) -> list[dict]:
    """
    Détecte les Fair Value Gaps actifs (fenêtre : 3 derniers mois, ~63 bougies).

    Bull FVG : low[i+2] > high[i]  — gap laissé par un mouvement haussier
    Bear FVG : high[i+2] < low[i]  — gap laissé par un mouvement baissier

    Filtre Discount : si range_midpoint fourni, seuls les FVG Bull sous le midpoint sont gardés.
    Statut de remplissage (via prix actuel) :
      not filled          : prix n'a pas encore touché la zone
      partially_filled    : prix entré dans la zone mais < 50 % absorbé
      filled              : prix a dépassé le midpoint (zone consommée)
    """
    recent = df.tail(63)
    opens  = recent["Open"].values
    closes = recent["Close"].values
    highs  = recent["High"].values
    lows   = recent["Low"].values
    dates  = recent.index.tolist()

    fvgs: list[dict] = []
    MIN_GAP_PCT = 0.002

    for i in range(len(recent) - 2):
        mid_range = highs[i + 1] - lows[i + 1]
        mid_body  = abs(closes[i + 1] - opens[i + 1])
        if mid_range <= 0 or mid_body / mid_range < 0.60:
            continue

        if lows[i + 2] > highs[i]:
            gap_low  = float(highs[i])
            gap_high = float(lows[i + 2])
            gap_size = gap_high - gap_low
            gap_mid  = (gap_low + gap_high) / 2

            if current_price > 0 and gap_size / current_price < MIN_GAP_PCT:
                continue
            if range_midpoint is not None and gap_mid >= range_midpoint:
                continue

            if current_price <= gap_mid:
                filled, partially = True,  False
            elif current_price <= gap_high:
                filled, partially = False, True
            else:
                filled, partially = False, False

            dist = round(abs(current_price - gap_mid) / current_price * 100, 2) if current_price > 0 else None
            fvgs.append({
                "type":             "BULL",
                "high":             round(gap_high, 2),
                "low":              round(gap_low,  2),
                "date":             _fmt_date(dates[i + 1]),
                "filled":           bool(filled),
                "partially_filled": bool(partially),
                "distance_pct":     dist,
            })

        elif highs[i + 2] < lows[i]:
            gap_high = float(lows[i])
            gap_low  = float(highs[i + 2])
            gap_size = gap_high - gap_low
            gap_mid  = (gap_low + gap_high) / 2

            if current_price > 0 and gap_size / current_price < MIN_GAP_PCT:
                continue
            if range_midpoint is not None and gap_mid <= range_midpoint:
                continue

            if current_price >= gap_mid:
                filled, partially = True,  False
            elif current_price >= gap_low:
                filled, partially = False, True
            else:
                filled, partially = False, False

            dist = round(abs(current_price - gap_mid) / current_price * 100, 2) if current_price > 0 else None
            fvgs.append({
                "type":             "BEAR",
                "high":             round(gap_high, 2),
                "low":              round(gap_low,  2),
                "date":             _fmt_date(dates[i + 1]),
                "filled":           bool(filled),
                "partially_filled": bool(partially),
                "distance_pct":     dist,
            })

    active = [f for f in fvgs if not f["filled"]]
    return active[-6:]
