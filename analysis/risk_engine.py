"""
Moteur de risque autoritaire — source unique de vérité pour le sizing.

Remplace les calculs dispersés dans setup_detector.py et dashboard/api.py.
Toute logique de position sizing passe par validate_and_size().

Règles (depuis config.settings) :
  - LONG uniquement : target > entry > stop obligatoire
  - risk_pct dans [RISK_PCT_MIN, RISK_PCT_MAX] %
  - R:R >= RR_MINIMUM
  - exposure <= MAX_EXPOSURE_PCT %
  - trades_today < MAX_TRADES_PER_DAY
"""

import math
from typing import Optional

from config.settings import (
    RISK_PCT_MIN,
    RISK_PCT_MAX,
    RR_MINIMUM,
    MAX_TRADES_PER_DAY,
    MAX_EXPOSURE_PCT,
)
from analysis.technical_indicators import clean_for_json


def validate_and_size(
    capital: float,
    risk_pct: float,
    entry: float,
    stop: float,
    target: float,
    open_positions_value: float = 0.0,
    trades_today: int = 0,
) -> dict:
    """Valide les paramètres d'un trade LONG et calcule la taille de position.

    Args:
        capital: Capital total du compte (USD).
        risk_pct: Risque souhaité en % du capital (ex. 1.0 pour 1 %).
        entry: Prix d'entrée envisagé.
        stop: Stop-loss (doit être < entry).
        target: Cible de profit (doit être > entry).
        open_positions_value: Dollars déjà à risque sur positions ouvertes (USD).
            Ex. : 2 positions à 1 % de $10k = $200.
        trades_today: Nombre de trades déjà exécutés aujourd'hui.

    Returns:
        {
            verdict: "GO" | "NO-GO",
            violations: [str, ...],  # liste vide si GO
            shares: int,
            risk_amount: float,      # risque en USD sur ce trade
            rr: float,               # ratio reward/risk
            exposure_pct: float,     # exposition totale au risque en % capital
            position_value: float,   # valeur notionnelle de la position (USD)
        }

    Note sur exposure_pct :
        exposure_pct = (open_positions_value + risk_amount) / capital * 100
        Mesure le % du capital RISQUE (pas la valeur notionnelle), cohérent avec
        la règle "3 % simultané" = max 3 trades à 1 % chacun.
    """
    print(f"[RiskEngine] validate_and_size: capital={capital}, risk_pct={risk_pct}%, "
          f"entry={entry}, stop={stop}, target={target}, "
          f"open_risk={open_positions_value}, trades_today={trades_today}")

    violations: list[str] = []

    # --- Règle 1 : direction LONG obligatoire ---
    if not (target > entry > stop):
        violations.append(
            f"Direction invalide: exige target({target}) > entry({entry}) > stop({stop})"
        )

    # --- Règle 2 : risk_pct dans les bornes ---
    if not (RISK_PCT_MIN <= risk_pct <= RISK_PCT_MAX):
        violations.append(
            f"risk_pct={risk_pct}% hors bornes [{RISK_PCT_MIN}, {RISK_PCT_MAX}]%"
        )

    # --- Règle 3 : max trades par jour ---
    if trades_today >= MAX_TRADES_PER_DAY:
        violations.append(
            f"trades_today={trades_today} >= limite {MAX_TRADES_PER_DAY}"
        )

    # Calculs (même si violations, pour retourner les valeurs informationnelles)
    risk_per_share = max(entry - stop, 1e-9)  # protection division / 0
    risk_amount = capital * (risk_pct / 100.0)
    shares = max(0, math.floor(risk_amount / risk_per_share))
    position_value = shares * entry
    # exposure = % du capital RISQUE (pas valeur notionnelle) : max 3 trades @ 1% = 3%
    exposure_pct = (open_positions_value + risk_amount) / capital * 100.0

    # R:R (calculé seulement si la direction est valide)
    rr = 0.0
    if entry > stop and target > entry:
        rr = (target - entry) / (entry - stop)

    # --- Règle 4 : R:R minimum ---
    if entry > stop and target > entry and rr < RR_MINIMUM:
        violations.append(
            f"R:R={rr:.2f} < minimum {RR_MINIMUM}"
        )

    # --- Règle 5 : exposition totale ---
    if exposure_pct > MAX_EXPOSURE_PCT:
        violations.append(
            f"Exposition={exposure_pct:.1f}% > limite {MAX_EXPOSURE_PCT}%"
        )

    verdict = "GO" if not violations else "NO-GO"

    result = {
        "verdict": verdict,
        "violations": violations,
        "shares": shares,
        "risk_amount": round(risk_amount, 2),
        "rr": round(rr, 3),
        "exposure_pct": round(exposure_pct, 2),
        "position_value": round(position_value, 2),
    }

    print(f"[RiskEngine] => {verdict} | R:R={rr:.2f} | shares={shares} | "
          f"exposure={exposure_pct:.1f}% | violations={violations}")

    return clean_for_json(result)
