"""
Unified Scorer â€” Croise setup_detector et smc_analyzer pour un score de conviction unifiÃ©.

Score sur 10 points :
  setup_detector (4 pts) :
    DISCOUNT_ZONE    â†’ +1.0
    SMA200_BOUNCE    â†’ +1.5  (signal technique fort)
    VOLUME_MOMENTUM  â†’ +1.5  (institutions actives)

  smc_analyzer (6 pts) :
    Biais HTF BULL            â†’ +1
    Prix en DISCOUNT ou OTE   â†’ +1
    Bull OB non mitigÃ© <5 %   â†’ +1
    FVG haussier non comblÃ©   â†’ +1
    SSL balayÃ© rÃ©cemment      â†’ +1
    Score confluences SMC â‰¥ 4 â†’ +1

Grades :
    8â€“10  â†’ A+  (toutes les Ã©toiles alignÃ©es)
    6â€“7   â†’ A   (setup solide)
    4â€“5   â†’ B   (setup correct)
    2â€“3   â†’ C   (setup faible)
    0â€“1   â†’ NO TRADE

Usage :
    from analysis.unified_scorer import unified_analysis, scan_unified
    result = unified_analysis("NVDA")
    top5   = scan_unified(top_n=5)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import WATCHLIST

# â”€â”€ Mode (doit correspondre Ã  smc_analyzer) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DEMO_MODE = True


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    Bull OB actif (non mitigÃ© ou partiellement mitigÃ©) Ã  moins de `threshold*100`% du prix.
    Utilise distance_pct si disponible (calculÃ© par smc_analyzer v2), sinon fallback.
    """
    if current_price <= 0:
        return False
    for ob in obs:
        if ob.get("type") != "BULL":
            continue
        # OB actif = non mitigÃ© OU partiellement mitigÃ©
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
    FVG haussier actif (non comblÃ© ou partiellement comblÃ©) Ã  moins de `threshold*100`% du prix.
    Seuil rÃ©duit Ã  3% (vs 5% pour OB) â€” FVG moins large, doit Ãªtre plus prÃ©cis.
    """
    if current_price <= 0:
        return False
    for fvg in fvgs:
        if fvg.get("type") != "BULL":
            continue
        # FVG actif = non comblÃ© OU partiellement comblÃ©
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
    Retourne True si le prix est rÃ©cemment passÃ© sous un niveau SSL puis est remontÃ©.
    Signe d'une chasse aux stops â€” pattern "sweep & reverse" SMC.
    """
    if not ssl_levels or current_price <= 0:
        return False
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period="1mo", interval="1d")
        if df is None or len(df) < 5:
            return False
        past_lows   = df["Low"].values[-lookback:-1]   # lows prÃ©cÃ©dents (hors dernier)
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
    """Construit un texte explicatif synthÃ©tique."""
    positives = []
    negatives = []

    if breakdown["sma200_bounce"]:
        positives.append("SMA200 Bounce confirmÃ©")
    if breakdown["volume_momentum"]:
        positives.append("momentum institutionnel (volume Ã—2+)")
    if breakdown["discount_zone"]:
        positives.append("Discount Zone dÃ©tectÃ©e")
    if breakdown["htf_bull"]:
        positives.append("biais HTF haussier")
    if breakdown["in_discount_or_ote"]:
        positives.append("prix en zone OTE/Discount")
    if breakdown["fresh_ob_nearby"]:
        positives.append("Bull OB non mitigÃ© proche")
    if breakdown["fvg_nearby"]:
        positives.append("FVG haussier actif")
    if breakdown["ssl_swept"]:
        positives.append("SSL rÃ©cemment balayÃ© (liquiditÃ© prise)")
    if breakdown["confluences_strong"]:
        positives.append("confluences SMC solides (â‰¥4)")
    if breakdown.get("options_bullish"):
        positives.append("options flow BULLISH")

    if not breakdown["htf_bull"]:
        negatives.append("biais HTF non haussier")
    if not breakdown["fresh_ob_nearby"]:
        negatives.append("pas de Bull OB frais proche")
    if not breakdown["fvg_nearby"]:
        negatives.append("pas de FVG haussier proche")

    text = f"{ticker} @ ${current_price:.2f} â€” "
    if positives:
        text += ", ".join(positives)
    if negatives:
        text += " | âš ï¸ " + ", ".join(negatives)
    text += f". Score {score:.1f}/10 â€” Grade {grade}."
    return text



def _is_ny_killzone() -> bool:
    """True si heure CET actuelle est dans NY Killzone (14:30-16:30)."""
    from datetime import datetime
    try:
        import pytz
        now = datetime.now(pytz.timezone("Europe/Paris"))
    except ImportError:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo("Europe/Paris"))
    h, m = now.hour, now.minute
    return (h == 14 and m >= 30) or h == 15 or (h == 16 and m <= 30)


def _price_in_active_fvg(fvgs: list, current_price: float) -> bool:
    """True si le prix est dans un FVG Bull actif (non comble)."""
    for fvg in fvgs:
        if fvg.get("type") != "BULL":
            continue
        if fvg.get("filled") and not fvg.get("partially_filled"):
            continue
        if fvg.get("low", 0) <= current_price <= fvg.get("high", 0):
            return True
    return False


def _check_macro_risk() -> dict:
    """
    Verifie si un evenement macro HIGH impact arrive dans les 2h.
    Retourne {"risk": HIGH/MEDIUM/LOW, "penalty": 0.0-0.8}
    """
    try:
        from datetime import datetime, timezone
        from scrapers.macro_calendar import get_macro_events
        events = get_macro_events() or []
        now = datetime.now(timezone.utc)
        for ev in events:
            dt_str = ev.get("datetime") or ev.get("date") or ""
            impact = (ev.get("impact") or ev.get("importance") or "").upper()
            if not dt_str or impact not in ("HIGH", "3"):
                continue
            try:
                ev_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                diff_h = (ev_dt - now).total_seconds() / 3600
                if 0 <= diff_h <= 2:
                    return {"risk": "HIGH", "penalty": 0.8, "event": ev.get("title", "?")}
            except Exception:
                pass
    except Exception:
        pass
    return {"risk": "LOW", "penalty": 0.0, "event": None}

# â”€â”€ Analyse unifiÃ©e â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def unified_analysis(ticker: str) -> dict:
    """
    Combine setup_detector et smc_analyzer en un score de conviction unifiÃ© (0â€“10).

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

    # â”€â”€ 1. Setup detector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    detected_types: set[str] = set()
    try:
        from analysis.setup_detector import detect_setups
        setups_all = detect_setups([ticker])
        detected_types = {s["setup_type"] for s in setups_all if s.get("ticker") == ticker}
        base["setup_detector_signals"] = list(detected_types)
    except Exception as e:
        base["setup_detector_signals"] = []

    # â”€â”€ 2. SMC analyzer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ 3. Extraire les donnÃ©es SMC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    structure = smc.get("structure", {})
    dp        = smc.get("discount_premium", {})
    obs       = smc.get("order_blocks", [])
    fvgs      = smc.get("fvg", [])
    liq       = smc.get("liquidity", {})
    cf        = smc.get("confluences", {})
    setup_smc = smc.get("setup", {})
    cp        = smc.get("current_price") or 0.0

    ssl_levels  = liq.get("ssl_levels", [])
    sweeps      = smc.get("sweeps", [])
    valid_choch = smc.get("valid_choch", False)
    asian_range = smc.get("asian_range", {})

    # ── 4. Score Technique (0-10) ─────────────────────────────────────────
    tech = 0.0

    # setup_detector (4 pts)
    d_discount_zone    = "DISCOUNT_ZONE"    in detected_types
    d_sma200_bounce    = "SMA200_BOUNCE"    in detected_types
    d_volume_momentum  = "VOLUME_MOMENTUM"  in detected_types

    if d_discount_zone:   tech += 1.0
    if d_sma200_bounce:   tech += 1.5
    if d_volume_momentum: tech += 1.5

    # smc_analyzer (6 pts)
    s_htf_bull           = structure.get("bias") == "BULL"
    s_in_discount_ote    = dp.get("current_zone") in ("DISCOUNT", "OTE")
    s_fresh_ob           = _fresh_ob_nearby(obs, cp, threshold=0.05)
    s_fvg                = _fvg_nearby(fvgs, cp, threshold=0.03)
    s_ssl_swept          = _ssl_swept_recently(ticker, ssl_levels, cp)
    s_confluences_strong = cf.get("count", 0) >= 4

    if s_htf_bull:           tech += 1.0
    if s_in_discount_ote:    tech += 1.0
    if s_fresh_ob:           tech += 1.0
    if s_fvg:                tech += 1.0
    if s_ssl_swept:          tech += 1.0
    if s_confluences_strong: tech += 1.0

    # options sentiment (+0.5)
    options_data: dict = {}
    s_options_bullish = False
    try:
        from analysis.options_flow import get_options_sentiment
        options_data = get_options_sentiment(ticker)
        s_options_bullish = options_data.get("overall_direction") == "BULLISH"
    except Exception:
        pass
    if s_options_bullish:
        tech += 0.5

    tech = min(tech, 10.0)

    # ── 5. Score Contextuel (0-10) ────────────────────────────────────────
    ctx = 0.0
    sweep_detected = len(sweeps) > 0
    price_in_fvg   = _price_in_active_fvg(fvgs, cp)
    in_premium     = dp.get("current_zone") == "PREMIUM"

    if sweep_detected: ctx += 2.0   # Asian sweep confirme
    if valid_choch:    ctx += 2.0   # CHoCH valide apres sweep
    if price_in_fvg:   ctx += 2.0   # Prix dans FVG actif
    if s_in_discount_ote: ctx += 2.0

    macro_info = _check_macro_risk()
    if macro_info["risk"] == "LOW":
        ctx += 2.0

    ctx = min(ctx, 10.0)

    # ── 6. Bonus / Malus ─────────────────────────────────────────────────
    # Bonus confluences SMC: sweep + valid CHoCH + prix dans FVG
    if sweep_detected and valid_choch and price_in_fvg:
        print(f"[SMC-Logic] BONUS CONFLUENCE triple {ticker} : sweep+CHoCH+FVG")
        tech = min(tech + 3.0, 10.0)

    # Malus Premium : LONG en zone Premium = dangereux
    if in_premium:
        tech = max(tech - 5.0, 0.0)

    # ── 7. Formule finale avec multiplicateur Killzone ────────────────────
    killzone_active = _is_ny_killzone()
    killzone_mult   = 1.5 if killzone_active else 1.0
    score = (tech * 0.6 + ctx * 0.4) * killzone_mult

    # Gate macro : penalite si evenement haute impact dans 2h
    if macro_info["penalty"] > 0:
        score = score * (1.0 - macro_info["penalty"])
        print(f"[SMC-Logic] MACRO GATE {ticker}: penalite {macro_info['penalty']*100:.0f}% — {macro_info.get('event')}")

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
        "sweep_detected":     sweep_detected,
        "valid_choch":        valid_choch,
        "price_in_fvg":       price_in_fvg,
        "in_premium":         in_premium,
        "killzone_active":    killzone_active,
        "macro_risk":         macro_info["risk"],
        "tech_score":         round(tech, 2),
        "ctx_score":          round(ctx, 2),
        "killzone_mult":      killzone_mult,
    }

    # â”€â”€ 5. Entry / Stop / Target (prioritÃ© : setup SMC, sinon setup_detector) â”€
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

    # â”€â”€ Enforce R:R minimum 2.5 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _MIN_RR        = 2.5
    rr_valid       = True
    rr_adjusted    = setup_smc.get("target_adjusted", False)

    if entry is not None and stop is not None:
        _risk = entry - stop
        if _risk > 0:
            _min_target = entry + _MIN_RR * _risk
            if target is None or target < _min_target:
                target     = round(_min_target, 2)
                rr_adjusted = True
            _reward = target - entry
            rr = round(_reward / _risk, 2)

    if rr is not None and rr < _MIN_RR:
        rr_valid = False
        grade    = "NO TRADE"
        score    = min(score, 3.0)  # score plafonnÃ© Ã  3/10 si R:R invalide
        entry    = None
        stop     = None
        target   = None
        rr       = None

    # â”€â”€ 6. RÃ©sumÃ© smc_analysis allÃ©gÃ© pour le dashboard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        "rr_valid":               rr_valid,
        "rr_adjusted":            rr_adjusted,
        "rr_rule":                "min_2.5",
        "reasoning":              reasoning,
        "error":                  smc.get("error"),
        "options_data":           options_data,
        "killzone_active":         killzone_active,
        "asian_range":             asian_range,
        "sweeps":                  sweeps,
        "valid_choch":             valid_choch,
    }


# â”€â”€ Scan de la watchlist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def scan_unified(top_n: int = 10) -> list[dict]:
    """
    Lance unified_analysis sur les `top_n` meilleurs tickers (par score DB).
    Retourne la liste triÃ©e par unified_score dÃ©croissant.
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


# â”€â”€ Test __main__ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    import json

    print("=== Unified Scorer â€” Test NVDA ===\n")
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
        print(f"  {'âœ…' if v else 'âŒ'} {k}")
