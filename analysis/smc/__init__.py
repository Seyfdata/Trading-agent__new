"""
Package analysis.smc — moteur SMC (Smart Money Concepts).

API publique inchangée : les consommateurs peuvent importer depuis ici
ou continuer à importer depuis analysis.smc_analyzer (les deux fonctionnent).

Migration progressive (T3.2-T3.5) :
  T3.2 → analysis/smc/asian_range.py  (detect_asian_range, detect_liquidity_sweeps)
  T3.3 → analysis/smc/structure.py    (_detect_swings, _analyze_structure)
  T3.4 → analysis/smc/blocks.py       (_detect_order_blocks, _detect_fvg)
  T3.5 → analysis/smc/levels.py       (_detect_liquidity, _discount_premium, …)
         analysis/smc/scoring.py      (_build_setup, _no_trade_reason)
"""
from analysis.smc_analyzer import (
    analyze_ticker,
    analyze_ticker_smc,
    format_smc_report,
)

__all__ = [
    "analyze_ticker",
    "analyze_ticker_smc",
    "format_smc_report",
]
