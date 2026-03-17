# 🗺️ ROADMAP — Trading Agent SMC-AI

> **Dernière mise à jour** : 17 mars 2026  
> **Statut global** : Phase 2A ✅ — Phase 2B ✅ — Phase 3 en cours 🔄

---

## 📊 Vue d'ensemble du projet

```
PHASE 1  — Morning Brief PRO             ✅ TERMINÉE (8 mars 2026)
PHASE 2A — Scoring + Dashboard            ✅ TERMINÉE (12 mars 2026)
PHASE 2B — Workflow automatisé             ✅ TERMINÉE (15 mars 2026)
PHASE 3  — Agent d'analyse SMC             🔄 EN COURS (démarré 15 mars 2026)
PHASE 4  — Agent d'exécution IBKR          ⬜ À VENIR
```

**Coût actuel : 0€/mois** (tout en local, aucune API payante)

---

## ✅ Ce qui est fait

### Phase 1 — Morning Brief PRO
- Rapport 7 sections, calendrier macro auto, Reddit PRO v4, 10 flux RSS

### Phase 2A — Scoring + Dashboard (3 sprints)
- Score composite 0-100 (SMA200 + Volume + Reddit + News)
- Watchlist 22 tickers + aliases dans config YAML
- Alertes killzone 14h30-16h30 CET (volume/SMA200/mouvement/breaking news)
- Mode test killzone simulé
- Résumé post-market (gainers/losers)
- Indicateurs macro enrichis (Treasury yields, Gold, Oil)
- Dashboard React + serveur FastAPI

### Phase 2B — Workflow automatisé (3 sprints)
- Détecteur setups SMC (discount zone, SMA200 bounce, volume momentum)
- Position sizing automatique
- Journal de trading (formulaire, DB SQLite, clôture auto PnL/R:R)
- Suivi positions temps réel (PnL latent, barre stop→target, alertes)
- Equity curve, heatmap mensuelle, drawdown analysis
- Edge tracker (par ticker, setup type, régime marché)
- Workflow end-to-end validé ✅

### Phase 3 — Agent d'analyse SMC (en cours)
- Analyseur SMC algorithmique (mode DEMO, sans API) :
  - Structure de marché : BOS/CHoCH, swing highs/lows
  - Order Blocks : zone institutionnelle [low,open], displacement 1.5x, 3 niveaux mitigation
  - FVG : filtre bougie impulsive, partially_filled, distance_pct
  - Liquidity Map : BSL/SSL clustering
  - Discount/Premium/OTE (Fibonacci 62-79%)
  - Confluences (6 critères)
- Score unifié : croisement setup_detector × smc_analyzer (grades A+/A/B/C)
- Reddit radar à trouvailles :
  - r/buzztickr intégré comme source de découverte
  - Trouvailles hors watchlist avec badges source (Reddit/buzztickr/Double)
  - Boutons Analyser/Watchlist temporaire/TradingView
  - Blacklist Reddit : 200+ faux tickers filtrés
  - Cross-validation Reddit × News
  - Tendances 5 jours

### Dashboard — 10 onglets

| # | Onglet | Contenu |
|---|--------|---------|
| 1 | 📊 Vue d'ensemble | Macro + régime + verdict + Top 3 + indicateurs FRED + post-market + positions |
| 2 | 📈 Watchlist | 22 tickers scorés, barres SHAP, liens TradingView |
| 3 | 🔴 Reddit | Watchlist mentions + Trouvailles buzztickr (grille cartes) |
| 4 | 📰 News | News tickers + macro filtrées |
| 5 | ⚡ Alertes | Killzone live, breaking news, alertes positions, mode test |
| 6 | 🎯 Setups | Détecteur discount/SMA200/momentum, position sizing |
| 7 | 🧠 Analyse SMC | Analyse complète + Score Unifié + Scanner Top 5 |
| 8 | 📝 Journal | Formulaire saisie, positions ouvertes avec PnL live, historique |
| 9 | 📊 Performance | Equity curve, heatmap, drawdown, edge tracker |
| 10 | ❓ Guide | Tutoriel 8 sections intégré |

### Environnement technique
- Python + venv | Git + GitHub (2 postes : pro + perso)
- Claude Code dans VS Code
- FastAPI + uvicorn | React via CDN | SQLite
- ~20 fichiers Python, ~20 endpoints API
- Audit : imports OK, DB OK, endpoints OK

---

## 🔄 Ce qui reste à faire

### Phase 3 — Finalisation (à venir)

| # | Tâche | Priorité | Statut |
|---|-------|----------|--------|
| A | Corriger R:R minimum dans smc_analyzer (NVDA à 1.34 au lieu de 2.5) | Haute | ⬜ |
| B | Brancher Claude API (mode LIVE) quand prêt (~15€/mois) | Moyenne | ⬜ |
| C | Sentiment composite avancé (options flow via yfinance) | Basse | ⬜ |
| D | Métriques avancées (Sharpe, Sortino, Monte Carlo) | Basse | ⬜ |

### Critères Phase 3 → Phase 4
- [ ] 50+ trades enregistrés dans la DB
- [ ] Winrate > 50%, PF > 1.3
- [ ] Agent stable 2+ mois
- [ ] Analyses SMC pertinentes vs analyse manuelle

### Phase 4 — Agent d'exécution IBKR

| # | Tâche | Détail |
|---|-------|--------|
| 31 | Connexion IBKR API (ib_insync) | Paper trading d'abord |
| 32 | Bracket orders auto | Entry + Stop + Target |
| 33 | Validation humaine | Dashboard GO/SKIP |
| 34 | Kill switches | Max loss, max trades, exposure 3% |
| 35 | Logging complet | Audit trail |
| 36 | 2 mois paper obligatoires | Avant le réel |

**Prérequis NON NÉGOCIABLES :**
- 6+ mois de trading documenté
- Phase 3 stable 2+ mois
- WR > 55% sur 100+ trades, PF > 1.5
- Compréhension totale du code

---

## 💰 Budget

| Phase | Coût actuel | Coût prévu |
|-------|------------|------------|
| 1 → 2B | **0€** | 0€ |
| 3 (actuel, mode DEMO) | **0€** | 0€ |
| 3 (mode LIVE, Claude API) | — | ~15€/mois |
| 4 (IBKR) | — | ~30€/mois |

---

## 📈 Chronologie

```
8 mars   → Phase 1 terminée (Morning Brief PRO)
10 mars  → Phase 2A Sprint 1 (scoring + dashboard)
10 mars  → Phase 2A Sprint 2 (alertes killzone)
12 mars  → Phase 2A Sprint 3 (config YAML + post-market) → Phase 2A ✅
12 mars  → Phase 2B Sprint 4 (détecteur setups)
15 mars  → Phase 2B Sprint 5 (journal trading)
15 mars  → Phase 2B Sprint 6 (performance) → Phase 2B ✅
15 mars  → Phase 3 démarrée (analyseur SMC + score unifié)
16 mars  → OB/FVG améliorés + Guide utilisateur intégré
17 mars  → Reddit refonte + radar trouvailles buzztickr
```

---

## 🎯 Prochaine action concrète

**→ Corriger le R:R minimum dans smc_analyzer.py (forcer >= 2.5)**

Puis : accumuler des trades réels dans le journal, valider l'outil au quotidien, et décider quand passer en mode LIVE (Claude API).

---

*"L'agent amplifie ton edge existant, il ne le crée pas."*