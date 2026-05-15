# 🗺️ ROADMAP — Trading Agent SMC-AI

> **Dernière mise à jour** : 21 mars 2026  
> **Statut global** : Phases 1-3 ✅ — CONSO ✅ — Nouvelles features en cours

---

## Vue d'ensemble

```
PHASE 1   Morning Brief PRO                    ✅ TERMINÉE
PHASE 2A  Scoring + Dashboard React             ✅ TERMINÉE
PHASE 2B  Workflow complet (setups→journal→perf) ✅ TERMINÉE
PHASE 3   Agent analyse SMC (mode DEMO)          ✅ 100%
──────────────────────────────────────────────────────────
CONSO     Consolidation & fiabilisation          ✅ TERMINÉE
──────────────────────────────────────────────────────────
PHASE 4   Connexion IBKR API                     ⬜ À VENIR
```

**Coût actuel : 0€/mois**

---

## Ce qui est FAIT et FONCTIONNE

### Dashboard — 11 onglets
| # | Onglet | Statut |
|---|--------|--------|
| 1 | Vue d'ensemble (macro, régime, verdict, Top 3, positions) | ✅ |
| 2 | Coach (copilote débutant, stepper 5 étapes, GO/NO GO) | ✅ |
| 3 | Watchlist (22 tickers scorés 0-100, barres SHAP) | ✅ |
| 4 | Reddit (mentions watchlist + trouvailles buzztickr) | ⚠️ À FIXER |
| 5 | News (10 flux RSS filtrés par ticker/alias) | ✅ |
| 6 | Alertes (killzone live, positions, breaking news, mode test) | ✅ |
| 7 | Setups (discount/SMA200/momentum, position sizing) | ✅ |
| 8 | Analyse SMC (BOS/CHoCH, OB, FVG, score unifié, options flow) | ⚠️ TROP COMPLEXE |
| 9 | Journal (formulaire, positions PnL live, historique) | ✅ |
| 10 | Performance (equity curve, heatmap, drawdown, Sharpe, Monte Carlo, backtest) | ✅ |
| 11 | Guide (12 sections FR + EN, glossaire, routine) | ✅ |

### Backend — ~20 endpoints API
- FastAPI + uvicorn, SQLite, yfinance, Reddit JSON public, 10 RSS
- Scoring, setup detection, SMC analysis, options flow, backtest
- Journal trades avec clôture auto (PnL, R:R)
- Config YAML externalisée

### TradingView — Pine Script
- Indicateur all-in-one (BOS/CHoCH, OB, FVG, SMA, signaux BUY/SELL, trail stop)
- Stratégie backtest séparée
- Mode simple/expert

### Environnement
- Windows, VS Code, Claude Code, Git + GitHub (2 postes)
- Skills custom : trading-smc, react-dashboard, pinescript-v5
- CLAUDE.md + GUIDE_CLAUDE_CODE.md + METHODOLOGIE_TRAVAIL.md

---

## ⚠️ CE QUI NE MARCHE PAS BIEN — À FIXER

### Priorité 1 — Reddit cassé
- MRVL est le seul ticker affiché depuis des jours
- 21/22 tickers à 0 mentions = impression que rien ne fonctionne
- Le wrapper Reddit lit un vieux CSV au lieu de scraper en direct
- **FIX** : créer scan_reddit_direct() qui scrape le JSON public à chaque refresh

### Priorité 2 — Onglets silotés
- Les trouvailles Reddit ne sont pas exploitables dans Setups et Analyse SMC
- Impossible de taper un ticker libre dans l'Analyse SMC
- **FIX** : ajouter input ticker libre + navigation croisée entre onglets

### Priorité 3 — Analyse SMC trop complexe
- Trop de sections techniques pour un débutant
- Pas de mode simple par défaut
- **FIX** : toggle Simple/Expert, mode simple par défaut

---

## PHASE CONSOLIDATION — Plan d'action

### Sprint CONSO-1 : Fiabiliser Reddit (1 session)
| Tâche | Détail |
|-------|--------|
| Créer scan_reddit_direct() | Scraper 7 subreddits en JSON public, plus de CSV |
| Fusionner avec buzztickr | scan_reddit_direct() + scan_buzztickers() |
| Masquer tickers à 0 mentions | Afficher "X/22 mentionnés" + toggle "Voir tous" |
| Tester | Le refresh doit montrer des données fraîches |

### Sprint CONSO-2 : Connecter les onglets (1 session)
| Tâche | Détail |
|-------|--------|
| Input ticker libre | Taper n'importe quel ticker dans Setups et Analyse SMC |
| Boutons navigation | Reddit → Analyse SMC en 1 clic |
| Trouvailles dans Setups | Inclure les tickers temporaires dans le scan |

### Sprint CONSO-3 : Simplifier l'UX (1 session)
| Tâche | Détail |
|-------|--------|
| Mode Simple/Expert | Toggle dans Analyse SMC, simple par défaut |
| Config TradingView | Bouton qui génère les niveaux à copier |
| Design aéré | Espacement, typographie, ombres |

### Sprint CONSO-4 : Stabiliser et documenter (1 session)
| Tâche | Détail |
|-------|--------|
| Audit complet | Tous les imports, endpoints, div balance |
| Mettre à jour le Guide | Sections Coach, Reddit, SMC |
| Push final | Version stable, documentée |

### Critères de fin de consolidation
- [x] Reddit montre des données fraîches à chaque refresh
- [x] Un ticker trouvaille peut être analysé en 2 clics
- [x] L'analyse SMC est lisible en mode simple
- [x] Le dashboard tourne sans erreur pendant 1 semaine
- [x] Le dashboard tourne sans erreur

---


## SPRINT NOUVELLES FEATURES — Mai 2026

### Feature NF-1 : Proposition du Jour (OverviewTab) ✅
| Tâche | Statut |
|-------|--------|
| Endpoint /api/proposals avec scoring unifié | ✅ |
| Carte "Proposition du Jour" en haut de la Vue d'ensemble | ✅ |
| Navigation directe vers onglet Propositions | ✅ |
| Position sizing automatique (capital 10 000 $) | ✅ |

### Feature NF-2 : Prochaine feature
- À définir selon priorités

---

## APRÈS LA CONSOLIDATION

### Phase 3 finale — Claude API (~15€/mois, quand prêt)
- Brancher Claude API pour des analyses SMC plus fines
- Le mode DEMO algorithmique reste disponible comme fallback

### Phase 4 — IBKR API (disponible dès que tu es prêt)
- Connexion broker, bracket orders, validation humaine
- Paper trading recommandé avant le réel

---

## Budget

| Phase | Coût |
|-------|------|
| Actuellement | **0€/mois** |
| Après Claude API | ~15€/mois |
| Après IBKR | ~30€/mois |

---

*"Consolide avant d'ajouter. Un outil fiable bat un outil riche."*
