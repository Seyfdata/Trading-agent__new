"""
Moteur de risque autoritaire — source unique de verite pour le sizing.

Remplace les calculs disperses dans setup_detector.py et dashboard/api.py.
Toute logique de position sizing passe par validate_and_size().

Regles (depuis config.settings) :
  - LONG uniquement : target > entry > stop obligatoire
  - risk_pct dans [RISK_PCT_MIN, RISK_PCT_MAX] %
  - R:R >= RR_MINIMUM
  - risk_exposure_pct (heat) <= MAX_EXPOSURE_PCT %
  - deployed (notionnel total) <= capital  [compte cash, pas de marge]
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
    open_risk_amount: float = 0.0,
    open_notional: float = 0.0,
    trades_today: int = 0,
) -> dict:
    """Valide les parametres d'un trade LONG et calcule la taille de position.

    Args:
        capital: Capital total du compte (USD).
        risk_pct: Risque souhaite en % du capital (ex. 1.0 pour 1 %).
        entry: Prix d'entree envisage.
        stop: Stop-loss (doit etre < entry).
        target: Cible de profit (doit etre > entry).
        open_risk_amount: Dollars deja a risque sur positions ouvertes (USD).
            Ex. : 2 positions a 1 % de $10k = $200.
        open_notional: Valeur notionnelle totale des positions ouvertes (USD).
            Ex. : 2 positions de $4000 chacune = $8000.
        trades_today: Nombre de trades deja executes aujourd'hui.

    Returns:
        {
            verdict: "GO" | "NO-GO",
            violations: [str, ...],
            shares: int,
            risk_amount: float,         # risque en USD sur ce trade
            rr: float,                  # ratio reward/risk
            risk_exposure_pct: float,   # % capital risque (heat) : <= 3 %
            deployed_pct: float,        # % capital deploye en notionnel
            position_value: float,      # notionnel de ce trade (USD)
        }

    Notes:
        risk_exposure_pct = (open_risk_amount + risk_amount) / capital * 100
            Cap a MAX_EXPOSURE_PCT % : max 3 trades x 1 % = 3 % de heat.
        deployed = open_notional + position_value
            deployed > capital -> NO-GO : compte cash, pas de marge.
    """
    print(f"[RiskEngine] validate_and_size: capital={capital}, risk_pct={risk_pct}%, "
          f"entry={entry}, stop={stop}, target={target}, "
          f"open_risk={open_risk_amount}, open_notional={open_notional}, "
          f"trades_today={trades_today}")

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

    # Calculs (meme si violations, pour retourner les valeurs informationnelles)
    risk_per_share = max(entry - stop, 1e-9)  # protection division / 0
    risk_amount = capital * (risk_pct / 100.0)
    shares = max(0, math.floor(risk_amount / risk_per_share))
    position_value = shares * entry

    # Heat = % capital risque (open + nouveau trade) ; cap MAX_EXPOSURE_PCT
    risk_exposure_pct = (open_risk_amount + risk_amount) / capital * 100.0

    # Deploiement cash = notionnel total des positions (open + nouveau trade)
    deployed = open_notional + position_value
    deployed_pct = deployed / capital * 100.0

    # R:R (calcule seulement si la direction est valide)
    rr = 0.0
    if entry > stop and target > entry:
        rr = (target - entry) / (entry - stop)

    # --- Regle 4 : R:R minimum (epsilon 1e-9 pour eviter faux-negatif flottant) ---
    if entry > stop and target > entry and rr < RR_MINIMUM - 1e-9:
        violations.append(
            f"R:R={rr:.2f} < minimum {RR_MINIMUM}"
        )

    # --- Regle 5 : heat (risque en % capital) ---
    if risk_exposure_pct > MAX_EXPOSURE_PCT:
        violations.append(
            f"Risk heat={risk_exposure_pct:.1f}% > limite {MAX_EXPOSURE_PCT}%"
        )

    # --- Regle 6 : deploiement cash (compte sans marge) ---
    if deployed > capital:
        violations.append(
            f"Notional depasse le capital disponible (compte cash) : "
            f"${deployed:,.0f} > ${capital:,.0f}"
        )

    verdict = "GO" if not violations else "NO-GO"

    result = {
        "verdict": verdict,
        "violations": violations,
        "shares": shares,
        "risk_amount": round(risk_amount, 2),
        "rr": round(rr, 3),
        "risk_exposure_pct": round(risk_exposure_pct, 2),
        "deployed_pct": round(deployed_pct, 2),
        "position_value": round(position_value, 2),
    }

    print(f"[RiskEngine] => {verdict} | R:R={rr:.2f} | shares={shares} | "
          f"heat={risk_exposure_pct:.1f}% | deployed={deployed_pct:.1f}% | "
          f"violations={violations}")

    return clean_for_json(result)
