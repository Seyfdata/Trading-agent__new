# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Identité du projet

**SMC-AI Trading Agent** — cockpit de trading local (dashboard web) qui détecte des opportunités, guide le trader pas à pas, et enregistre les trades pour mesurer la performance.  
**Créateur** : Seyf — swing trader actions US, compte cash IBKR réel. LONG uniquement. L'humain décide toujours.

---

## Commandes courantes

```bash
# Lancer le dashboard (tue le port 8000, ouvre le navigateur)
python launch_dashboard.py

# Vérifier les imports clés
python -c "from config.settings import WATCHLIST; print(f'{len(WATCHLIST)} tickers')"
python -c "from database.models import init_db; init_db(); print('DB OK')"

# Audit div HTML (toujours vérifier après modification de index.html)
python -c "
c = open('dashboard/index.html', encoding='utf-8').read()
print(f'<div: {c.count(chr(60)+\"div\")}, </div>: {c.count(\"</div>\")}')
"

# Git
git add . && git commit -m "type: message" && git push origin main
```

---

## Architecture — vue d'ensemble

### Stack

| Couche | Technologie |
|--------|-------------|
| Backend | Python 3.10+, FastAPI, uvicorn, port 8000 |
| Frontend | React 18 + Recharts via CDN, Babel standalone — **fichier HTML unique**, pas de build |
| BDD | SQLite (`database/trading_agent.db`, gitignored) |
| Données | yfinance (gratuit, 0 API key) |
| Reddit | Scraping JSON public `/r/sub/hot.json` — pas de PRAW |

### Flux de données

```
config/config.yaml
    → config/settings.py (WATCHLIST, TICKER_ALIASES, seuils)
        → scrapers/ (market_data, reddit, rss_news, macro_calendar)
        → analysis/ (scoring, smc_analyzer, unified_scorer, options_flow…)
            → dashboard/api.py (FastAPI ~40 endpoints)
                → dashboard/index.html (React, polling toutes les 30s)
```

### Modules analysis (ordre de dépendance)

```
technical_indicators.py   ← fonctions pures RSI/BB/Stoch/ADX/MACD/MAs, clean_for_json()
market_breadth.py         ← 50 constituants S&P500, A/D ratio, cache 5 min
pullback_scanner.py       ← RSI<35 + BB%B<0 + Stoch<20 → alert/watch/neutral/overbought
relative_strength.py      ← alpha vs SPY sur 1W/1M/3M, ADX, short interest, cache 5 min
scoring.py                ← score composite 0-100 (SMA200 + Volume + Reddit + News)
setup_detector.py         ← discount/SMA200 bounce/momentum
smc_analyzer.py           ← BOS/CHoCH, Order Blocks, FVG, Liquidity algorithmique
unified_scorer.py         ← score 0-10 (setup × SMC × options)
options_flow.py           ← PCR, max pain, unusual activity
backtester.py             ← 3 stratégies sur données historiques
advanced_metrics.py       ← Sharpe, Sortino, Calmar, Kelly, Monte Carlo
```

---

## API — endpoints complets

```
# Marché & tickers
GET  /api/market              → SPY, VIX, DXY, régime BULL/BEAR
GET  /api/tickers             → watchlist 22 tickers scorés 0-100
GET  /api/indicators/{ticker} → RSI, Bollinger, Stoch, ADX, MACD
GET  /api/breadth             → ampleur marché (A/D ratio, top gainers/losers)

# Reddit & News
GET  /api/reddit              → mentions watchlist
GET  /api/reddit/discoveries  → trouvailles hors watchlist
GET  /api/news                → news RSS filtrées
GET  /api/macro               → calendrier macro (NFP, CPI, FOMC)

# Scanners
GET  /api/pullbacks           → tickers en zone survente (alert/watch)
GET  /api/relative-strength   → ranking alpha vs SPY
GET  /api/alpha/{ticker}      → alpha détaillé d'un ticker
GET  /api/deep-analysis/{ticker} → analyse approfondie (ADX, short int.)

# SMC & Setups
GET  /api/analysis/{ticker}   → analyse SMC complète (BOS, OB, FVG)
GET  /api/unified/{ticker}    → score unifié 0-10
GET  /api/unified             → top 5 scores unifiés
GET  /api/setups              → setups détectés + position sizing
GET  /api/options/{ticker}    → PCR, max pain, unusual activity

# Alertes
GET  /api/alerts              → alertes killzone live
GET  /api/alerts/news         → breaking news <30 min

# Journal & Performance
POST /api/trades              → créer un trade
GET  /api/trades              → lister les trades
PUT  /api/trades/{id}/close   → clôturer
DELETE /api/trades/{id}       → supprimer
GET  /api/performance         → métriques de base
GET  /api/performance/advanced → Sharpe, Sortino, Monte Carlo
GET  /api/backtest/{ticker}   → backtest 3 stratégies
GET  /api/backtest/report     → rapport global backtest

# Utilitaires
GET  /api/ping                → healthcheck
GET  /api/history             → historique scores (14j par défaut)
GET  /api/positions/monitor   → suivi positions temps réel
GET  /api/postmarket          → résumé post-market
POST /api/refresh             → scan complet (market + reddit + news)
POST /api/watchlist/temp      → ajouter ticker temporaire
DELETE /api/watchlist/temp/{t} → retirer ticker temporaire
```

---

## Core Rules de trading — NE JAMAIS VIOLER

| Règle | Valeur |
|-------|--------|
| Direction | LONG uniquement |
| Risque/trade | 0.5-1% du capital |
| R:R minimum | **1:2.5** |
| Max trades/jour | 2 |
| Exposition max | 3% simultané |
| Killzone | 14h30-16h30 CET uniquement |
| Instruments | Actions US uniquement |

---

## Conventions de code critiques

### Python
- `clean_for_json()` obligatoire avant tout retour API (numpy.bool_, numpy.float64 → types Python natifs)
- Imports depuis `config.settings` pour `WATCHLIST`, `TICKER_ALIASES`
- `try/except` sur chaque endpoint FastAPI, retourner JSON valide même en erreur
- Logs : `print()` avec préfixe `[Module]`

### JavaScript/React (`dashboard/index.html`)
- **Pas d'imports ES6** : `const { useState, useEffect } = React;`
- **Hooks EN PREMIER** : tous les `useState`/`useEffect` avant tout `return` conditionnel
- **Pas de `<form>`** : `onChange` + `onClick` uniquement
- **Pas de localStorage**
- Vérifier le balance `<div>`/`</div>` après chaque modification

### Pine Script (`pinescripts/`)
- Version 5 uniquement
- Pas d'opérateur ternaire `?` → `if/else`
- `ta.crossover()`/`ta.crossunder()` au niveau global, jamais dans un `if`

---

## Pièges connus

1. **Port 8000 occupé** → `launch_dashboard.py` tue le port, ou `taskkill /PID XXX /F`
2. **numpy types dans l'API** → appliquer `clean_for_json()` (dans `technical_indicators.py`)
3. **React hooks order** → crash "Rendered more hooks" si `useState` après `return` conditionnel
4. **Div imbalance** → `<div>` et `</div>` doivent être égaux dans `index.html`
5. **Reddit sans API** → scraping JSON public uniquement, pas de PRAW
6. **PowerShell** → les parenthèses dans les textes sont interprétées ; coller les prompts dans Claude Code

---

## État du projet

| Phase | Statut |
|-------|--------|
| Phase 1 — Morning Brief PRO | ✅ |
| Phase 2 — Scoring + Dashboard | ✅ |
| Phase 3 — SMC, options, backtest, Coach, Pullback Scanner, RS Scout | ✅ 100% |
| Phase 4 — Connexion IBKR API | ⬜ À venir |

**Priorités actuelles** : utiliser le journal de trades dès maintenant, exploiter tous les onglets (Propositions → Analyse → Journal).

---

## Outils Claude Code installés

### Plugins actifs

| Plugin | Rôle |
|--------|------|
| **ECC** (Everything Claude Code) | Skills, agents, hooks, rules — écosystème complet |
| **claude-mem** | Mémoire sémantique persistante inter-sessions |

### MCP servers disponibles

| MCP | Commande | Usage typique pour ce projet |
|-----|----------|------------------------------|
| `ecc:exa` | `mcp__plugin_ecc_exa__web_search_exa` | Recherche stratégies trading, docs yfinance, news marché |
| `ecc:context7` | `mcp__plugin_ecc_context7__query-docs` | Docs FastAPI, pandas, React, yfinance |
| `ecc:github` | `mcp__plugin_ecc_github__*` | Gestion PRs, issues, push de code |
| `ecc:playwright` | `mcp__plugin_ecc_playwright__*` | Tests UI du dashboard dans le navigateur |
| `ecc:memory` | `mcp__plugin_ecc_memory__*` | Graphe de connaissances projet |
| `ecc:sequential-thinking` | `mcp__plugin_ecc_sequential-thinking__*` | Raisonnement structuré sur des problèmes complexes |
| `claude-mem` | `mcp__plugin_claude-mem_mcp-search__*` | Retrouver décisions et patterns des sessions passées |
| `claude_ai:Gmail` | `mcp__claude_ai_Gmail__*` | Notifications, alertes par email |
| `claude_ai:Google_Drive` | `mcp__claude_ai_Google_Drive__*` | Export/import de données |

### Skills ECC utiles pour ce projet

Invoquer avec `/ecc:<skill>` ou `/nom-court` :

| Skill | Commande | Quand l'utiliser |
|-------|----------|-----------------|
| `deep-research` | `/ecc:deep-research` | Rechercher nouvelles stratégies SMC, docs techniques |
| `market-research` | `/ecc:market-research` | Analyser concurrents, tendances outils trading |
| `security-review` | `/ecc:security-review` | Auditer api.py avant déploiement |
| `python-review` | `/ecc:python-review` | Review modules analysis/, scrapers/ |
| `e2e-testing` | `/ecc:e2e` | Tests Playwright du dashboard (killzone, journal) |
| `tdd-workflow` | `/ecc:tdd` | TDD pour nouveaux modules d'analyse |
| `verification-loop` | `/ecc:verify` | Validation complète avant release |
| `blueprint` | `/ecc:blueprint` | Planifier une fonctionnalité multi-sessions |
| `plan` | `/ecc:plan` | Planifier une feature dans la session courante |
| `mem-search` | `/claude-mem:mem-search` | Retrouver contexte des sessions précédentes |

### Hooks actifs (automatiques, ne pas contourner)

| Hook | Déclencheur | Effet |
|------|-------------|-------|
| `block-no-verify` | `git commit --no-verify` | Bloqué — ne jamais bypasser |
| `quality-gate` | Après Edit/Write | Vérifie qualité du code modifié |
| `governance-capture` | Bash/Edit/Write | Capture les décisions d'architecture |
| `continuous-learning-v2` | Toutes actions | Apprend les patterns pour sessions futures |
| `cost-tracker` | Fin de session | Suit le coût API |
| `config-protection` | Edit/Write | Protège les fichiers de config sensibles |
| `pre-bash-commit-quality` | Avant commit | Vérifie format et qualité du message |

### Workflow Claude Code pour ce projet

```bash
# Recherche rapide dans la mémoire des sessions passées
/claude-mem:mem-search "pullback scanner"

# Planifier une nouvelle fonctionnalité
/ecc:plan

# Review du code Python après modification
/ecc:python-review

# Test E2E du dashboard
/ecc:e2e

# Rechercher une stratégie trading ou doc technique
/ecc:deep-research "SMC order block detection algorithm"

# Vérification complète avant commit
/ecc:verify
```

---

## Fichiers de référence

- `GUIDE_UTILISATEUR.md` — guide complet pour l'utilisateur final (débutant)
- `ROADMAP.md` — roadmap consolidée
- `skills/trading-coach.skill` — skill pour le coaching trading
- `skills/webapp-testing.skill` — skill pour les tests webapp
- `everything-claude-code/` — repo ECC local (ne pas modifier)
