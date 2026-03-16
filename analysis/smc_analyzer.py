"""
SMC Analyzer — Analyse Smart Money Concepts (algorithmique).

DEMO_MODE = True  : analyse pure pandas/yfinance, sans appel API.
DEMO_MODE = False : délègue à Claude API (à implémenter Phase 3B).

Usage :
    from analysis.smc_analyzer import analyze_ticker, format_smc_report
    result = analyze_ticker("NVDA")
    print(format_smc_report(result))
"""

from __future__ import annotations

import traceback
from datetime import date
from typing import Optional

# ── Mode de fonctionnement ────────────────────────────────────────────────────
DEMO_MODE = True   # Passer à False pour activer Claude API (Phase 3B)

# ── Dépendances optionnelles ──────────────────────────────────────────────────
try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


# ── Helpers internes ──────────────────────────────────────────────────────────

def _fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> Optional["pd.DataFrame"]:
    """Récupère l'historique de prix via yfinance."""
    if not _YF_OK or not _PANDAS_OK:
        return None
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def _fmt_date(ts) -> str:
    """Extrait une date ISO-8601 depuis un timestamp pandas ou une string."""
    try:
        return str(ts)[:10]
    except Exception:
        return "?"


# ── 1. Structure de marché ────────────────────────────────────────────────────

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
            # HH mais LL → retournement baissier probable
            bias       = "BEAR"
            last_choch = {"direction": "BEAR", "price": sl_last["price"], "date": sl_last["date"]}

        else:
            # LH mais HL → retournement haussier probable
            bias       = "BULL"
            last_choch = {"direction": "BULL", "price": sh_last["price"], "date": sh_last["date"]}

    return {
        "bias":        bias,
        "last_bos":    last_bos,
        "last_choch":  last_choch,
        "swing_highs": [{"price": s["price"], "date": s["date"]} for s in swing_highs[-5:]],
        "swing_lows":  [{"price": s["price"], "date": s["date"]} for s in swing_lows[-5:]],
    }


# ── 2. Order Blocks ──────────────────────────────────────────────────────────

def _detect_order_blocks(df: "pd.DataFrame", current_price: float) -> list[dict]:
    """
    Détecte les Order Blocks récents (fenêtre : 3 derniers mois, ~63 bougies).

    Bull OB  : dernière bougie baissière avant un mouvement haussier impulsif (>2 %).
    Bear OB  : dernière bougie haussière avant un mouvement baissier impulsif (>2 %).
    Mitigated : le prix est revenu dans la zone depuis sa création.
    """
    recent = df.tail(63).copy().reset_index()
    opens  = recent["Open"].values
    closes = recent["Close"].values
    highs  = recent["High"].values
    lows   = recent["Low"].values
    # Récupérer les dates depuis l'index ou la colonne "Date"
    if "Date" in recent.columns:
        dates = recent["Date"].tolist()
    elif "index" in recent.columns:
        dates = recent["index"].tolist()
    else:
        dates = recent.index.tolist()

    obs: list[dict] = []

    for i in range(1, len(recent) - 3):
        end_i    = min(i + 3, len(recent) - 1)
        move_pct = (closes[end_i] - closes[i]) / closes[i] * 100

        bearish_candle = closes[i] < opens[i]
        bullish_candle = closes[i] > opens[i]

        if bearish_candle and move_pct > 2.0:
            # Bull OB : prix revenu dans la zone = mitigé
            mitigated = current_price <= highs[i]
            obs.append({
                "type":      "BULL",
                "high":      round(float(highs[i]), 2),
                "low":       round(float(lows[i]), 2),
                "date":      _fmt_date(dates[i]),
                "mitigated": bool(mitigated),
            })

        elif bullish_candle and move_pct < -2.0:
            mitigated = current_price >= lows[i]
            obs.append({
                "type":      "BEAR",
                "high":      round(float(highs[i]), 2),
                "low":       round(float(lows[i]), 2),
                "date":      _fmt_date(dates[i]),
                "mitigated": bool(mitigated),
            })

    bull_obs = [o for o in obs if o["type"] == "BULL"][-3:]
    bear_obs = [o for o in obs if o["type"] == "BEAR"][-3:]
    return bull_obs + bear_obs


# ── 3. Fair Value Gaps ───────────────────────────────────────────────────────

def _detect_fvg(df: "pd.DataFrame", current_price: float) -> list[dict]:
    """
    Détecte les Fair Value Gaps non comblés (fenêtre : 3 derniers mois).

    Bullish FVG  : low[i+2] > high[i]  (gap entre bougie 1 et 3)
    Bearish FVG  : high[i+2] < low[i]
    Filled       : le prix est passé à travers la zone.
    """
    recent = df.tail(63)
    highs  = recent["High"].values
    lows   = recent["Low"].values
    dates  = recent.index.tolist()

    fvgs: list[dict] = []

    for i in range(len(recent) - 2):
        # Bullish FVG
        if lows[i + 2] > highs[i]:
            gap_low  = float(highs[i])
            gap_high = float(lows[i + 2])
            filled   = current_price < gap_low
            fvgs.append({
                "type":   "BULL",
                "high":   round(gap_high, 2),
                "low":    round(gap_low, 2),
                "date":   _fmt_date(dates[i + 1]),
                "filled": filled,
            })

        # Bearish FVG
        elif highs[i + 2] < lows[i]:
            gap_high = float(lows[i])
            gap_low  = float(highs[i + 2])
            filled   = current_price > gap_high
            fvgs.append({
                "type":   "BEAR",
                "high":   round(gap_high, 2),
                "low":    round(gap_low, 2),
                "date":   _fmt_date(dates[i + 1]),
                "filled": filled,
            })

    # Retourner les 6 FVG non comblés les plus récents
    unfilled = [f for f in fvgs if not f["filled"]]
    return unfilled[-6:]


# ── 4. Liquidity Map ─────────────────────────────────────────────────────────

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
        """Regroupe les prix proches et retourne les niveaux de liquidité."""
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


# ── 5. Discount / Premium / OTE ──────────────────────────────────────────────

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
    ote_high = round(range_high - 0.62 * rng, 2)   # 38 % du range depuis le bas
    ote_low  = round(range_high - 0.79 * rng, 2)   # 21 % du range depuis le bas

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


# ── 6. Confluences ─────────────────────────────────────────────────────────────

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

    # 1. Discount
    zone = dp.get("current_zone", "")
    if zone in ("DISCOUNT", "OTE"):
        count += 1
        details.append(f"✅ Prix en {zone}")
    else:
        details.append("❌ Prix en PREMIUM")

    # 2. OTE
    if zone == "OTE":
        count += 1
        details.append("✅ Zone OTE (62–79 % Fibonacci)")

    # 3. Bull OB non mitigé proche
    bull_obs_active = [o for o in obs if o["type"] == "BULL" and not o["mitigated"]]
    near_ob = any(
        abs(current_price - (o["high"] + o["low"]) / 2) / current_price <= 0.03
        for o in bull_obs_active
    )
    if near_ob:
        count += 1
        details.append("✅ Bull OB non mitigé à proximité")
    else:
        details.append("❌ Pas de Bull OB proche")

    # 4. FVG haussier non comblé proche
    bull_fvgs_active = [f for f in fvgs if f["type"] == "BULL" and not f["filled"]]
    near_fvg = any(
        abs(current_price - (f["high"] + f["low"]) / 2) / current_price <= 0.03
        for f in bull_fvgs_active
    )
    if near_fvg:
        count += 1
        details.append("✅ FVG haussier non comblé proche")
    else:
        details.append("❌ Pas de FVG proche")

    # 5. Volume
    if len(df) > 20:
        avg_vol  = float(df["Volume"].tail(20).mean())
        last_vol = float(df["Volume"].iloc[-1])
        if avg_vol > 0 and last_vol > avg_vol * 1.1:
            count += 1
            details.append(f"✅ Volume > moyenne 20j ({last_vol/avg_vol:.1f}×)")
        else:
            details.append("❌ Volume normal")

    # 6. Biais HTF
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


# ── 7. Setup ──────────────────────────────────────────────────────────────────

def _build_setup(
    current_price: float,
    structure:     dict,
    obs:           list[dict],
    fvgs:          list[dict],
    liquidity:     dict,
    dp:            dict,
    confluences:   dict,
) -> dict:
    """Construit le setup de trade si les conditions sont réunies."""
    no_trade = {
        "has_setup":     False,
        "direction":     "NO TRADE",
        "entry":         None,
        "stop":          None,
        "target":        None,
        "rr_ratio":      None,
        "invalidation":  None,
        "reasoning":     _no_trade_reason(structure, dp, confluences),
    }

    if structure.get("bias") != "BULL":
        return no_trade
    if dp.get("current_zone") not in ("DISCOUNT", "OTE"):
        return no_trade
    if confluences.get("count", 0) < 3:
        return no_trade

    # Entry : mid du bull OB non mitigé le plus récent, ou prix actuel
    bull_obs_active = [o for o in obs if o["type"] == "BULL" and not o["mitigated"]]
    if bull_obs_active:
        ob    = bull_obs_active[-1]
        entry = round((ob["high"] + ob["low"]) / 2, 2)
    else:
        entry = round(current_price, 2)

    # Stop : 1 % sous le range_low (plancher de la structure)
    stop_ref = dp.get("range_low") or current_price * 0.97
    stop     = round(float(stop_ref) * 0.99, 2)

    # Target : premier BSL level au-dessus de l'entry
    bsl    = [l for l in liquidity.get("bsl_levels", []) if l > entry]
    if bsl:
        target = round(min(bsl), 2)
    else:
        target = round(dp.get("range_high") or entry * 1.06, 2)

    risk   = entry - stop
    reward = target - entry
    rr     = round(reward / risk, 2) if risk > 0 else 0.0

    parts = []
    if structure.get("bias") == "BULL":
        parts.append("Biais HTF haussier confirmé")
    if dp.get("current_zone") == "OTE":
        parts.append("prix dans la zone OTE optimale (62–79 %)")
    elif dp.get("current_zone") == "DISCOUNT":
        parts.append("prix en discount (<50 % du range)")
    if bull_obs_active:
        parts.append(f"Bull OB non mitigé @ ${bull_obs_active[-1]['high']:.2f}")
    reasoning = " — ".join(parts) + f" ({confluences['count']}/6 confluences)"

    return {
        "has_setup":    True,
        "direction":    "LONG",
        "entry":        entry,
        "stop":         stop,
        "target":       target,
        "rr_ratio":     rr,
        "invalidation": f"Clôture sous ${stop:.2f}",
        "reasoning":    reasoning,
    }


def _no_trade_reason(structure: dict, dp: dict, confluences: dict) -> str:
    parts = []
    if structure.get("bias") != "BULL":
        parts.append(f"biais {structure.get('bias', 'RANGE')}")
    if dp.get("current_zone") == "PREMIUM":
        parts.append("prix en PREMIUM (attendre pullback en discount)")
    if confluences.get("count", 0) < 3:
        parts.append(f"seulement {confluences.get('count', 0)}/6 confluences")
    return "Pas de setup : " + ", ".join(parts) if parts else "Conditions non réunies"


# ── Fonction principale ───────────────────────────────────────────────────────

def analyze_ticker(ticker: str, timeframes: list | None = None) -> dict:
    """
    Analyse SMC complète pour un ticker.

    En DEMO_MODE : analyse algorithmique pure (yfinance + pandas).
    En LIVE mode : délègue à Claude API (à implémenter Phase 3B).

    Retourne un dict complet avec structure, OBs, FVGs, liquidité,
    discount/premium, confluences et setup.
    """
    if timeframes is None:
        timeframes = ["1d"]

    base = {
        "ticker":           ticker,
        "timeframe":        "1d",
        "analysis_date":    date.today().isoformat(),
        "current_price":    None,
        "mode":             "DEMO" if DEMO_MODE else "LIVE",
        "structure":        {},
        "order_blocks":     [],
        "fvg":              [],
        "liquidity":        {"bsl_levels": [], "ssl_levels": []},
        "discount_premium": {},
        "confluences":      {"count": 0, "details": [], "conviction": "LOW"},
        "setup":            {"has_setup": False, "direction": "NO TRADE"},
        "error":            None,
    }

    if not DEMO_MODE:
        base["error"] = "Mode LIVE non implémenté — activez DEMO_MODE=True"
        return base

    if not _YF_OK:
        base["error"] = "yfinance non installé (pip install yfinance)"
        return base

    if not _PANDAS_OK:
        base["error"] = "pandas non installé (pip install pandas)"
        return base

    try:
        df = _fetch_history(ticker, period="1y", interval="1d")
        if df is None or len(df) < 30:
            base["error"] = f"Données insuffisantes pour {ticker}"
            return base

        current_price = float(df["Close"].iloc[-1])

        structure   = _analyze_structure(df)
        obs         = _detect_order_blocks(df, current_price)
        fvgs        = _detect_fvg(df, current_price)
        liquidity   = _detect_liquidity(df)
        dp          = _discount_premium(structure["swing_highs"], structure["swing_lows"], current_price)
        confluences = _count_confluences(current_price, dp, obs, fvgs, df, structure)
        setup       = _build_setup(current_price, structure, obs, fvgs, liquidity, dp, confluences)

        return {
            "ticker":           ticker,
            "timeframe":        "1d",
            "analysis_date":    date.today().isoformat(),
            "current_price":    round(current_price, 2),
            "mode":             "DEMO",
            "structure":        structure,
            "order_blocks":     obs,
            "fvg":              fvgs,
            "liquidity":        liquidity,
            "discount_premium": dp,
            "confluences":      confluences,
            "setup":            setup,
            "error":            None,
        }

    except Exception as exc:
        base["error"] = f"Erreur analyse {ticker} : {exc}"
        traceback.print_exc()
        return base


# ── Rapport texte ─────────────────────────────────────────────────────────────

def format_smc_report(a: dict) -> str:
    """
    Formate l'analyse en rapport texte SMC PRO v2.

    Même style que le skill trading-coach :
    🎯 SMC PRO {TICKER} Daily | {DATE}
    📈 HTF Bias : ...
    🗺️  LIQUIDITY MAP : ...
    🟢 ZONES D'INTÉRÊT : ...
    📊 CONFLUENCES : ...
    🎯 TRADE SETUP : ...
    📈 CONVICTION : ...
    """
    if a.get("error"):
        return f"❌ Erreur : {a['error']}"

    ticker = a.get("ticker", "?")
    dt     = a.get("analysis_date", "?")
    st     = a.get("structure", {})
    dp     = a.get("discount_premium", {})
    cf     = a.get("confluences", {})
    su     = a.get("setup", {})
    liq    = a.get("liquidity", {})
    cp     = a.get("current_price")

    bias       = st.get("bias", "RANGE")
    bias_emoji = "📈" if bias == "BULL" else "📉" if bias == "BEAR" else "↔️"

    lines = [
        f"🎯 SMC PRO {ticker} Daily | {dt}",
        "─" * 48,
        "",
    ]

    # HTF Bias
    bos   = st.get("last_bos")
    choch = st.get("last_choch")
    if bos:
        lines.append(f"{bias_emoji} HTF Bias : {bias}  |  BOS {bos['direction']} @ ${bos['price']:.2f}  ({bos['date']})")
    elif choch:
        lines.append(f"{bias_emoji} HTF Bias : {bias}  |  CHoCH {choch['direction']} @ ${choch['price']:.2f}  ({choch['date']})")
    else:
        lines.append(f"{bias_emoji} HTF Bias : {bias}")
    lines.append("")

    # Swing levels récents
    sh = st.get("swing_highs", [])
    sl = st.get("swing_lows",  [])
    if sh:
        lines.append("  SH récents : " + "  ".join(f"${s['price']:.2f} ({s['date']})" for s in sh[-3:]))
    if sl:
        lines.append("  SL récents : " + "  ".join(f"${s['price']:.2f} ({s['date']})" for s in sl[-3:]))
    lines.append("")

    # Liquidity Map
    bsl = liq.get("bsl_levels", [])
    ssl = liq.get("ssl_levels", [])
    lines.append("🗺️  LIQUIDITY MAP :")
    if bsl:
        lines.append("  🔴 BSL (cibles haussières) : " + "  |  ".join(f"${l:.2f}" for l in bsl[:3]))
    if ssl:
        lines.append("  🟢 SSL (cibles baissières) : " + "  |  ".join(f"${l:.2f}" for l in ssl[:3]))
    lines.append("")

    # Zones d'intérêt
    lines.append("🟢 ZONES D'INTÉRÊT :")
    for ob in a.get("order_blocks", []):
        st_tag = "⚠️ MITIGÉ" if ob["mitigated"] else "✅ ACTIF"
        em     = "🟢" if ob["type"] == "BULL" else "🔴"
        lines.append(f"  {em} {ob['type']} OB  ${ob['low']:.2f}–${ob['high']:.2f}  ({ob['date']})  {st_tag}")
    for fvg in a.get("fvg", []):
        em = "📊" if fvg["type"] == "BULL" else "📉"
        lines.append(f"  {em} FVG {fvg['type']}  ${fvg['low']:.2f}–${fvg['high']:.2f}  ({fvg['date']})  ✅ ACTIF")
    lines.append("")

    # Discount / Premium
    if dp.get("range_high") and dp.get("range_low"):
        zone_em = "🟢" if dp.get("current_zone") == "DISCOUNT" else \
                  "🔵" if dp.get("current_zone") == "OTE"       else "🔴"
        lines.append("📐 DISCOUNT / PREMIUM :")
        lines.append(f"  Range   : ${dp['range_low']:.2f}  —  ${dp['range_high']:.2f}")
        lines.append(f"  OTE     : ${dp.get('ote_low', 0):.2f}  —  ${dp.get('ote_high', 0):.2f}  (62–79 % retrace)")
        if cp:
            lines.append(f"  Prix    : ${cp:.2f}  →  {zone_em} {dp.get('current_zone', '?')}")
        lines.append("")

    # Confluences
    lines.append(f"📊 CONFLUENCES ({cf.get('count', 0)}/6) :")
    for detail in cf.get("details", []):
        lines.append(f"  {detail}")
    lines.append("")

    # Trade Setup
    lines.append("🎯 TRADE SETUP :")
    if su.get("has_setup"):
        lines.append(f"  Direction    : {su['direction']}")
        lines.append(f"  Entry        : ${su['entry']:.2f}")
        lines.append(f"  Stop         : ${su['stop']:.2f}")
        lines.append(f"  Target       : ${su['target']:.2f}")
        lines.append(f"  R:R          : {su['rr_ratio']:.2f}R")
        lines.append(f"  Invalidation : {su['invalidation']}")
        lines.append(f"  Raisonnement : {su['reasoning']}")
    else:
        lines.append(f"  {su.get('reasoning', 'Conditions non réunies')}")
    lines.append("")

    conviction = cf.get("conviction", "LOW")
    conv_em    = "🔥" if conviction == "HIGH" else "📈" if conviction == "MEDIUM" else "📊"
    lines.append(f"📈 CONVICTION : {conv_em} {conviction}  ({cf.get('count', 0)}/6 confluences)")
    lines.append(f"🤖 Mode : DÉMO (analyse algorithmique)")

    return "\n".join(lines)


# ── Test __main__ ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=== SMC Analyzer — Test NVDA ===\n")
    analysis = analyze_ticker("NVDA")

    if analysis.get("error"):
        print("ERREUR :", analysis["error"])
    else:
        print(format_smc_report(analysis))
        print("\n--- Structure ---")
        print(json.dumps(analysis["structure"], indent=2))
        print("\n--- Discount/Premium ---")
        print(json.dumps(analysis["discount_premium"], indent=2))
        print("\n--- Setup ---")
        print(json.dumps(analysis["setup"], indent=2))
        print("\n--- Confluences ---")
        print(json.dumps(analysis["confluences"], indent=2))
