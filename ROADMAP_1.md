# 🗺️ ROADMAP — Trading Agent SMC-AI

> **Dernière mise à jour** : 12 mars 2026  
> **Statut global** : Phase 2A terminée ✅ — Phase 2B en cours

---

## État des lieux — Ce qui est fait

### ✅ Skill Trading Coach v7 (terminé)
- 26 fichiers de référence, 341K, 10/10 tests
- Couverture complète : SMC, Pine Script, IBKR, scraping, sentiment, performance, mise en prod
- Gamification, parcours 12 semaines, backtest

### ✅ Phase 1 — Morning Brief PRO (terminé)
- Rapport 7 sections fonctionnel
- Calendrier macro avec détection auto (NFP, CPI, Jobless Claims)
- Contexte marché : SPY, QQQ, VIX, DXY, US10Y via yfinance
- Reddit buzz : RedditScanner PRO v4 intégré (13 subreddits, time-decay scoring)
- News RSS filtrées : 10 sources, matching tickers + alias

### ✅ Phase 2A — Morning Brief v2 (terminé — 12 mars 2026)

**Sprint 1 — Scoring & Dashboard ✅**
| # | Tâche | Statut |
|---|-------|--------|
| 1 | Score composite 0-100 par ticker (SMA200 + Volume + Reddit + News) | ✅ |
| 2 | Tri automatique + Top 3 du jour | ✅ |
| 3 | Score contexte marché BULL/NEUTRAL/BEAR + sizing | ✅ |
| 4 | Historique scores SQLite | ✅ |
| 4b | Watchlist élargie 22 tickers + aliases | ✅ |
| 4c | Dashboard React 6 onglets + FastAPI 7 endpoints | ✅ |
| 4d | Bouton Rafraîchir scan complet | ✅ |
| 4e | Pivot Telegram → Dashboard local | ✅ |

**Sprint 2 — Alertes killzone ✅**
| # | Tâche | Statut |
|---|-------|--------|
| 5 | Monitoring killzone 14h30-16h30 CET (auto-refresh 5min) | ✅ |
| 6 | Alerte breakout volume (>2x moyenne) | ✅ |
| 7 | Alerte approche SMA200 (<1.5%) | ✅ |
| 8 | Alerte mouvement fort (>3% intraday) | ✅ |
| 8b | Breaking News 30min dans onglet Alertes | ✅ |
| 8c | Mode test killzone simulé | ✅ |

**Sprint 3 — Fiabilisation & UX ✅**
| # | Tâche | Statut |
|---|-------|--------|
| 9 | Gestion d'erreurs robuste (clean_for_json, try/except) | ✅ |
| 10 | Design amélioré : liens TradingView, barres de score, badges volume | ✅ |
| 11 | Résumé post-market (top gainers/losers, résumé marché, compteur alertes) | ✅ |
| 12 | Config YAML externalisée (watchlist, seuils, killzone, scoring) | ✅ |

### ✅ Environnement technique
- Python + venv | Git + GitHub | Claude Code dans VS Code
- FastAPI + uvicorn | React via CDN | SQLite
- RedditScanner PRO v4 wrappé | 10 flux RSS
- Lancement : `python launch_dashboard.py` → http://localhost:8000/dashboard

---

## Les phases

```
PHASE 2A — Morning Brief v2          ✅ TERMINÉE
PHASE 2B — Workflow automatisé       ← ON EST ICI
PHASE 3  — Agent d'analyse SMC       ⬜
PHASE 4  — Agent d'exécution IBKR    ⬜
```

---

## PHASE 2B — Workflow scan → setup → suivi

> **Objectif** : couvrir le cycle complet du trade, de la détection au suivi post-entrée. Le dashboard devient un vrai outil de performance.

### Sprint 4 — Détection de setups (Sem. 7-9)

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| 13 | Détection discount zone | Ticker en discount < 50% du range 20j | ⬜ |
| 14 | Détection OB non mitigé | Zones d'intérêt via données de prix | ⬜ |
| 15 | Notification setup candidat | Alerte dashboard avec R:R estimé | ⬜ |
| 16 | Calcul position sizing auto | Nb actions + risque calculé | ⬜ |

### Sprint 5 — Journal de trading automatisé (Sem. 10-12)

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| 17 | Base de données trades (SQLite) | Tables : trades, setups, positions | ⬜ |
| 18 | Formulaire saisie trade (dashboard) | Enregistrer entry/stop/target | ⬜ |
| 19 | Suivi de position en temps réel | Alertes target/stop/invalidation | ⬜ |
| 20 | Clôture et calcul automatique | R réalisé, PnL, MAJ DB | ⬜ |

### Sprint 6 — Métriques & reporting (Sem. 13-14)

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| 21 | Calcul métriques de base | WR, PF, Expectancy, Max DD | ⬜ |
| 22 | Onglet Performance dashboard | Bilan semaine/mois, courbe equity | ⬜ |
| 23 | Edge tracker | Perf par ticker/jour/régime VIX | ⬜ |

### Critères de passage 2B → Phase 3
- [ ] 50+ trades enregistrés dans la DB
- [ ] Winrate > 50%, PF > 1.3
- [ ] Workflow complet : brief → alerte → trade → suivi → clôture → stats
- [ ] Routines morning + killzone + post-market opérationnelles

---

## PHASE 3 — Agent d'analyse SMC (Mois 4-7)

| # | Tâche | Détail |
|---|-------|--------|
| 24 | Claude API pour analyse | Données prix + contexte → analyse SMC formatée |
| 25 | Détection structure marché | BOS/CHoCH automatiques |
| 26 | Scoring SMC par setup | Confluence OB+FVG+discount+volume |
| 27 | Sentiment composite avancé | Reddit + news + options flow |
| 28 | Rapport analyse complet | Format SMC PRO v2 auto |
| 29 | Métriques avancées | Sharpe, Sortino, Monte Carlo |
| 30 | Dashboard enrichi | Onglets analyse SMC + performance |

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

## Prochaine action concrète

**→ Sprint 4 tâche #13 : détection discount zone + position sizing.**

---

*"L'agent amplifie ton edge existant, il ne le crée pas."*
