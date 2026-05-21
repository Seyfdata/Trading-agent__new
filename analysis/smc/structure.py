"""
analysis.smc.structure — Structure de marché SMC.

Swing highs/lows, BOS et CHoCH algorithmiques.
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


def _detect_swings(df: "pd.DataFrame", pivot: int = 2) -> tuple[list, list]:
    """
    Détecte les swing highs et swing lows sur le DataFrame.

    Un swing high : high[i] > high[i±1] ET high[i] > high[i±2]
    Un swing low  : low[i]  < low[i±1]  ET low[i]  < low[i±2]
    """
    highs = df["High"].values
    lows  = df["Low"].values
    dates = df.index.tolist()

    swing_highs: list[dict] = []
    swing_lows:  list[dict] = []

    for i in range(pivot, len(df) - pivot):
        is_sh = all(highs[i] > highs[i - k] for k in range(1, pivot + 1)) and \
                all(highs[i] > highs[i + k] for k in range(1, pivot + 1))
        if is_sh:
            swing_highs.append({
                "price": float(highs[i]),
                "date":  _fmt_date(dates[i]),
                "idx":   i,
            })

        is_sl = all(lows[i] < lows[i - k] for k in range(1, pivot + 1)) and \
                all(lows[i] < lows[i + k] for k in range(1, pivot + 1))
        if is_sl:
            swing_lows.append({
                "price": float(lows[i]),
                "date":  _fmt_date(dates[i]),
                "idx":   i,
            })

    return swing_highs, swing_lows


def _analyze_structure(df: "pd.DataFrame") -> dict:
    """
    Détermine le biais HTF (BULL / BEAR / RANGE), le dernier BOS et CHoCH.

    Règles :
        HH + HL → BULL BOS
        LH + LL → BEAR BOS
        HH + LL → CHoCH baissier (retournement après bull)
        LH + HL → CHoCH haussier (retournement après bear)
    """
    swing_highs, swing_lows = _detect_swings(df, pivot=2)

    bias      = "RANGE"
    last_bos  = None
    last_choch = None

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        sh_last, sh_prev = swing_highs[-1], swing_highs[-2]
        sl_last, sl_prev = swing_lows[-1],  swing_lows[-2]

        sh_rising = sh_last["price"] > sh_prev["price"]
        sl_rising = sl_last["price"] > sl_prev["price"]

        if sh_rising and sl_rising:
            bias     = "BULL"
            last_bos = {"direction": "BULL", "price": sh_last["price"], "date": sh_last["date"]}

        elif not sh_rising and not sl_rising:
            bias     = "BEAR"
            last_bos = {"direction": "BEAR", "price": sl_last["price"], "date": sl_last["date"]}

        elif sh_rising and not sl_rising:
            bias       = "BEAR"
            last_choch = {"direction": "BEAR", "price": sl_last["price"], "date": sl_last["date"]}

        else:
            bias       = "BULL"
            last_choch = {"direction": "BULL", "price": sh_last["price"], "date": sh_last["date"]}

    return {
        "bias":        bias,
        "last_bos":    last_bos,
        "last_choch":  last_choch,
        "swing_highs": [{"price": s["price"], "date": s["date"]} for s in swing_highs[-5:]],
        "swing_lows":  [{"price": s["price"], "date": s["date"]} for s in swing_lows[-5:]],
    }
