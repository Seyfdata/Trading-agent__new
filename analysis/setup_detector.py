"""
Setup Detector — Détection automatique de setups SMC sur la watchlist.

3 types de setups détectés :
  1. DISCOUNT_ZONE  — Prix dans la moitié basse du range 20j
  2. SMA200_BOUNCE  — Rebond sur SMA200 en structure haussière (SMA50 > SMA200)
  3. MOMENTUM       — Volume spike (×2) + hausse intraday > 1%

Usage :
  python -m analysis.setup_detector
"""

import math
import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

from config.loader import get_watchlist, get_trading_rules


# ── Paramètres chargés depuis config.yaml ─────────────────────────────────────

_RULES       = get_trading_rules()
RR_MINIMUM   = _RULES.get("rr_minimum",   2.5)
RISK_PCT_MAX = _RULES.get("risk_pct_max", 1.0)


def _get_capital() -> float:
    """Lit le capital depuis .env (CAPITAL=) ; défaut 10 000 $."""
    try:
        return float(os.getenv("CAPITAL", 10000))
    except (ValueError, TypeError):
        return 10000.0


# ── Détecteur 1 : DISCOUNT ZONE ───────────────────────────────────────────────

def _detect_discount_zone(hist, price: float) -> dict | None:
    """
    Prix dans la moitié basse du range des 20 derniers jours.

    discount_pct = (range_high - price) / (range_high - range_low) * 100
    Signal si discount_pct > 50 (prix sous le midpoint du range).
    """
    if len(hist) < 20:
        return None

    recent     = hist.tail(20)
    range_high = float(recent["High"].max())
    range_low  = float(recent["Low"].min())
    range_size = range_high - range_low

    if range_size <= 0:
        return None

    discount_pct = (range_high - price) / range_size * 100

    if discount_pct < 50:
        return None

    entry = price
    stop  = round(range_low * 0.995, 2)   # légèrement sous le range low
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + RR_MINIMUM * risk, 2)
    rr     = round((target - entry) / risk, 2)

    confidence = "HIGH" if discount_pct >= 80 else "MEDIUM" if discount_pct >= 65 else "LOW"

    reasons = [
        f"Prix à {discount_pct:.0f}% de discount dans le range 20j",
        f"Range : ${range_low:.2f} – ${range_high:.2f} (taille ${range_size:.2f})",
    ]
    # Confirmation volume
    last_vol = float(hist["Volume"].iloc[-1])
    avg_vol  = float(hist["Volume"].tail(10).mean())
    if avg_vol > 0 and last_vol > avg_vol * 1.2:
        reasons.append(f"Volume au-dessus de la moyenne (×{last_vol / avg_vol:.1f})")

    return {
        "setup_type":   "DISCOUNT_ZONE",
        "entry":        round(entry, 2),
        "stop":         stop,
        "target":       target,
        "rr_ratio":     rr,
        "discount_pct": round(discount_pct, 1),
        "confidence":   confidence,
        "reasons":      reasons,
    }


# ── Détecteur 2 : SMA200 BOUNCE ───────────────────────────────────────────────

def _detect_sma200_bounce(hist, price: float) -> dict | None:
    """
    Rebond potentiel sur la SMA200 en structure haussière.

    Conditions :
      - Prix entre -1% et +3% de la SMA200
      - SMA50 > SMA200 (uptrend confirmé)
    """
    if len(hist) < 200:
        return None

    closes = hist["Close"]
    sma200 = float(closes.rolling(200).mean().iloc[-1])
    sma50  = float(closes.rolling(50).mean().iloc[-1])

    if sma200 <= 0:
        return None

    dist_pct = (price - sma200) / sma200 * 100

    if not (-1.0 <= dist_pct <= 3.0):
        return None

    uptrend = sma50 > sma200

    entry = price
    stop  = round(sma200 * 0.99, 2)   # 1% sous la SMA200
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + RR_MINIMUM * risk, 2)
    rr     = round((target - entry) / risk, 2)

    confidence = "HIGH" if uptrend and dist_pct >= 0 else "MEDIUM"

    reasons = [
        f"Prix à {dist_pct:+.1f}% de la SMA200 (${sma200:.2f})",
        "Test du support dynamique majeur (SMA200)",
    ]
    if uptrend:
        reasons.append(f"Structure haussiere : SMA50 (${sma50:.2f}) > SMA200 (${sma200:.2f})")
    else:
        reasons.append(f"Attention : SMA50 (${sma50:.2f}) < SMA200 — structure mixte")

    return {
        "setup_type":   "SMA200_BOUNCE",
        "entry":        round(entry, 2),
        "stop":         stop,
        "target":       target,
        "rr_ratio":     rr,
        "discount_pct": round(max(0.0, 100.0 - abs(dist_pct) * 20), 1),
        "confidence":   confidence,
        "reasons":      reasons,
    }


# ── Détecteur 3 : MOMENTUM ────────────────────────────────────────────────────

def _detect_momentum(hist, price: float) -> dict | None:
    """
    Volume spike institutionnel + pression acheteuse.

    Conditions :
      - Volume du jour > 2× la moyenne 20j
      - Variation intraday > +1% vs close précédent
    """
    if len(hist) < 21:
        return None

    avg_vol_20 = float(hist["Volume"].tail(20).mean())
    vol_today  = float(hist["Volume"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2])

    if avg_vol_20 <= 0 or prev_close <= 0:
        return None

    vol_ratio = vol_today / avg_vol_20
    chg_pct   = (price - prev_close) / prev_close * 100

    if vol_ratio < 2.0 or chg_pct < 1.0:
        return None

    # Stop sous le bas de la bougie du jour
    day_low = float(hist["Low"].iloc[-1])
    entry   = price
    stop    = round(min(day_low * 0.998, price * 0.98), 2)
    risk    = entry - stop
    if risk <= 0:
        return None

    target = round(entry + RR_MINIMUM * risk, 2)
    rr     = round((target - entry) / risk, 2)

    confidence = "HIGH" if vol_ratio >= 3.0 and chg_pct >= 2.0 else "MEDIUM"

    reasons = [
        f"Volume ×{vol_ratio:.1f} la moyenne 20j — activite institutionnelle",
        f"Momentum intraday : {chg_pct:+.1f}% vs close precedent",
        f"Stop sous le bas du jour (${day_low:.2f})",
    ]

    return {
        "setup_type":   "MOMENTUM",
        "entry":        round(entry, 2),
        "stop":         stop,
        "target":       target,
        "rr_ratio":     rr,
        "discount_pct": 0.0,
        "confidence":   confidence,
        "reasons":      reasons,
    }


# ── Fonction principale ───────────────────────────────────────────────────────

def detect_setups(tickers: list | None = None) -> list[dict]:
    """
    Scanne les tickers et retourne les setups détectés, triés par confidence.

    Paramètres
    ----------
    tickers : liste de tickers à scanner. None = watchlist complète (config.yaml).

    Retourne
    --------
    Liste de dicts :
    {ticker, price, setup_type, entry, stop, target, rr_ratio,
     discount_pct, confidence, reasons, detected_at}
    """
    if not YF_AVAILABLE:
        print("[WARN] yfinance non installee — pip install yfinance")
        return []

    if tickers is None:
        tickers = get_watchlist()

    setups = []

    for ticker in tickers:
        try:
            tk   = yf.Ticker(ticker)
            hist = tk.history(period="1y", interval="1d", auto_adjust=True)

            if hist.empty or len(hist) < 2:
                continue

            price = float(hist["Close"].iloc[-1])

            for detector in (_detect_discount_zone, _detect_sma200_bounce, _detect_momentum):
                result = detector(hist, price)
                if result is not None:
                    setups.append({
                        "ticker":      ticker,
                        "price":       round(price, 2),
                        "detected_at": datetime.now().strftime("%H:%M:%S"),
                        **result,
                    })

        except Exception as e:
            print(f"[WARN] {ticker} : {e}")
            continue

    # HIGH → MEDIUM → LOW, puis R:R décroissant
    _order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    setups.sort(key=lambda s: (_order.get(s["confidence"], 2), -s["rr_ratio"]))
    return setups


# ── Position sizing ───────────────────────────────────────────────────────────

def calculate_position_size(
    entry: float,
    stop: float,
    capital: float | None = None,
    risk_pct: float = RISK_PCT_MAX,
) -> dict:
    """
    Calcule la taille de position en fonction du risque.

    Paramètres
    ----------
    entry    : prix d'entrée
    stop     : prix du stop-loss
    capital  : capital total en $ (None → lit CAPITAL depuis .env)
    risk_pct : % du capital à risquer par trade (défaut = risk_pct_max de config.yaml)

    Retourne
    --------
    {shares, risk_dollars, position_value, risk_pct_actual, risk_per_share}
    """
    if capital is None:
        capital = _get_capital()

    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return {"error": "stop >= entry — setup invalide"}

    risk_dollars    = capital * risk_pct / 100
    shares          = math.floor(risk_dollars / risk_per_share)
    position_value  = round(shares * entry, 2)
    actual_risk     = round(shares * risk_per_share, 2)
    actual_risk_pct = round(actual_risk / capital * 100, 3) if capital > 0 else 0.0

    return {
        "shares":          shares,
        "risk_dollars":    round(risk_dollars, 2),
        "position_value":  position_value,
        "risk_pct_actual": actual_risk_pct,
        "risk_per_share":  round(risk_per_share, 2),
    }


# ── Formatage pour le dashboard ───────────────────────────────────────────────

def format_setup_alert(setup: dict, position: dict) -> str:
    """
    Formate un setup en texte lisible pour les logs ou le dashboard.

    Retourne une chaîne multi-lignes.
    """
    _conf_icon = {"HIGH": "[FIRE]", "MEDIUM": "[BOLT]", "LOW": "[WARN]"}
    _type_icon = {
        "DISCOUNT_ZONE": "[DISC]",
        "SMA200_BOUNCE": "[SMA]",
        "MOMENTUM":      "[MOM]",
    }
    conf = setup.get("confidence", "?")
    stype = setup.get("setup_type", "?")

    entry  = setup.get("entry",  0)
    stop   = setup.get("stop",   0)
    target = setup.get("target", 0)

    lines = [
        f"{_conf_icon.get(conf, '')} {_type_icon.get(stype, '')} "
        f"{setup.get('ticker', '?')} | {stype} [{conf}] | R:R {setup.get('rr_ratio', 0):.1f}x",
        f"  Entry  ${entry:.2f}  Stop ${stop:.2f} (-${entry - stop:.2f})"
        f"  Target ${target:.2f} (+${target - entry:.2f})",
    ]

    if not position.get("error"):
        lines.append(
            f"  Size   {position.get('shares', 0)} actions"
            f" | ${position.get('position_value', 0):,.0f} position"
            f" | Risque ${position.get('risk_dollars', 0):.0f}"
            f" ({position.get('risk_pct_actual', 0):.2f}%)"
        )

    for reason in setup.get("reasons", []):
        lines.append(f"  • {reason}")

    return "\n".join(lines)


# ── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Setup Detector — Test ===\n")

    TEST_TICKERS = ["NVDA", "AAPL", "TSLA", "AMD"]
    capital = _get_capital()
    print(f"Capital : ${capital:,.0f}  |  Risque max : {RISK_PCT_MAX}%  |  R:R minimum : {RR_MINIMUM}x\n")

    setups = detect_setups(TEST_TICKERS)

    if not setups:
        print("Aucun setup detecte sur les tickers de test.")
    else:
        print(f"{len(setups)} setup(s) detecte(s) :\n")
        for s in setups:
            pos = calculate_position_size(s["entry"], s["stop"], capital)
            print(format_setup_alert(s, pos))
            print()

    print("[OK] setup_detector.py fonctionne correctement.")
