# 🗺️ ROADMAP — Trading Agent SMC-AI

> **Dernière mise à jour** : 15 mars 2026  
> **Statut global** : Phase 2A ✅ — Phase 2B quasi terminée — Test workflow en cours

---

## État des lieux — Ce qui est fait

### ✅ Skill Trading Coach v7
- 26 fichiers de référence, 341K, 10/10 tests

### ✅ Phase 1 — Morning Brief PRO
- Rapport 7 sections, calendrier macro auto, Reddit PRO v4, 10 flux RSS

### ✅ Phase 2A — Morning Brief v2 (terminé — 12 mars 2026)

| Sprint | Contenu | Statut |
|--------|---------|--------|
| Sprint 1 | Score composite 0-100, SQLite, watchlist 22 tickers, dashboard React + FastAPI | ✅ |
| Sprint 2 | Alertes killzone 14h30-16h30 CET (volume/SMA200/mouvement/breaking news), mode test | ✅ |
| Sprint 3 | Config YAML externalisée, résumé post-market, liens TradingView | ✅ |

### ✅ Phase 2B — Workflow automatisé (en cours — 15 mars 2026)

| Sprint | Contenu | Statut |
|--------|---------|--------|
| Sprint 4 | Détecteur setups SMC (discount zone), position sizing auto | ✅ |
| Sprint 5 | Journal trading (formulaire, DB trades, clôture auto PnL/R:R) | ✅ |
| Sprint 6 | Performance (equity curve, heatmap mensuelle, drawdown, edge tracker) | ✅ |

**Améliorations intégrées :**
- Reddit Scanner amélioré : tendance 5j, filtrage penny stocks (209 valides/131 blacklistés), vérification yfinance, cross-validation Reddit×News, badges vérifié/confirmé
- Indicateurs macro enrichis : Treasury yields (13W/5Y/10Y/30Y), Gold, Oil
- Barres SHAP-style : contribution de chaque composante du score
- Key drivers dans le Top 3

### ✅ Dashboard — 8 onglets complets

| Onglet | Contenu |
|--------|---------|
| 📊 Vue d'ensemble | Macro + régime + verdict + Top 3 + indicateurs FRED + post-market |
| 📈 Watchlist | 22 tickers scorés, barres SHAP, liens TradingView |
| 🔴 Reddit | Tendances 5j, badges vérifié/confirmé, cross-validation |
| 📰 News | News tickers + macro filtrées |
| ⚡ Alertes | Killzone live, breaking news 30min, mode test |
| 🎯 Setups | Détecteur discount/SMA200/momentum, position sizing |
| 📝 Journal | Formulaire saisie, positions ouvertes, historique |
| 📊 Performance | Equity curve, heatmap, drawdown, edge tracker |

### ✅ Environnement technique
- Python + venv | Git + GitHub (2 postes : pro + perso)
- Claude Code dans VS Code
- FastAPI + uvicorn | React via CDN | SQLite
- 17 fichiers, 10 modules, 17 endpoints API
- Audit 100% vert

---

## Prochaines étapes — Finalisation Phase 2B

### En cours : Test workflow complet

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| A | Tester le workflow end-to-end | Scanner setups → choisir → enregistrer trade → suivre → clôturer → voir stats | 🔄 |
| B | Améliorer détecteur setups | Ajouter SMA200 bounce + volume momentum (pas que discount) | ⬜ |
| C | Suivi position temps réel | Pendant killzone : alerte si target/stop touché | ⬜ |

### Critères Phase 2B → Phase 3
- [ ] 50+ trades enregistrés dans la DB
- [ ] Winrate > 50%, PF > 1.3
- [ ] Workflow complet testé : brief → alerte → trade → suivi → clôture → stats
- [ ] Dashboard utilisé quotidiennement

---

## PHASE 3 — Agent d'analyse SMC (Mois 4-7)

> **Objectif** : le système analyse les charts et propose des setups structurés. Toi tu décides.

| # | Tâche | Détail |
|---|-------|--------|
| 24 | Claude API pour analyse | Données prix + contexte → analyse SMC formatée |
| 25 | Détection structure marché | BOS/CHoCH automatiques |
| 26 | Scoring SMC par setup | Confluence OB+FVG+discount+volume |
| 27 | Sentiment composite avancé | Reddit + news + options flow |
| 28 | Rapport analyse complet | Format SMC PRO v2 auto |
| 29 | Métriques avancées | Sharpe, Sortino, Monte Carlo |
| 30 | Dashboard enrichi | Onglets analyse SMC + performance avancée |

⚠️ Stack ajoutée (coûts à discuter) : Claude API ~10€ + VPS ~5€/mois

---

## PHASE 4 — Agent d'exécution IBKR (Mois 8-12)

| # | Tâche | Détail |
|---|-------|--------|
| 31 | Connexion IBKR API (ib_insync) | Paper trading d'abord |
| 32 | Bracket orders auto | Entry + Stop + Target |
| 33 | Validation humaine | Dashboard GO/SKIP |
| 34 | Kill switches | Max loss, max trades, exposure 3% |
| 35 | Logging complet | Audit trail |
| 36 | 2 mois paper obligatoires | Avant le réel |

---

## Budget

| Phase | Coût | Statut |
|-------|------|--------|
| 2A | 0€ | ✅ terminé |
| 2B | 0€ | 🔄 en cours |
| 3 | ~15€/mois (API + VPS) | ⬜ à discuter |
| 4 | ~30€/mois (+ IBKR data) | ⬜ |

---

*"L'agent amplifie ton edge existant, il ne le crée pas."*
