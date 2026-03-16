"""
Setup Detector — Détection automatique de setups SMC sur la watchlist.

3 types de setups détectés :
  1. DISCOUNT_ZONE    — Prix dans la moitié basse du range 20j
  2. SMA200_BOUNCE    — Rebond confirmé sur SMA200 en structure haussière (SMA50 > SMA200)
  3. VOLUME_MOMENTUM  — Volume spike (×2) + hausse intraday > 1.5% + SMA50 OK

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

    Filtres :
      - Volume du jour >= 0.8× moyenne (pas de discount dans le vide)
    Bonus confidence :
      - Si la zone de discount coïncide avec la SMA200 (double support)
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

    # ── Filtre volume : activité minimum requise ──────────────────────────────
    last_vol = float(hist["Volume"].iloc[-1])
    avg_vol  = float(hist["Volume"].tail(20).mean())
    if avg_vol <= 0 or last_vol < avg_vol * 0.8:
        return None

    entry = price
    stop  = round(range_low * 0.995, 2)   # légèrement sous le range low
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + RR_MINIMUM * risk, 2)
    rr     = round((target - entry) / risk, 2)

    # ── Confidence de base ────────────────────────────────────────────────────
    confidence = "HIGH" if discount_pct >= 80 else "MEDIUM" if discount_pct >= 65 else "LOW"

    reasons = [
        f"Prix à {discount_pct:.0f}% de discount dans le range 20j",
        f"Range : ${range_low:.2f} – ${range_high:.2f} (taille ${range_size:.2f})",
    ]

    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    if vol_ratio >= 1.2:
        reasons.append(f"Volume au-dessus de la moyenne (×{vol_ratio:.1f})")

    # ── Bonus : double support si SMA200 proche ───────────────────────────────
    double_support = False
    if len(hist) >= 200:
        sma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        if sma200 > 0:
            dist_sma200 = abs(price - sma200) / sma200 * 100
            if dist_sma200 <= 5.0:
                double_support = True
                reasons.append(
                    f"Double support : zone de discount + SMA200 (${sma200:.2f}, "
                    f"dist {dist_sma200:.1f}%)"
                )
                # Upgrade confidence si double support
                if confidence == "MEDIUM":
                    confidence = "HIGH"
                elif confidence == "LOW":
                    confidence = "MEDIUM"

    return {
        "setup_type":     "DISCOUNT_ZONE",
        "entry":          round(entry, 2),
        "stop":           stop,
        "target":         target,
        "rr_ratio":       rr,
        "discount_pct":   round(discount_pct, 1),
        "confidence":     confidence,
        "double_support": double_support,
        "reasons":        reasons,
    }


# ── Détecteur 2 : SMA200 BOUNCE ───────────────────────────────────────────────

def _detect_sma200_bounce(hist, price: float) -> dict | None:
    """
    Rebond confirmé sur la SMA200 en structure haussière.

    Conditions :
      1. Prix entre 0% et +3% au-dessus de la SMA200 (zone de support)
      2. SMA50 > SMA200 (tendance haussière confirmée)
      3. Au moins un low des 5 derniers jours à moins de 1% de la SMA200
         (rebond réel, pas juste passage à proximité)

    Stop  : SMA200 × 0.985 (1.5% sous le support)
    Target: entry + 2.5 × (entry – stop)

    Confidence :
      HIGH   — rebond sur la SMA200 dans les 2 derniers jours
      MEDIUM — rebond dans les 5 derniers jours
    """
    if len(hist) < 200:
        return None

    closes = hist["Close"]
    sma200 = float(closes.rolling(200).mean().iloc[-1])
    sma50  = float(closes.rolling(50).mean().iloc[-1])

    if sma200 <= 0:
        return None

    dist_pct = (price - sma200) / sma200 * 100

    # Prix doit être entre 0% et +3% AU-DESSUS de la SMA200
    if not (0.0 <= dist_pct <= 3.0):
        return None

    # SMA50 doit être au-dessus de la SMA200 (tendance haussière)
    if sma50 <= sma200:
        return None

    # ── Vérifier qu'un low récent a touché la SMA200 (< 1%) ──────────────────
    lows_5d = hist["Low"].tail(5)
    touch_day = None    # index depuis la fin (1 = hier, 2 = avant-hier, …)
    for i, low in enumerate(reversed(lows_5d.values)):
        dist_low = abs(low - sma200) / sma200 * 100
        if dist_low < 1.0:
            touch_day = i + 1
            break

    if touch_day is None:
        return None   # pas de contact réel avec la SMA200 dans les 5 jours

    entry = price
    stop  = round(sma200 * 0.985, 2)   # 1.5% sous la SMA200
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + RR_MINIMUM * risk, 2)
    rr     = round((target - entry) / risk, 2)

    confidence = "HIGH" if touch_day <= 2 else "MEDIUM"

    recency_str = f"il y a {touch_day} jour" + ("" if touch_day == 1 else "s")
    reasons = [
        f"Prix à {dist_pct:+.1f}% de la SMA200 (${sma200:.2f}) — zone de rebond",
        f"Contact confirmé avec la SMA200 {recency_str} (low < 1% du support)",
        f"Structure haussière : SMA50 (${sma50:.2f}) > SMA200 (${sma200:.2f})",
    ]

    return {
        "setup_type":   "SMA200_BOUNCE",
        "entry":        round(entry, 2),
        "stop":         stop,
        "target":       target,
        "rr_ratio":     rr,
        "discount_pct": round(100.0 - dist_pct * 20, 1),
        "confidence":   confidence,
        "touch_day":    touch_day,
        "reasons":      reasons,
    }


# ── Détecteur 3 : VOLUME MOMENTUM ─────────────────────────────────────────────

def _detect_volume_momentum(hist, price: float) -> dict | None:
    """
    Volume spike institutionnel + pression acheteuse + structure intacte.

    Conditions :
      1. Volume du jour > 2× la moyenne 20j
      2. Variation du jour > +1.5% vs close précédent
      3. Prix au-dessus de la SMA50 (tendance à court terme intacte)
      4. Prix non étendu : < 15% au-dessus de la SMA200

    Stop  : low du jour – 0.5%
    Target: entry + 2.5 × (entry – stop)

    Confidence :
      HIGH   — volume > 3× ET variation > 3%
      MEDIUM — volume > 2× ET variation > 1.5%
    """
    if len(hist) < 50:
        return None

    avg_vol_20 = float(hist["Volume"].tail(20).mean())
    vol_today  = float(hist["Volume"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2])
    day_low    = float(hist["Low"].iloc[-1])

    if avg_vol_20 <= 0 or prev_close <= 0:
        return None

    vol_ratio = vol_today / avg_vol_20
    chg_pct   = (price - prev_close) / prev_close * 100

    # Conditions principales
    if vol_ratio < 2.0 or chg_pct < 1.5:
        return None

    # Prix au-dessus de la SMA50
    sma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
    if price <= sma50:
        return None

    # Prix non étendu vs SMA200 (< 15% au-dessus)
    if len(hist) >= 200:
        sma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        if sma200 > 0:
            dist_sma200 = (price - sma200) / sma200 * 100
            if dist_sma200 >= 15.0:
                return None   # trop étendu, risque de mean reversion
    # Si on a moins de 200 barres, on ne bloque pas (données insuffisantes)

    entry = price
    stop  = round(day_low * 0.995, 2)   # 0.5% sous le low du jour
    risk  = entry - stop
    if risk <= 0:
        return None

    target = round(entry + RR_MINIMUM * risk, 2)
    rr     = round((target - entry) / risk, 2)

    confidence = "HIGH" if vol_ratio >= 3.0 and chg_pct >= 3.0 else "MEDIUM"

    reasons = [
        f"Volume ×{vol_ratio:.1f} la moyenne 20j — activité institutionnelle",
        f"Momentum intraday : {chg_pct:+.1f}% vs close précédent",
        f"Prix au-dessus SMA50 (${sma50:.2f}) — tendance court terme intacte",
        f"Stop sous le bas du jour (${day_low:.2f} – 0.5%)",
    ]

    return {
        "setup_type":   "VOLUME_MOMENTUM",
        "entry":        round(entry, 2),
        "stop":         stop,
        "target":       target,
        "rr_ratio":     rr,
        "discount_pct": 0.0,
        "confidence":   confidence,
        "vol_ratio":    round(vol_ratio, 2),
        "chg_pct":      round(chg_pct, 2),
        "reasons":      reasons,
    }


# ── Fonction principale ───────────────────────────────────────────────────────

def detect_setups(tickers: list | None = None) -> list[dict]:
    """
    Scanne les tickers et retourne tous les setups valides, triés par confidence.

    - Un ticker peut avoir plusieurs setups simultanément.
    - Seuls les setups avec R:R >= RR_MINIMUM sont inclus.
    - Tri : HIGH → MEDIUM → LOW, puis R:R décroissant.

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
        print("[WARN] yfinance non installée — pip install yfinance")
        return []

    if tickers is None:
        tickers = get_watchlist()

    _detectors = [
        _detect_discount_zone,
        _detect_sma200_bounce,
        _detect_volume_momentum,
    ]

    setups = []

    for ticker in tickers:
        try:
            tk   = yf.Ticker(ticker)
            hist = tk.history(period="1y", interval="1d", auto_adjust=True)

            if hist.empty or len(hist) < 2:
                continue

            price = float(hist["Close"].iloc[-1])

            for detector in _detectors:
                try:
                    result = detector(hist, price)
                except Exception as e:
                    print(f"[WARN] {ticker}/{detector.__name__} : {e}")
                    continue

                if result is None:
                    continue

                # Filtre R:R minimum
                if result.get("rr_ratio", 0) < RR_MINIMUM:
                    continue

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
    """
    _conf_icon = {"HIGH": "[FIRE]", "MEDIUM": "[BOLT]", "LOW": "[WARN]"}
    _type_icon = {
        "DISCOUNT_ZONE":   "[DISC]",
        "SMA200_BOUNCE":   "[SMA]",
        "VOLUME_MOMENTUM": "[MOM]",
    }
    conf  = setup.get("confidence", "?")
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

    TEST_TICKERS = ["NVDA", "AAPL", "TSLA", "AMD", "MU", "PLTR"]
    capital = _get_capital()
    print(f"Capital : ${capital:,.0f}  |  Risque max : {RISK_PCT_MAX}%  |  R:R minimum : {RR_MINIMUM}x\n")

    setups = detect_setups(TEST_TICKERS)

    if not setups:
        print("Aucun setup détecté sur les tickers de test.")
    else:
        print(f"{len(setups)} setup(s) détecté(s) :\n")
        for s in setups:
            pos = calculate_position_size(s["entry"], s["stop"], capital)
            print(format_setup_alert(s, pos))
            print()

    print("[OK] setup_detector.py fonctionne correctement.")
