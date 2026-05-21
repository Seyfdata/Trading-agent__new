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
from datetime import date, datetime, timedelta
from typing import Optional

try:
    from analysis.technical_indicators import clean_for_json as _clean_for_json
except ImportError:
    def _clean_for_json(obj):  # type: ignore[misc]
        import math, numpy as np  # noqa: F401
        if isinstance(obj, dict):
            return {k: _clean_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean_for_json(i) for i in obj]
        try:
            if hasattr(obj, "item"):
                return obj.item()
        except Exception:
            pass
        return obj

from config.settings import DEMO_MODE

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


# ── 0. Sessions & Asian Range (extrait dans analysis.smc.asian_range) ────────
# Import lazy pour eviter l'import circulaire smc_analyzer <-> smc/__init__
# Les fonctions sont importees dans le corps de analyze_ticker().

# ── Sessions / Structure / Blocks / Levels : extraits dans analysis/smc/ ──────────────
# Toutes les fonctions privées SMC sont lazy-importées dans analyze_ticker_smc().

# ── Confluences / Setup / Scoring (extraits dans analysis.smc.scoring) ─────────────────
# _count_confluences, _build_setup, _no_trade_reason : lazy-importés dans analyze_ticker_smc().

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

        # ── Pipeline SMC (ordre de dépendance) ───────────────────────────────
        from analysis.smc.structure import _analyze_structure  # lazy
        structure   = _analyze_structure(df)
        from analysis.smc.blocks import _detect_order_blocks, _detect_fvg  # lazy
        obs         = _detect_order_blocks(df, current_price)
        from analysis.smc.levels import _detect_liquidity, _discount_premium, _detect_equal_levels, _flag_inducement  # lazy
        liquidity   = _detect_liquidity(df)
        dp          = _discount_premium(structure["swing_highs"], structure["swing_lows"], current_price)

        # FVG filtré sur zone Discount grâce au midpoint
        fvgs        = _detect_fvg(df, current_price, range_midpoint=dp.get("midpoint"))

        # Niveaux égaux (EQH/EQL) → Inducement flags sur les OBs
        eq_levels   = _detect_equal_levels(df)
        obs         = _flag_inducement(obs, eq_levels)

        # Session Asie + sweeps de liquidité (données 1h)
        from analysis.smc.asian_range import detect_asian_range, detect_liquidity_sweeps  # lazy
        asian_range = detect_asian_range(ticker)
        sweeps      = detect_liquidity_sweeps(ticker, asian_range)

        # CHoCH valide uniquement s'il survient APRÈS un sweep de liquidité
        last_choch  = structure.get("last_choch")
        valid_choch = False
        if last_choch and sweeps:
            choch_date = last_choch.get("date", "")
            for sw in sweeps:
                if sw.get("date", "") <= choch_date:
                    valid_choch = True
                    break
        print(f"[SMC-Logic] Valid CHoCH after sweep: {valid_choch} for {ticker}")

        from analysis.smc.scoring import _count_confluences, _build_setup  # lazy
        confluences = _count_confluences(current_price, dp, obs, fvgs, df, structure)
        setup       = _build_setup(current_price, structure, obs, fvgs, liquidity, dp, confluences)

        _rr = setup.get("rr")
        if _rr is not None:
            print(f"[SMC] {ticker} R:R brut={_rr:.2f} valid={setup.get('rr_valid')} adjusted={setup.get('target_adjusted')}")
            if not setup.get("rr_valid"):
                print(f"[SMC] {ticker} REJETE : R:R {_rr:.2f} < 2.5")

        return _clean_for_json({
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
            "asian_range":      asian_range,
            "sweeps":           sweeps,
            "equal_levels":     eq_levels,
            "valid_choch":      valid_choch,
            "error":            None,
        })

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
        if ob["mitigated"]:
            st_tag = "⚠️ MITIGÉ"
        elif ob.get("partially_mitigated"):
            st_tag = "🔶 PARTIEL"
        else:
            st_tag = "✅ FRAIS"
        em   = "🟢" if ob["type"] == "BULL" else "🔴"
        dist = f"  [{ob['distance_pct']}% du prix]" if ob.get("distance_pct") is not None else ""
        lines.append(f"  {em} {ob['type']} OB  ${ob['low']:.2f}–${ob['high']:.2f}  ({ob['date']})  {st_tag}{dist}")
    for fvg in a.get("fvg", []):
        if fvg["filled"]:
            fvg_tag = "⚠️ COMBLÉ"
        elif fvg.get("partially_filled"):
            fvg_tag = "🔶 PARTIEL"
        else:
            fvg_tag = "✅ ACTIF"
        em   = "📊" if fvg["type"] == "BULL" else "📉"
        dist = f"  [{fvg['distance_pct']}% du prix]" if fvg.get("distance_pct") is not None else ""
        lines.append(f"  {em} FVG {fvg['type']}  ${fvg['low']:.2f}–${fvg['high']:.2f}  ({fvg['date']})  {fvg_tag}{dist}")
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


def analyze_ticker_smc(ticker: str) -> dict:
    """Alias de analyze_ticker qui surface les champs R:R au niveau racine du dict."""
    result = analyze_ticker(ticker)
    setup  = result.get("setup") or {}
    result["rr"]               = setup.get("rr")
    result["rr_valid"]         = setup.get("rr_valid", False)
    result["rr_rule"]          = setup.get("rr_rule", "min_2.5")
    result["target_adjusted"]  = setup.get("target_adjusted", False)
    result["rejection_reason"] = setup.get("rejection_reason")
    return result


# ── Test __main__ ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, sys
    sys.stdout.reconfigure(encoding="utf-8")

    for _ticker in ["NVDA", "AMD"]:
        print(f"\n{'='*56}")
        print(f"=== SMC Analyzer v2 — Test {_ticker} ===")
        print('='*56)
        _a = analyze_ticker(_ticker)
        if _a.get("error"):
            print("ERREUR :", _a["error"])
            continue
        print(format_smc_report(_a))
        print("\n--- Order Blocks ---")
        for ob in _a["order_blocks"]:
            print(f"  {ob['type']} OB ${ob['low']}–${ob['high']} | mitigated={ob['mitigated']} | partial={ob.get('partially_mitigated')} | dist={ob.get('distance_pct')}%")
        print("\n--- FVG ---")
        for fvg in _a["fvg"]:
            print(f"  {fvg['type']} FVG ${fvg['low']}–${fvg['high']} | filled={fvg['filled']} | partial={fvg.get('partially_filled')} | dist={fvg.get('distance_pct')}%")
        print("\n--- Confluences ---")
        cf = _a["confluences"]
        print(f"  Score: {cf['count']}/6 — {cf['conviction']}")
        for d in cf["details"]:
            print(f"  {d}")

