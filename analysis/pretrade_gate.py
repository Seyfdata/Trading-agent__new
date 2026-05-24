"""
Gate pre-trade — verdict GO/NO-GO unique avant d'engager une position.

Agregge en un seul appel :
  1. RISK       — risk_engine.validate_and_size()
  2. REGIME     — regime marche live (BULL/NEUTRAL/BEAR)
  3. KILLZONE   — 14h30-16h30 CET (depuis config.settings)
  4. NEWS_DAY   — FOMC/NFP/CPI detectes par scrapers.macro_calendar
  5. MAX_TRADES — limite journaliere depuis la base de trades

Verdict global :
  GO       : tous les checks sont PASS
  GO-WARN  : aucun FAIL, au moins un WARN
  NO-GO    : au moins un FAIL
"""

import sqlite3
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from config.settings import (
    KILLZONE_START_HOUR,
    KILLZONE_START_MIN,
    KILLZONE_END_HOUR,
    KILLZONE_END_MIN,
    TZ_MARKET,
    MAX_TRADES_PER_DAY,
)
from analysis.risk_engine import validate_and_size
from analysis.technical_indicators import clean_for_json
from database.models import DB_PATH

_CET = ZoneInfo(TZ_MARKET)


# ======================================================================
# Helpers internes
# ======================================================================

def _get_regime() -> str:
    """Retourne BULL/NEUTRAL/BEAR depuis le marche live. Fallback UNKNOWN."""
    try:
        from scrapers.market_data import get_market_context
        from analysis.scoring import score_market_context
        raw = get_market_context()
        if not raw:
            return "UNKNOWN"
        # Adapter: meme logique que dashboard/routers/market.py::_extract_scoring_ctx
        ctx: dict = {}
        vix = raw.get("^VIX")
        spy = raw.get("SPY")
        dxy = raw.get("DX-Y.NYB")
        tny = raw.get("^TNX")
        if vix and "price" in vix:
            ctx["vix"] = vix["price"]
        if spy and "change_pct" in spy:
            ctx["spy_change"] = spy["change_pct"]
        if dxy and "price" in dxy:
            ctx["dxy"] = dxy["price"]
        if tny and "price" in tny:
            ctx["us10y"] = tny["price"]
        scored = score_market_context(ctx)
        return scored.get("regime", "UNKNOWN")
    except Exception as e:
        print(f"[PretradeGate] Erreur regime: {e}")
        return "UNKNOWN"


def _count_trades_today(date_str: str) -> int:
    """Compte les trades ouverts aujourd'hui (toute heure) dans la DB."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE date_open LIKE ?",
                (f"{date_str}%",),
            ).fetchone()
            return row[0] if row else 0
    except Exception as e:
        print(f"[PretradeGate] Erreur DB count trades: {e}")
        return 0


def _build_today_info(now_cet: datetime) -> dict:
    """Construit le dict attendu par detect_recurring_events a partir d'un datetime."""
    return {
        "date": now_cet.strftime("%d/%m/%Y"),
        "day_name": now_cet.strftime("%A"),
        "day_of_week": now_cet.weekday(),
        "day_of_month": now_cet.day,
        "week_of_month": (now_cet.day - 1) // 7 + 1,
        "month": now_cet.month,
        "is_first_friday": now_cet.weekday() == 4 and now_cet.day <= 7,
        "is_first_business_day": now_cet.weekday() == 0 and now_cet.day <= 3,
    }


# ======================================================================
# Fonction principale
# ======================================================================

def evaluate_trade(
    capital: float,
    risk_pct: float,
    entry: float,
    stop: float,
    target: float,
    now: Optional[datetime] = None,
    open_risk_amount: float = 0.0,
    open_notional: float = 0.0,
    trades_today: Optional[int] = None,
) -> dict:
    """Gate pre-trade : agrege risk, regime, killzone, news et max trades.

    Args:
        capital: Capital total (USD).
        risk_pct: Risque souhaite en % du capital (ex. 1.0 pour 1 %).
        entry: Prix d'entree.
        stop: Stop-loss (< entry).
        target: Cible de profit (> entry).
        now: Datetime CET de reference (defaut = maintenant en heure locale Paris).
            Naive datetime traite comme CET. Timezone-aware converti en CET.
        open_risk_amount: Dollars deja a risque sur positions ouvertes.
        open_notional: Notionnel total des positions ouvertes (USD).
        trades_today: Override manuel du comptage de trades du jour.
            Si None, comptage automatique depuis la DB (trades ouverts ce jour).

    Returns:
        {
            verdict : "GO" | "GO-WARN" | "NO-GO",
            checks  : [
                {"nom": str, "statut": "PASS"|"FAIL"|"WARN", "detail": str},
                ...
            ],
            sizing  : dict,  # sortie complete de validate_and_size
        }
    """
    # --- Resolution du now en CET ---
    if now is None:
        now_cet = datetime.now(tz=_CET)
    elif now.tzinfo is None:
        now_cet = now.replace(tzinfo=_CET)
    else:
        now_cet = now.astimezone(_CET)

    date_str = now_cet.strftime("%Y-%m-%d")
    time_str = now_cet.strftime("%H:%M")
    print(f"[PretradeGate] evaluate_trade: {date_str} {time_str} CET | "
          f"capital={capital} risk_pct={risk_pct}% entry={entry} stop={stop} target={target}")

    checks: list[dict] = []

    # ==================================================================
    # CHECK 1 — RISK (risk_engine autoritaire)
    # La verification MAX_TRADES est geree par le check 5 ci-dessous ;
    # on passe trades_today=0 pour ne pas compter deux fois.
    # ==================================================================
    sizing = validate_and_size(
        capital=capital,
        risk_pct=risk_pct,
        entry=entry,
        stop=stop,
        target=target,
        open_risk_amount=open_risk_amount,
        open_notional=open_notional,
        trades_today=0,
    )
    if sizing["verdict"] == "GO":
        checks.append({
            "nom": "RISK",
            "statut": "PASS",
            "detail": (f"R:R={sizing['rr']:.2f} | "
                       f"shares={sizing['shares']} | "
                       f"heat={sizing['risk_exposure_pct']:.1f}% | "
                       f"deployed={sizing['deployed_pct']:.1f}%"),
        })
    else:
        checks.append({
            "nom": "RISK",
            "statut": "FAIL",
            "detail": "; ".join(sizing["violations"]),
        })

    # ==================================================================
    # CHECK 2 — REGIME (marche live)
    # PASS si BULL, FAIL si BEAR (LONG only), WARN si NEUTRAL/UNKNOWN
    # ==================================================================
    regime = _get_regime()
    if regime == "BULL":
        checks.append({"nom": "REGIME", "statut": "PASS",
                        "detail": f"Regime={regime}"})
    elif regime == "BEAR":
        checks.append({"nom": "REGIME", "statut": "FAIL",
                        "detail": f"Regime={regime} — LONG interdit en regime BEAR"})
    else:
        checks.append({"nom": "REGIME", "statut": "WARN",
                        "detail": f"Regime={regime} — confirmer avant d'entrer"})

    # ==================================================================
    # CHECK 3 — KILLZONE (14h30-16h30 CET)
    # ==================================================================
    kz_start = now_cet.replace(
        hour=KILLZONE_START_HOUR, minute=KILLZONE_START_MIN, second=0, microsecond=0,
    )
    kz_end = now_cet.replace(
        hour=KILLZONE_END_HOUR, minute=KILLZONE_END_MIN, second=0, microsecond=0,
    )
    kz_label = (f"{KILLZONE_START_HOUR:02d}:{KILLZONE_START_MIN:02d}"
                f"-{KILLZONE_END_HOUR:02d}:{KILLZONE_END_MIN:02d}")
    if kz_start <= now_cet <= kz_end:
        checks.append({"nom": "KILLZONE", "statut": "PASS",
                        "detail": f"{time_str} CET dans la fenetre [{kz_label}]"})
    else:
        checks.append({"nom": "KILLZONE", "statut": "FAIL",
                        "detail": f"{time_str} CET hors killzone [{kz_label}]"})

    # ==================================================================
    # CHECK 4 — NEWS_DAY (macro calendar : FOMC/NFP/CPI)
    # FAIL si evenement FORT detecte, PASS sinon.
    # ==================================================================
    try:
        from scrapers.macro_calendar import detect_recurring_events, check_earnings_today
        today_info = _build_today_info(now_cet)
        events = detect_recurring_events(today_info)
        high_impact = [e for e in events if e.get("impact") == "FORT"]
        earnings = check_earnings_today()
        if high_impact or earnings:
            names = [e["name"] for e in high_impact] + [f"Earnings {t}" for t in earnings]
            checks.append({"nom": "NEWS_DAY", "statut": "FAIL",
                            "detail": f"Evenements FORT: {', '.join(names)}"})
        else:
            checks.append({"nom": "NEWS_DAY", "statut": "PASS",
                            "detail": "Aucun evenement macro majeur detecte"})
    except Exception as e:
        checks.append({"nom": "NEWS_DAY", "statut": "WARN",
                        "detail": f"Calendrier macro indisponible: {e}"})

    # ==================================================================
    # CHECK 5 — MAX_TRADES (limite journaliere)
    # ==================================================================
    trades_today_count = (
        _count_trades_today(date_str) if trades_today is None else trades_today
    )
    if trades_today_count >= MAX_TRADES_PER_DAY:
        checks.append({"nom": "MAX_TRADES", "statut": "FAIL",
                        "detail": f"{trades_today_count}/{MAX_TRADES_PER_DAY} trades executes aujourd'hui"})
    else:
        checks.append({"nom": "MAX_TRADES", "statut": "PASS",
                        "detail": f"{trades_today_count}/{MAX_TRADES_PER_DAY} trades executes aujourd'hui"})

    # ==================================================================
    # Verdict global
    # ==================================================================
    has_fail = any(c["statut"] == "FAIL" for c in checks)
    has_warn = any(c["statut"] == "WARN" for c in checks)

    if has_fail:
        verdict = "NO-GO"
    elif has_warn:
        verdict = "GO-WARN"
    else:
        verdict = "GO"

    print(f"[PretradeGate] => {verdict} | "
          + " | ".join(f"{c['nom']}={c['statut']}" for c in checks))

    return clean_for_json({
        "verdict": verdict,
        "checks": checks,
        "sizing": sizing,
    })
