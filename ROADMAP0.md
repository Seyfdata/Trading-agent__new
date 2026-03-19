# 🗺️ ROADMAP — Trading Agent SMC-AI

> **Dernière mise à jour** : 10 mars 2026  
> **Statut global** : Phase 2A — Sprint 1 terminé ✅, Sprint 3 en cours

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
- Scanner watchlist : prix, variation D/W, distance SMA200, volume relatif
- Candidats setup : tickers prioritaires pour TradingView
- Reddit buzz : RedditScanner PRO v4 intégré (13 subreddits, time-decay scoring)
- News RSS filtrées : 10 sources, matching tickers + alias
- Environnement : Windows, VS Code, Claude Code, Git

### ✅ Sprint 1 Phase 2A — Scoring & Dashboard (terminé — 10 mars 2026)
- **Watchlist élargie à 22 tickers** : Mag7 + Semi + Cloud/Cyber/Chine
  - Ajouts : INTC, PLTR, SMCI, MU, ASML, TWLO, BABA, ZS, MRVL, CRM, SNOW, TSM
  - Aliases mis à jour dans config/settings.py
- **Module scoring.py** : score composite 0-100 par ticker
  - 4 composantes pondérées /25 : SMA200, Volume, Reddit, News
  - Score contexte marché : BULL/NEUTRAL/BEAR avec sizing recommandé
  - Fonction rank_tickers() : tri + Top 3
- **Base SQLite** (database/models.py) : historique des scores quotidiens
- **Pivot Telegram → Dashboard React** : cockpit web local
  - Serveur FastAPI (dashboard/api.py) avec 7 endpoints
  - Dashboard React 5 onglets (Vue d'ensemble, Watchlist, Reddit, News, Historique)
  - Bouton Rafraîchir : scan complet Reddit + News + Market en 1 clic
  - Dernière MAJ affichée dans le header
  - Lancement : `python launch_dashboard.py` → http://localhost:8000/dashboard
- **Telegram désactivé** (flag TELEGRAM_ENABLED=False)

### ✅ Environnement technique (opérationnel)
- Python + venv fonctionnel
- Git initialisé + GitHub connecté
- Claude Code dans VS Code opérationnel
- FastAPI + uvicorn installés
- RedditScanner PRO v4 préservé et wrappé

---

## Les 4 phases

```
PHASE 2A — Morning Brief v2          (4-6 semaines)    ← ON EST ICI
  Sprint 1 : Scoring & Dashboard     ✅ TERMINÉ
  Sprint 2 : Alertes intraday        ⬜ À FAIRE
  Sprint 3 : Fiabilisation & UX      🔄 EN COURS

PHASE 2B — Workflow automatisé       (6-8 semaines)
  Scan → Setup → Suivi de position, journal auto

PHASE 3  — Agent d'analyse SMC       (3-4 mois)
  Analyse de charts, scoring SMC, décision assistée

PHASE 4  — Agent d'exécution IBKR    (3-4 mois)
  Connexion broker, ordres validés, paper puis réel
```

---

## PHASE 2A — Morning Brief v2

### Sprint 1 — Scoring & Dashboard ✅ TERMINÉ

| # | Tâche | Statut |
|---|-------|--------|
| 1 | Score composite 0-100 par ticker (SMA200 + Volume + Reddit + News) | ✅ |
| 2 | Tri automatique + Top 3 du jour | ✅ |
| 3 | Score contexte marché BULL/NEUTRAL/BEAR + sizing | ✅ |
| 4 | Historique scores SQLite | ✅ |
| 4b | Watchlist élargie 22 tickers + aliases | ✅ |
| 4c | Dashboard React 5 onglets + FastAPI | ✅ |
| 4d | Bouton Rafraîchir scan complet | ✅ |
| 4e | Pivot Telegram → Dashboard | ✅ |

### Sprint 2 — Alertes intraday

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| 5 | Monitoring killzone 14h30-16h30 CET | Vérification prix toutes les 5 min | ⬜ |
| 6 | Alerte breakout volume | Ticker >2x volume moyen → alerte dashboard | ⬜ |
| 7 | Alerte approche zone clé | Prix approche SMA200 / support → alerte | ⬜ |
| 8 | Alerte news breaking | Polling RSS toutes les 15 min pendant killzone | ⬜ |

### Sprint 3 — Fiabilisation & UX 🔄 EN COURS

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| 9 | Gestion d'erreurs robuste | Retry auto, fallback, clean_for_json | ✅ partiel |
| 10 | Design dashboard amélioré | Liens TradingView, mini-charts, UX polish | ⬜ |
| 11 | Résumé post-market dans le dashboard | Moves importants du jour | ⬜ |
| 12 | Config YAML | Externaliser watchlist, seuils, horaires | ⬜ |

### Critères de passage 2A → 2B
- [ ] Score composite fiable (corrélation avec tes trades réels)
- [ ] Alertes killzone testées 2+ semaines
- [ ] Dashboard utilisé chaque matin
- [ ] Config externalisée

---

## PHASE 2B — Workflow scan → setup → suivi (Semaines 7-14)

> **Objectif** : couvrir le cycle complet du trade.

| # | Tâche | Détail | Statut |
|---|-------|--------|--------|
| 13 | Détection discount zone | Ticker en discount < 50% range HTF | ⬜ |
| 14 | Détection OB non mitigé | Zones d'intérêt via données de prix | ⬜ |
| 15 | Notification setup candidat | Alerte dashboard avec R:R estimé | ⬜ |
| 16 | Position sizing auto | Calcul nb actions + risque | ⬜ |
| 17 | DB trades SQLite | Tables trades, daily_scans | ⬜ |
| 18 | Saisie trade via dashboard | Formulaire entry/stop/target | ⬜ |
| 19 | Suivi de position | Alertes target/stop/invalidation | ⬜ |
| 20 | Clôture auto | Calcul R réalisé, MAJ DB | ⬜ |
| 21 | Métriques de base | WR, PF, Expectancy, Max DD | ⬜ |
| 22 | Rapport hebdo dashboard | Onglet Performance | ⬜ |
| 23 | Edge tracker | Perf par ticker/jour/régime VIX | ⬜ |

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

## Budget

| Phase | Essentiel | Total |
|-------|-----------|-------|
| 2A (actuel) | 0€ | 0-15€/mois |
| 2B | ~5€ Claude API | 5-25€/mois |
| 3 | ~15€ (API + VPS) | 15-45€/mois |
| 4 | ~30€ (+ IBKR data) | 30-60€/mois |

---

## Prochaine action

**→ Sprint 3 tâche #10 : améliorer le dashboard — liens TradingView, UX, design.**

---

*"L'agent amplifie ton edge existant, il ne le crée pas."*
