"""
Pullback Scanner — Détecte les actions de la watchlist en zone de survente.

Critères :
  - RSI < 35
  - Bollinger %B < 0 (sous la bande basse)
  - Stochastique %K < 20

Classification :
  - "alert"      : 2+ conditions remplies
  - "watch"      : 1 condition remplie
  - "neutral"    : 0 condition
  - "overbought" : RSI > 70
"""

from __future__ import annotations
from datetime import datetime

try:
    from config.settings import WATCHLIST
except Exception:
    WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "META", "AMZN", "GOOGL",
        "AMD", "AVGO", "QCOM", "INTC", "MU", "ASML", "TSM", "MRVL",
        "PLTR", "SMCI", "CRM", "SNOW", "TWLO", "ZS", "BABA",
    ]

from analysis.technical_indicators import analyze_ticker, clean_for_json
from analysis.market_breadth import get_market_breadth


def _build_interpretation(item: dict, breadth: dict) -> str:
    """Génère une phrase d'interprétation pour un ticker en survente."""
    parts = []
    rsi   = item.get("rsi")
    bb    = item.get("bb_percent_b")
    stoch = item.get("stoch_k")
    cond  = item.get("conditions_met", 0)
    bs    = breadth.get("breadth_strength", "unknown")

    if cond >= 3:
        parts.append("Zone de survente extrême (3/3 conditions)")
    elif cond == 2:
        parts.append("Zone de survente confirmée (2/3 conditions)")
    elif cond == 1:
        parts.append("Signal faible (1/3 condition)")

    if rsi is not None and rsi < 30:
        parts.append(f"RSI très bas ({rsi:.1f})")
    if bb is not None and bb < -0.1:
        parts.append("Prix largement sous la bande basse")

    if bs == "bullish":
        parts.append("Marché haussier → rebond possible")
    elif bs == "bearish":
        parts.append("Marché baissier → attendre confirmation")
    else:
        parts.append("Marché neutre → patience")

    return " · ".join(parts) if parts else "Surveiller"


def scan_pullbacks(extra_tickers: list[str] | None = None) -> dict:
    """
    Scanne la watchlist (+ tickers extra optionnels) à la recherche de surventes.
    Retourne alertes triées par conditions_met décroissant + contexte marché.
    """
    tickers = list(WATCHLIST)
    if extra_tickers:
        for t in extra_tickers:
            if t.upper() not in tickers:
                tickers.append(t.upper())

    print(f"[PullbackScanner] Scan de {len(tickers)} tickers...")

    # Breadth marché en parallèle
    try:
        breadth = get_market_breadth()
    except Exception as e:
        print(f"[PullbackScanner] breadth error: {e}")
        breadth = {"ad_ratio": 1.0, "breadth_strength": "unknown"}

    bs = breadth.get("breadth_strength", "unknown")
    ad = breadth.get("ad_ratio", 1.0)
    if bs == "bullish":
        ctx_text = "Marché haussier → signaux de survente plus fiables, rebonds plus probables"
    elif bs == "bearish":
        ctx_text = "Marché baissier → surventes peuvent continuer, attendre confirmation"
    else:
        ctx_text = "Marché neutre → signaux spécifiques aux actions, analyser au cas par cas"

    alerts   : list[dict] = []
    watches  : list[dict] = []
    no_alerts: list[dict] = []

    for ticker in tickers:
        try:
            data = analyze_ticker(ticker)
            if data.get("error"):
                print(f"[PullbackScanner] {ticker}: erreur {data['error']}")
                continue

            rsi   = data.get("rsi")
            bb    = data.get("bollinger", {}).get("percent_b")
            stoch = data.get("stochastic", {}).get("k")
            price = data.get("price")
            chg   = data.get("change_pct", 0.0)
            sigs  = data.get("signals", {})
            cond  = sigs.get("pullback_conditions_met", 0)

            # Classification
            if rsi is not None and rsi > 70:
                status = "overbought"
            elif cond >= 2:
                status = "alert"
            elif cond == 1:
                status = "watch"
            else:
                status = "neutral"

            entry = {
                "ticker":        ticker,
                "status":        status,
                "conditions_met": cond,
                "rsi":           rsi,
                "bb_percent_b":  bb,
                "stoch_k":       stoch,
                "price":         price,
                "change_pct":    chg,
                "rsi_oversold":       sigs.get("oversold", False),
                "bb_below_lower":     sigs.get("below_bb_lower", False),
                "stoch_oversold":     sigs.get("stoch_oversold", False),
                "interpretation": "",
            }
            entry["interpretation"] = _build_interpretation(entry, breadth)

            if status == "alert":
                alerts.append(entry)
            elif status in ("watch", "overbought"):
                watches.append(entry)
            else:
                no_alerts.append(entry)

        except Exception as e:
            print(f"[PullbackScanner] {ticker}: exception {e}")
            continue

    # Tri par conditions_met décroissant
    alerts.sort(key=lambda x: -x["conditions_met"])
    watches.sort(key=lambda x: -(x.get("conditions_met") or 0))

    print(f"[PullbackScanner] {len(alerts)} alertes, {len(watches)} à surveiller, {len(no_alerts)} neutres")

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "scanned_at": datetime.now().isoformat(),
        "tickers_scanned": len(tickers),
        "market_context": {
            "breadth":        bs,
            "ad_ratio":       ad,
            "interpretation": ctx_text,
            "advancers":      breadth.get("advancers", 0),
            "decliners":      breadth.get("decliners", 0),
        },
        "alerts":    alerts,
        "watches":   watches,
        "no_alerts": no_alerts,
        "summary": {
            "alert_count":   len(alerts),
            "watch_count":   len(watches),
            "neutral_count": len(no_alerts),
        },
    }
    return clean_for_json(result)
