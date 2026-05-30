# 🗺️ ROADMAP — Trading Agent SMC-AI

> **Dernière mise à jour** : 24 mai 2026
> **Statut global** : Pivot stratégique acté ✅ — Cockpit de discipline construit 🔄 — Premiers paper trades à venir ⬜

---

## ⚠️ Lis ceci d'abord — le projet a changé de nature

Les versions précédentes de cette roadmap visaient un **agent d'analyse prédictive** (détecter
quoi acheter et quand, via scoring SMC) puis une **exécution automatique IBKR**. Cette direction
a été **testée puis abandonnée sur la base de données réelles**, pas d'une intuition. Ce document
remplace l'ancien. Ne te fie plus aux roadmaps antérieures.

---

## 🔬 Le pivot — ce qui a été testé, et pourquoi on a changé de cap

On a construit un backtester honnête (frictions réelles, exécution à l'open suivant, séparation
out-of-sample, Deflated Sharpe, test de permutation par entrées aléatoires) et on y a fait passer
les 3 stratégies mécaniques existantes (discount zone, SMA200 bounce, volume momentum), sur les
22 tickers, 10 ans d'historique.

**Résultat, sans ambiguïté :**

| Constat | Mesure |
|---------|--------|
| Aucun edge de timing hors échantillon | Deflated Sharpe au plancher (−0.5) sur les 3 stratégies |
| Le buy-and-hold passif domine massivement | Stratégies battent le B&H sur 2 tickers / 22 (9 %) |
| Le timing n'est pas distinct du hasard | p-value du test de permutation : 0–6 % de tickers significatifs |
| Net de frictions, ça perd | DISCOUNT_ZONE : profit factor < 1.0 en OOS |

**Conclusion** : sur cet univers (mégacaps tech US survivantes, régime haussier 2022-2025), le
timing SMC mécanique n'a **pas** d'edge démontrable. Choisir ses dates d'entrée au hasard fait
aussi bien. Ce n'est pas un échec — c'est la réfutation propre qui évite des mois de développement
sur une hypothèse fausse.

**Ce qu'on en tire** : le projet abandonne la promesse « l'outil prédit » (non prouvée) et assume
la promesse « l'outil discipline » (mesurable, défendable). `smc_analyzer` et `unified_scorer`
restent dans le code mais sont **rétrogradés** : lecture descriptive pour l'œil du trader, jamais
décisionnels. Cadre métrologue : un instrument qui fait respecter une tolérance (R:R, risque,
exposition) est *fit for purpose* sans rien prédire — comme un calibre go/no-go.

---

## ✅ Ce qui a été construit (le cockpit de discipline)

| Module | Rôle | Statut |
|--------|------|--------|
| Backtester honnête (`analysis/honest_backtester.py`) | Juge de paix : frictions, OOS, DSR, permutation, B&H. Survivorship NON corrigé (assumé, borne haute) | ✅ |
| **Module 1 — Risk engine** (`analysis/risk_engine.py`) | Source unique du sizing. Refuse toute config hors-règles (R:R < 2.5, risque > 1 %, risk-heat > 3 %, notional > capital en compte cash) | ✅ |
| **Module 2 — Gate pré-trade** (`analysis/pretrade_gate.py`) | Verdict unique GO / GO-WARN / NO-GO agrégeant risk + régime + killzone + jour de news + max 2 trades | ✅ |
| **Module 3a — Journal disciplinaire (backend)** | 7 champs Kahneman/Duke, verdict gate + override loggés, matrice resulting (process × résultat) anti-resulting | ✅ |
| **Module 3b — Journal disciplinaire (UI)** | Champs dans le formulaire, gate affiché en live, panneau discipline | 🔄 à vérifier (4 tests + parité des clés POST/colonnes) |

**Fil rouge** : chaque trade logge le respect/violation de chaque règle + des champs comportementaux.
Au bout de 20-40 trades, le cockpit ne dit plus « tu surtrades peut-être » — il montre, chiffres à
l'appui, laquelle de tes fuites est réelle.

---

## 📊 État technique

- Stack inchangée : Python/FastAPI, React 18 CDN, SQLite, yfinance, Pine Script v5 (descriptif).
- Coût : **0 €/mois**.
- Pine Script `smc_all_in_one.pine` : overlay **descriptif** sur TradingView, pas un générateur de
  signaux. À ne pas re-documenter comme un système de trading.

---

## ⚠️ Ce qui n'est PAS prouvé / risques ouverts (honnêteté métrologue)

- **Edge prédictif** : réfuté. Ne pas y revenir sans une hypothèse *pré-enregistrée* et un test
  honnête. Reformuler une règle après avoir vu un OOS échouer = data-snooping interdit.
- **Survivorship bias** : non corrigé (yfinance ne fournit pas les titres délistés). Tout backtest
  reste une borne haute optimiste.
- **Risque de gap overnight** : un stop à 1 % ne garantit pas une perte de 1 % ; un gap baissier
  à l'ouverture peut dépasser le stop. Tracé dans le journal (`held_overnight`), à surveiller.
- **Le trader, c'est toi** : la discipline mesurée vaut ce que vaut l'honnêteté de ta saisie.

---

## 🎯 Prochaine action concrète — et elle n'est pas du code

1. **Vérifier le Module 3b** : les 4 tests du bloc TESTE + la parité exacte des clés POST avec les
   colonnes SQLite (`thesis` vs `these`, `initial_stop_violated` vs `stop_violated`, etc.).
2. **10 à 15 paper trades sur IBKR**, passés à travers le cockpit, journal rempli honnêtement.
   Règle de la série : un override d'un NO-GO est permis (l'humain décide) mais **jamais sans
   écrire pourquoi** dans le champ thèse.
3. **Ramener `GET /api/discipline/report`** : première conversation du projet basée sur des données
   réelles de discipline, pas sur des suppositions.

**Différé jusqu'à après la première série de trades** : guide utilisateur complet, graphiques du
panneau discipline (à concevoir contre des données réelles), nettoyage visuel « descriptif/non
décisionnel » de l'onglet SMC.

---

## 🧭 Phases — version révisée

```
PHASE 1-2B  — Morning brief, scoring, dashboard, journal de base   ✅ (conservés)
PIVOT       — Réfutation de l'edge prédictif (backtester honnête)   ✅
PHASE D     — Cockpit de discipline (risk engine, gate, journal)    🔄 (3b à vérifier)
PHASE E     — Première série de paper trades + lecture du report     ⬜ ← TU ES ICI
PHASE F     — Itérations guidées PAR LES DONNÉES de discipline       ⬜
```

L'ancienne « Phase 4 — exécution automatique IBKR » est **retirée** comme objectif. L'humain décide
et exécute. L'outil mesure et discipline.

---

*"L'outil ne prédit pas le marché. Il t'empêche de te saboter. C'est moins sexy, et c'est ce que
les données soutiennent. Le trading comporte un risque de perte en capital."*