"""
Unified Scorer — Croise setup_detector et smc_analyzer pour un score de conviction unifié.

Score sur 10 points :
  setup_detector (4 pts) :
    DISCOUNT_ZONE    → +1.0
    SMA200_BOUNCE    → +1.5  (signal technique fort)
    VOLUME_MOMENTUM  → +1.5  (institutions actives)

  smc_analyzer (6 pts) :
    Biais HTF BULL            → +1
    Prix en DISCOUNT ou OTE   → +1
    Bull OB non mitigé <5 %   → +1
    FVG haussier non comblé   → +1
    SSL balayé récemment      → +1
    Score confluences SMC ≥ 4 → +1

Grades :
    8–10  → A+  (toutes les étoiles alignées)
    6–7   → A   (setup solide)
    4–5   → B   (setup correct)
    2–3   → C   (setup faible)
    0–1   → NO TRADE

Usage :
    from analysis.unified_scorer import unified_analysis, scan_unified
    result = unified_analysis("NVDA")
    top5   = scan_unified(top_n=5)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import WATCHLIST

# ── Mode (doit correspondre à smc_analyzer) ───────────────────────────────────
DEMO_MODE = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _grade(score: float) -> str:
    if score >= 8:
        return "A+"
    if score >= 6:
        return "A"
    if score >= 4:
        return "B"
    if score >= 2:
        return "C"
    return "NO TRADE"


def _fresh_ob_nearby(obs: list[dict], current_price: float, threshold: float = 0.05) -> bool:
    """
    Bull OB actif (non mitigé ou partiellement mitigé) à moins de `threshold*100`% du prix.
    Utilise distance_pct si disponible (calculé par smc_analyzer v2), sinon fallback.
    """
    if current_price <= 0:
        return False
    for ob in obs:
        if ob.get("type") != "BULL":
            continue
        # OB actif = non mitigé OU partiellement mitigé
        if ob.get("mitigated") and not ob.get("partially_mitigated"):
            continue
        dist_pct = ob.get("distance_pct")
        if dist_pct is not None:
            if dist_pct <= threshold * 100:
                return True
        else:
            mid  = (ob["high"] + ob["low"]) / 2
            if abs(current_price - mid) / current_price <= threshold:
                return True
    return False


def _fvg_nearby(fvgs: list[dict], current_price: float, threshold: float = 0.03) -> bool:
    """
    FVG haussier actif (non comblé ou partiellement comblé) à moins de `threshold*100`% du prix.
    Seuil réduit à 3% (vs 5% pour OB) — FVG moins large, doit être plus précis.
    """
    if current_price <= 0:
        return False
    for fvg in fvgs:
        if fvg.get("type") != "BULL":
            continue
        # FVG actif = non comblé OU partiellement comblé
        if fvg.get("filled") and not fvg.get("partially_filled"):
            continue
        dist_pct = fvg.get("distance_pct")
        if dist_pct is not None:
            if dist_pct <= threshold * 100:
                return True
        else:
            mid  = (fvg["high"] + fvg["low"]) / 2
            if abs(current_price - mid) / current_price <= threshold:
                return True
    return False


def _ssl_swept_recently(ticker: str, ssl_levels: list[float], current_price: float,
                        lookback: int = 10) -> bool:
    """
    Retourne True si le prix est récemment passé sous un niveau SSL puis est remonté.
    Signe d'une chasse aux stops — pattern "sweep & reverse" SMC.
    """
    if not ssl_levels or current_price <= 0:
        return False
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period="1mo", interval="1d")
        if df is None or len(df) < 5:
            return False
        past_lows   = df["Low"].values[-lookback:-1]   # lows précédents (hors dernier)
        for ssl in ssl_levels:
            swept = any(low < ssl for low in past_lows)
            above = current_price > ssl
            if swept and above:
                return True
    except Exception:
        pass
    return False


def _top_tickers_from_db(top_n: int = 10) -> list[str]:
    """
    Retourne les `top_n` tickers par score composite du jour (depuis scores_history).
    Retourne WATCHLIST[:top_n] si la DB est vide ou inaccessible.
    """
    try:
        from database.models import DB_PATH
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """
                SELECT ticker, total_score
                FROM scores_history
                WHERE date = (SELECT MAX(date) FROM scores_history)
                ORDER BY total_score DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()
        tickers = [r[0] for r in rows]
        return tickers if tickers else list(WATCHLIST)[:top_n]
    except Exception:
        return list(WATCHLIST)[:top_n]


def _build_reasoning(
    ticker:         str,
    score:          float,
    grade:          str,
    breakdown:      dict,
    setup_signals:  list[str],
    current_price:  float,
) -> str:
    """Construit un texte explicatif synthétique."""
    positives = []
    negatives = []

    if breakdown["sma200_bounce"]:
        positives.append("SMA200 Bounce confirmé")
    if breakdown["volume_momentum"]:
        positives.append("momentum institutionnel (volume ×2+)")
    if breakdown["discount_zone"]:
        positives.append("Discount Zone détectée")
    if breakdown["htf_bull"]:
        positives.append("biais HTF haussier")
    if breakdown["in_discount_or_ote"]:
        positives.append("prix en zone OTE/Discount")
    if breakdown["fresh_ob_nearby"]:
        positives.append("Bull OB non mitigé proche")
    if breakdown["fvg_nearby"]:
        positives.append("FVG haussier actif")
    if breakdown["ssl_swept"]:
        positives.append("SSL récemment balayé (liquidité prise)")
    if breakdown["confluences_strong"]:
        positives.append("confluences SMC solides (≥4)")
    if breakdown.get("options_bullish"):
        positives.append("options flow BULLISH")

    if not breakdown["htf_bull"]:
        negatives.append("biais HTF non haussier")
    if not breakdown["fresh_ob_nearby"]:
        negatives.append("pas de Bull OB frais proche")
    if not breakdown["fvg_nearby"]:
        negatives.append("pas de FVG haussier proche")

    text = f"{ticker} @ ${current_price:.2f} — "
    if positives:
        text += ", ".join(positives)
    if negatives:
        text += " | ⚠️ " + ", ".join(negatives)
    text += f". Score {score:.1f}/10 — Grade {grade}."
    return text


# ── Analyse unifiée ───────────────────────────────────────────────────────────

def unified_analysis(ticker: str) -> dict:
    """
    Combine setup_detector et smc_analyzer en un score de conviction unifié (0–10).

    Retourne un dict complet avec grade, breakdown, entry/stop/target, reasoning.
    """
    base = {
        "ticker":                ticker,
        "unified_score":         0.0,
        "grade":                 "NO TRADE",
        "setup_detector_signals": [],
        "smc_analysis":          {},
        "scoring_breakdown":     {},
        "best_entry":            None,
        "best_stop":             None,
        "best_target":           None,
        "rr_ratio":              None,
        "reasoning":             f"Erreur lors de l'analyse de {ticker}",
        "error":                 None,
    }

    # ── 1. Setup detector ────────────────────────────────────────────────────
    detected_types: set[str] = set()
    try:
        from analysis.setup_detector import detect_setups
        setups_all = detect_setups([ticker])
        detected_types = {s["setup_type"] for s in setups_all if s.get("ticker") == ticker}
        base["setup_detector_signals"] = list(detected_types)
    except Exception as e:
        base["setup_detector_signals"] = []

    # ── 2. SMC analyzer ──────────────────────────────────────────────────────
    smc = {}
    try:
        from analysis.smc_analyzer import analyze_ticker
        smc = analyze_ticker(ticker)
        if smc.get("error"):
            base["error"] = smc["error"]
    except Exception as e:
        base["error"] = str(e)

    if not smc:
        return base

    # ── 3. Extraire les données SMC ──────────────────────────────────────────
    structure = smc.get("structure", {})
    dp        = smc.get("discount_premium", {})
    obs       = smc.get("order_blocks", [])
    fvgs      = smc.get("fvg", [])
    liq       = smc.get("liquidity", {})
    cf        = smc.get("confluences", {})
    setup_smc = smc.get("setup", {})
    cp        = smc.get("current_price") or 0.0

    ssl_levels = liq.get("ssl_levels", [])

    # ── 4. Calcul du score ───────────────────────────────────────────────────
    score = 0.0

    # setup_detector (4 pts)
    d_discount_zone    = "DISCOUNT_ZONE"    in detected_types
    d_sma200_bounce    = "SMA200_BOUNCE"    in detected_types
    d_volume_momentum  = "VOLUME_MOMENTUM"  in detected_types

    if d_discount_zone:   score += 1.0
    if d_sma200_bounce:   score += 1.5
    if d_volume_momentum: score += 1.5

    # smc_analyzer (6 pts)
    s_htf_bull          = structure.get("bias") == "BULL"
    s_in_discount_ote   = dp.get("current_zone") in ("DISCOUNT", "OTE")
    s_fresh_ob          = _fresh_ob_nearby(obs, cp, threshold=0.05)   # OB : 5 %
    s_fvg               = _fvg_nearby(fvgs, cp, threshold=0.03)      # FVG : 3 %
    s_ssl_swept         = _ssl_swept_recently(ticker, ssl_levels, cp)
    s_confluences_strong = cf.get("count", 0) >= 4

    if s_htf_bull:           score += 1.0
    if s_in_discount_ote:    score += 1.0
    if s_fresh_ob:           score += 1.0
    if s_fvg:                score += 1.0
    if s_ssl_swept:          score += 1.0
    if s_confluences_strong: score += 1.0

    # options sentiment (+0.5 pt si BULLISH)
    options_data: dict = {}
    s_options_bullish = False
    try:
        from analysis.options_flow import get_options_sentiment
        options_data = get_options_sentiment(ticker)
        s_options_bullish = options_data.get("overall_direction") == "BULLISH"
    except Exception:
        pass

    if s_options_bullish:
        score += 0.5

    score = round(min(score, 10.0), 1)
    grade = _grade(score)

    breakdown = {
        "discount_zone":      d_discount_zone,
        "sma200_bounce":      d_sma200_bounce,
        "volume_momentum":    d_volume_momentum,
        "htf_bull":           s_htf_bull,
        "in_discount_or_ote": s_in_discount_ote,
        "fresh_ob_nearby":    s_fresh_ob,
        "fvg_nearby":         s_fvg,
        "ssl_swept":          s_ssl_swept,
        "confluences_strong": s_confluences_strong,
        "options_bullish":    s_options_bullish,
    }

    # ── 5. Entry / Stop / Target (priorité : setup SMC, sinon setup_detector) ─
    entry  = setup_smc.get("entry")
    stop   = setup_smc.get("stop")
    target = setup_smc.get("target")
    rr     = setup_smc.get("rr_ratio")

    if entry is None:
        try:
            from analysis.setup_detector import detect_setups
            det_setups = detect_setups([ticker])
            for s in det_setups:
                if s.get("ticker") == ticker and s.get("entry"):
                    entry  = s["entry"]
                    stop   = s.get("stop")
                    target = s.get("target")
                    risk   = (entry - stop) if (entry and stop) else 0
                    reward = (target - entry) if (target and entry) else 0
                    rr     = round(reward / risk, 2) if risk > 0 else None
                    break
        except Exception:
            pass

    # ── Enforce R:R minimum 2.5 ───────────────────────────────────────────────
    _MIN_RR = 2.5
    if entry is not None and stop is not None:
        _risk = entry - stop
        if _risk > 0:
            _min_target = entry + _MIN_RR * _risk
            if target is None or target < _min_target:
                target = round(_min_target, 2)
            _reward = target - entry
            rr = round(_reward / _risk, 2)

    if rr is not None and rr < _MIN_RR:
        grade  = "NO TRADE"
        entry  = None
        stop   = None
        target = None
        rr     = None

    # ── 6. Résumé smc_analysis allégé pour le dashboard ─────────────────────
    smc_summary = {
        "bias":       structure.get("bias"),
        "last_bos":   structure.get("last_bos"),
        "last_choch": structure.get("last_choch"),
        "obs":        obs,
        "fvgs":       fvgs,
        "liquidity":  liq,
        "zone":       dp.get("current_zone"),
        "confluences": cf,
    }

    reasoning = _build_reasoning(ticker, score, grade, breakdown, list(detected_types), cp)

    return {
        "ticker":                 ticker,
        "unified_score":          score,
        "grade":                  grade,
        "current_price":          round(cp, 2) if cp else None,
        "setup_detector_signals": list(detected_types),
        "smc_analysis":           smc_summary,
        "scoring_breakdown":      breakdown,
        "best_entry":             entry,
        "best_stop":              stop,
        "best_target":            target,
        "rr_ratio":               rr,
        "reasoning":              reasoning,
        "error":                  smc.get("error"),
        "options_data":           options_data,
    }


# ── Scan de la watchlist ──────────────────────────────────────────────────────

def scan_unified(top_n: int = 10) -> list[dict]:
    """
    Lance unified_analysis sur les `top_n` meilleurs tickers (par score DB).
    Retourne la liste triée par unified_score décroissant.
    """
    tickers = _top_tickers_from_db(top_n)
    results: list[dict] = []

    for ticker in tickers:
        try:
            result = unified_analysis(ticker)
            results.append(result)
        except Exception as e:
            results.append({
                "ticker":        ticker,
                "unified_score": 0.0,
                "grade":         "NO TRADE",
                "error":         str(e),
            })

    return sorted(results, key=lambda x: x.get("unified_score", 0.0), reverse=True)


# ── Test __main__ ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=== Unified Scorer — Test NVDA ===\n")
    r = unified_analysis("NVDA")
    print(f"Grade     : {r['grade']}")
    print(f"Score     : {r['unified_score']}/10")
    print(f"Signaux   : {r['setup_detector_signals']}")
    print(f"Entry     : {r['best_entry']}")
    print(f"Stop      : {r['best_stop']}")
    print(f"Target    : {r['best_target']}")
    print(f"R:R       : {r['rr_ratio']}")
    print(f"Reasoning : {r['reasoning']}")
    print("\nBreakdown :")
    for k, v in r["scoring_breakdown"].items():
        print(f"  {'✅' if v else '❌'} {k}")
