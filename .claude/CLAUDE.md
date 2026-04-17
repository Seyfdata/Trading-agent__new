# CLAUDE.md — Instructions pour Claude Code

> Ce fichier est lu automatiquement par Claude Code à chaque session.
> Il donne le contexte complet du projet pour des réponses précises et cohérentes.

---

## 🎯 Identité du projet

**Nom** : SMC-AI Trading Agent  
**Créateur** : Seyf — 43 ans, métrologue/formateur, swing trader actions US, IBKR réel  
**Objectif** : cockpit de trading local (dashboard web) qui détecte des opportunités, guide le trader pas à pas, et enregistre les trades pour mesurer la performance  

**Ce n'est PAS** : un bot de trading automatique. L'humain décide toujours. L'agent propose, l'humain dispose.

---

## 🏗️ Architecture du projet

```
trading-agent/
├── config/
│   ├── settings.py          # Watchlist, aliases, constantes (charge depuis YAML)
│   ├── loader.py            # Chargeur config.yaml avec fallback
│   └── config.yaml          # Configuration externalisée (watchlist, seuils, killzone)
├── scrapers/
│   ├── market_data.py       # Données marché via yfinance (SPY, VIX, watchlist)
│   ├── reddit.py            # Wrapper Reddit + scan direct + buzztickr + trouvailles
│   ├── rss_news.py          # 10 flux RSS filtrés par ticker/alias
│   └── macro_calendar.py    # Calendrier macro (NFP, CPI, FOMC)
├── analysis/
│   ├── scoring.py           # Score composite 0-100 (SMA200 + Volume + Reddit + News)
│   ├── setup_detector.py    # Détection setups (discount, SMA200 bounce, volume momentum)
│   ├── smc_analyzer.py      # Analyse SMC algorithmique (BOS/CHoCH, OB, FVG, Liquidity)
│   ├── unified_scorer.py    # Score unifié 0-10 (setup_detector × smc_analyzer × options)
│   ├── options_flow.py      # Sentiment options (PCR, max pain, unusual activity)
│   ├── reddit_trend.py      # Tendances Reddit 5 jours + vérification tickers
│   ├── advanced_metrics.py  # Sharpe, Sortino, Calmar, Kelly, Monte Carlo
│   └── backtester.py        # Backtest 3 stratégies sur données historiques
├── database/
│   ├── models.py            # SQLite : scores_history, market_context, trades
│   └── trading_agent.db     # Base de données (gitignored)
├── dashboard/
│   ├── api.py               # Serveur FastAPI (~20 endpoints)
│   └── index.html           # Dashboard React standalone (CDN, pas de build)
├── notifications/
│   └── telegram.py          # Envoi Telegram (désactivé, flag TELEGRAM_ENABLED=False)
├── pinescripts/
│   ├── smc_all_in_one.pine  # Indicateur TradingView all-in-one
│   ├── smc_strategy_backtest.pine  # Stratégie backtest TradingView
│   └── INSTALL.md           # Guide installation Pine Script
├── RedditScanner/           # Scanner Reddit standalone (PRO v4, préservé)
├── morning_scan.py          # Orchestrateur original (remplacé par le dashboard)
├── launch_dashboard.py      # Lanceur dashboard (tue le port, lance FastAPI, ouvre navigateur)
├── launch_dashboard.bat     # Raccourci Windows
├── requirements.txt         # Dépendances Python
├── .env                     # Variables d'environnement (gitignored)
├── .env.example             # Template .env
├── ROADMAP.md               # Roadmap du projet
└── CLAUDE.md                # CE FICHIER
```

---

## ⚙️ Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.10+, FastAPI, uvicorn |
| Frontend | React 18 via CDN (unpkg.com), Recharts, Babel standalone |
| Base de données | SQLite (database/trading_agent.db) |
| Données marché | yfinance (gratuit, pas d'API key) |
| Données Reddit | JSON public Reddit (pas d'API Reddit, pas de PRAW) |
| Charting | TradingView (compte gratuit, Pine Script v5) |
| Broker | Interactive Brokers (IBKR, trading réel) |
| Versioning | Git + GitHub (repo privé) |
| Environnement | Windows, VS Code, Claude Code |
| Coût | 0€/mois (aucune API payante) |

---

## 🎯 Core Rules — NE JAMAIS VIOLER

| Règle | Valeur |
|-------|--------|
| Direction | **LONG uniquement** (compte cash, pas de short) |
| Risque/trade | **0.5-1% du capital** max |
| R:R minimum | **1:2.5** — aucun trade en dessous |
| Max trades/jour | **2** |
| Exposition max | **3%** du capital simultané |
| Killzone | **14h30-16h30 CET** uniquement |
| Instruments | Actions US uniquement |
| News | Éviter FOMC, NFP, CPI, earnings |

---

## 📊 Dashboard — 11 onglets

| # | Onglet | Rôle |
|---|--------|------|
| 1 | Vue d'ensemble | Macro, régime BULL/BEAR, verdict GO/NO TRADE, Top 3, positions |
| 2 | 🤝 Coach | **Copilote débutant** — stepper 5 étapes, GO/NO GO, guide IBKR |
| 3 | Watchlist | 22 tickers scorés 0-100, barres SHAP, liens TradingView |
| 4 | Reddit | Mentions watchlist + trouvailles buzztickr (grille cartes) |
| 5 | News | News tickers + macro filtrées (10 sources RSS) |
| 6 | Alertes | Killzone live (volume/SMA200/mouvement), alertes positions |
| 7 | Setups | Détecteur discount/SMA200/momentum, position sizing |
| 8 | Analyse SMC | Structure marché, OB, FVG, score unifié, options flow |
| 9 | Journal | Formulaire saisie trade, positions ouvertes PnL live, historique |
| 10 | Performance | Equity curve, heatmap, drawdown, Sharpe/Sortino/Monte Carlo, backtest |
| 11 | Guide | Tutoriel 12 sections FR + EN, glossaire |

---

## 🔌 API — Endpoints principaux

```
GET  /dashboard              → Page HTML du dashboard
GET  /api/market              → Contexte marché (SPY, VIX, DXY, régime)
GET  /api/tickers             → Watchlist 22 tickers scorés
GET  /api/reddit              → Mentions Reddit (watchlist uniquement)
GET  /api/reddit/discoveries  → Trouvailles hors watchlist
GET  /api/news                → News RSS filtrées
GET  /api/macro               → Calendrier macro
GET  /api/alerts              → Alertes killzone
GET  /api/alerts/news         → Breaking news 30 min
GET  /api/setups              → Setups détectés
GET  /api/analysis/{ticker}   → Analyse SMC complète
GET  /api/unified/{ticker}    → Score unifié (setup × SMC × options)
GET  /api/unified             → Top 5 scores unifiés
GET  /api/options/{ticker}    → Options flow (PCR, max pain)
GET  /api/positions/monitor   → Suivi positions temps réel
GET  /api/postmarket          → Résumé post-market
GET  /api/performance         → Métriques de base
GET  /api/performance/advanced → Sharpe, Sortino, Monte Carlo
GET  /api/backtest/{ticker}   → Backtest 3 stratégies
GET  /api/history             → Historique des scores
POST /api/refresh             → Scan complet (market + reddit + news)
POST /api/trades              → Créer un trade
GET  /api/trades              → Lister les trades
PUT  /api/trades/{id}/close   → Clôturer un trade
DELETE /api/trades/{id}       → Supprimer un trade
POST /api/watchlist/temp      → Ajouter ticker temporaire
DELETE /api/watchlist/temp/{t} → Retirer ticker temporaire
```

---

## 📏 Conventions de code

### Python
- Encoding : UTF-8 partout
- Imports : depuis config.settings pour WATCHLIST, TICKER_ALIASES
- Erreurs : try/except sur chaque endpoint, retourner du JSON valide même en cas d'erreur
- Types numpy : utiliser `clean_for_json()` avant tout retour API (numpy.bool → bool, etc.)
- Logs : print() avec préfixe `[Module]` (ex: `[Reddit]`, `[Scoring]`, `[API]`)
- venv : `.venv\Scripts\activate` sur Windows
- pip : `pip install --break-system-packages` si hors venv

### JavaScript/React (dashboard/index.html)
- Fichier HTML standalone — PAS de build, PAS de npm, PAS de webpack
- React 18 + ReactDOM via CDN unpkg.com
- Recharts via CDN pour les graphiques
- Babel standalone pour la compilation JSX
- **PAS d'imports ES6** : utiliser `const { useState, useEffect } = React;`
- **PAS de localStorage** : utiliser des states React uniquement
- **PAS de balise `<form>`** : utiliser onChange + onClick
- **HOOKS EN PREMIER** : tous les useState/useEffect AVANT tout return conditionnel
- **DIVS ÉQUILIBRÉES** : après chaque modification, vérifier le balance des `<div>`/`</div>`
- Composants Recharts extraits en haut : `const { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, Legend, ReferenceLine } = Recharts;`

### Pine Script (TradingView)
- Version 5 uniquement (`//@version=5`)
- PAS d'opérateur ternaire `?` → utiliser `if/else`
- PAS de `+` en début de ligne (continuation) → concaténer sur une ligne ou utiliser `:=`
- `ta.crossover()`/`ta.crossunder()` : TOUJOURS au niveau global, JAMAIS dans un `if`
- Compatible TradingView gratuit (3 indicateurs max, 1 alerte)

---

## 🧠 Watchlist — 22 tickers

```
Mag7 :  AAPL, NVDA, TSLA, MSFT, META, AMZN, GOOGL
Semi :  AMD, AVGO, QCOM, INTC, MU, ASML, TSM, MRVL
Tech :  PLTR, SMCI, CRM, SNOW, TWLO, ZS, BABA
```

Aliases configurés dans config.yaml (ex: Broadcom → AVGO, Nvidia → NVDA)

---

## 🚨 Pièges connus — Éviter absolument

1. **numpy.bool dans l'API** : yfinance retourne des types numpy → toujours appliquer `clean_for_json()` avant de retourner des données
2. **Port 8000 occupé** : `launch_dashboard.py` tue le port avant de lancer, mais si ça échoue → `taskkill /PID XXX /F`
3. **React hooks order** : JAMAIS de useState après un return conditionnel → crash "Rendered more hooks"
4. **Div imbalance** : après chaque modification du HTML, compter les `<div>` et `</div>` → doivent être égaux
5. **Reddit sans API** : on scrape le JSON public (`/r/sub/hot.json`), PAS de PRAW, PAS d'API key Reddit
6. **Pine Script continuation** : pas de `+` en début de ligne, pas de `?` ternaire
7. **PowerShell vs CMD** : les parenthèses dans les textes sont interprétées par PowerShell → coller les prompts dans Claude Code, PAS dans le terminal
8. **Fichier .env** : n'est PAS sur GitHub (gitignored), doit être recréé sur chaque machine depuis `.env.example`

---

## 📋 Commandes utiles

```bash
# Lancer le dashboard
python launch_dashboard.py
# ou
launch_dashboard.bat

# Tester les imports
python -c "from config.settings import WATCHLIST; print(f'{len(WATCHLIST)} tickers')"
python -c "from database.models import init_db; init_db(); print('DB OK')"

# Audit syntaxe HTML
python -c "
content = open('dashboard/index.html', encoding='utf-8').read()
print(f'div ouvrantes: {content.count(\"<div\")}')
print(f'div fermantes: {content.count(\"</div>\")}')
"

# Git
git add . && git commit -m "message" && git push origin main
git pull origin main  # sur l'autre poste
```

---

## 📊 État du projet

- **Phase 1** : ✅ Morning Brief PRO
- **Phase 2A** : ✅ Scoring + Dashboard
- **Phase 2B** : ✅ Workflow automatisé
- **Phase 3** : 🔄 95% (analyse SMC, options flow, backtest, Coach)
- **Phase 4** : ⬜ Connexion IBKR API (prérequis : 50+ trades, 6+ mois)

**Priorités actuelles** :
1. Fiabiliser Reddit (scan direct, pas de CSV stagnant)
2. Simplifier l'UX (mode simple/expert dans Analyse SMC)
3. Connecter les onglets entre eux (Reddit → Setups → Analyse)
4. Accumuler 50 trades dans le journal

---

## 🗣️ Ton et style

- **Tutoiement** (Seyf préfère le tu)
- **Français** avec termes techniques en anglais
- **Direct et concret** : pas de blabla, des actions claires
- **Honnête** : dire quand quelque chose ne sert à rien
- **Coach** : encourager mais ne jamais promettre de gains
- Rappeler : "Le trading comporte des risques de perte en capital"
