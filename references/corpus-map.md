# Cartographie du corpus — livre → notebook → usage

> Curation opinionée pour le projet SMC-AI (LONG only, SMC, swing actions US, validation humaine).
> Objectif : ne charger chaque notebook qu'avec des sources pertinentes. Une source hors-sujet
> dilue la réponse de NotebookLM. La pertinence se juge par rapport à CE projet, pas dans l'absolu.

---

## NB-VALIDATION — *priorité absolue*

**But** : déterminer si le système a un edge réel et comment le prouver/réfuter. C'est le banc
d'étalonnage. Sans ce notebook, tout le reste est de la décoration.

| Livre | Pourquoi |
|-------|----------|
| **Evidence-Based Technical Analysis — Aronson** | LE livre central. Démolition statistique de l'AT subjective + méthode pour tester une règle scientifiquement (data-mining bias, tests d'hypothèse). Tout SMC algorithmique doit passer par là. |
| **The Evaluation and Optimization of Trading Strategies — Pardo** | Référence du walk-forward analysis et de l'out-of-sample. Comment optimiser sans sur-optimiser. |
| **Advances in Financial Machine Learning — López de Prado** | Purged/combinatorial cross-validation, deflated Sharpe ratio, pourquoi le backtest naïf ment. Dense mais décisif. |
| **Building Winning Algorithmic Trading Systems — Davey** | Vécu retail sur l'overfitting et la robustesse. Plus accessible que LdP, complémentaire. |

Sources à cocher selon la question : Aronson seul pour "comment tester une règle" ; Pardo seul pour
"comment structurer mon walk-forward" ; LdP pour la rigueur statistique avancée.

---

## NB-SMC-FORMALIZATION

**But** : transformer BOS, CHoCH, Order Block, FVG, liquidity sweep, displacement en règles
déterministes et backtestables. Ancrer le SMC (corpus retail, peu rigoureux) dans la TA et la
microstructure les plus sérieuses pour distinguer ce qui correspond à une réalité de marché du folklore.

| Livre | Pourquoi |
|-------|----------|
| **The Art and Science of Technical Analysis — Grimes** | La TA la plus rigoureuse qui existe. Formalise structure, momentum, pullbacks — le plus proche d'un SMC scientifique. |
| **Trading Systems and Methods — Kaufman** | Encyclopédie. Définitions opérationnelles de quasi tout indicateur/structure. Référence à piocher. |
| **Trading and Exchanges — Harris** | Microstructure : ce que "liquidité" veut *vraiment* dire (carnet d'ordres, market makers). Teste si tes "liquidity grabs" SMC ont un sens. |
| **Market Microstructure Theory — O'Hara** | Approfondit Harris côté académique. À cocher seulement pour une question microstructure pointue. |
| *Cycle Analytics for Traders — Ehlers* | *Optionnel* : maths du filtrage/swing detection si tu veux des swing highs/lows propres. |

---

## NB-SCORING-RISK

**But** : un scoring multi-facteurs SANS redondance + un moteur de risk professionnel. Attaque
frontale du "score cosmétique" (momentum compté 3×).

| Livre | Pourquoi |
|-------|----------|
| **Causal Factor Investing — López de Prado** | Court et chirurgical. Différence corrélation/causalité, indépendance des facteurs. Exactement ton problème de double-comptage. |
| **Systematic Trading — Carver** | Conception de systèmes simples et robustes, sizing par volatilité, combinaison de signaux. Très applicable à ton échelle. |
| **Leveraged Trading — Carver** | Version plus accessible de Systematic Trading, focalisée risk et sizing. |
| **The Mathematics of Money Management — Vince** | Sizing, gestion du capital, géométrie du risque. À doser (parfois agressif — Kelly). |
| **Active Portfolio Management — Grinold & Kahn** | Fondamental Law (IC × breadth), comment penser l'information d'un signal. Avancé. |
| *Finding Alphas — Tulchinsky* | *Optionnel* : construction et test de facteurs (alphas), éviter l'illusion de signal. |
| *Quantitative Momentum — Gray* | *Optionnel* : si tu ajoutes un facteur momentum cross-sectional, voilà la version rigoureuse. |

---

## NB-ADVERSARY — *le plus rentable*

**But** : un seul rôle, détruire le système. Biais cognitifs, hasard, fragilité, overfitting
psychologique. NotebookLM y est mis en posture de risk officer hostile.

| Livre | Pourquoi |
|-------|----------|
| **Fooled by Randomness — Taleb** | La performance est-elle de la compétence ou de la chance ? Indispensable pour un trader qui valide à la main. |
| **Thinking, Fast and Slow — Kahneman** | Tous les biais qui pourrissent la décision discrétionnaire (ancrage, confirmation, disponibilité). |
| **Thinking in Bets — Duke** | Décider sous incertitude, séparer qualité de la décision et qualité du résultat (resulting). |
| **Evidence-Based TA — Aronson** | (aussi ici) data-mining bias, illusions de l'AT. |
| **A Random Walk Down Wall Street — Malkiel** | Contre-poison : "le marché est efficient, ton edge est une illusion — prouve le contraire". Le seul livre value/passif à garder, et uniquement pour ça. |
| *Inside the Black Box — Narang* | *Optionnel* : ce à quoi ressemble un vrai système quant pro, pour mesurer l'écart avec le tien. |

---

## NB-IMPLEMENTATION *(optionnel)*

**But** : comprendre les *patterns* d'implémentation Python. La logique ici → le code chez Claude Code.

| Livre | Pourquoi |
|-------|----------|
| **Python for Algorithmic Trading — Hilpisch** | Patterns concrets data/backtest en Python. |
| **Python for Finance — Hilpisch** | Plus large (pandas, numpy, viz). Base solide. |
| **Trading Evolved — Clenow** | Backtests réalistes (zipline), mentalité système. Pragmatique. |
| **Machine Learning for Algorithmic Trading — Jansen** | Quand tu auras tes 1000+ snapshots propres et voudras du ML supervisé. Pas avant. |
| *The Algorithmic Trading Cookbook — Strimpel* | *Optionnel* : recettes ponctuelles. |

---

## NB-ARCHITECTURE *(optionnel, phase refactor)*

| Livre | Pourquoi |
|-------|----------|
| **Refactoring — Fowler** | Découper proprement api.py / smc_analyzer.py sans tout casser. Directement utile. |
| **Clean Architecture — Martin** | Frontières entre couches (data / logique / API). Garde-fou anti-monolithe. |
| **Release It! — Nygard** | Stabilité, timeouts, circuit breakers — pertinent pour les appels yfinance instables. |
| *Designing Data-Intensive Applications — Kleppmann* | *Optionnel* : excellent mais surdimensionné pour une app SQLite locale. Survol seulement. |

---

## ⛔ Le bruit — NE PAS charger pour ce projet

Ces livres sont hors-sujet pour un système SMC LONG-only swing actions US. Les inclure dilue les
réponses. À garder dans NotebookLM si tu veux, mais dans des notebooks séparés "culture", pas dans
les notebooks de travail.

- **Options / dérivés / calcul stochastique** : Hull (*Options, Futures & Other Derivatives*),
  Natenberg (*Option Volatility & Pricing*), Wilmott, Shreve (*Stochastic Calculus*),
  Stefanica (*Primer Financial Engineering*). → Tu ne trades pas d'options. Zéro usage tant que ça dure.
- **Value / fondamental / passif** : Graham & Dodd (*Security Analysis*), Graham (*Intelligent
  Investor*), Lynch (*One Up on Wall Street*), Bogle (*Common Sense Investing*), Tracy & Ittelson
  (états financiers). → Approche opposée à la tienne. (Garder *Malkiel* seul, dans NB-ADVERSARY.)
- **Culture / histoire / essais** : Lefèvre (*Reminiscences*), Lewis (*Flash Boys*),
  Hazlitt (*Economics in One Lesson*). → Plaisants, zéro méthode exploitable.
- **Économétrie lourde** : Hamilton, Tsay (*Time Series Analysis*). → Surdimensionné pour ton stade ;
  à ressortir seulement si un jour tu fais de la cointégration/stationnarité sérieuse.
- **ML théorique avancé** : Dixon/Halperin/Bilokon (*ML in Finance: Theory to Practice*),
  Machine Learning for Asset Managers (LdP — utile mais dense, à réserver à plus tard). → Pas avant
  d'avoir un dataset propre.
- **Exécution institutionnelle** : Kissell (*Science of Algo Trading*, *Algo Trading Methods*),
  Johnson (*Algorithmic Trading and DMA* — pas dans ta liste mais même catégorie). → Pour des desks
  institutionnels, pas un compte cash retail.
- **Plateforme spécifique** : Scarpino (*Hands-On AI Trading w/ QuantConnect/AWS*). → Pas ta stack.
- **Facteurs value** : Gray (*Quantitative Value*), Clenow (*Stocks on the Move*). → (*Quantitative
  Momentum* peut servir si tu ajoutes un facteur momentum ; le reste, non.)

---

## Règle d'or de curation

Pour répondre à "quel livre / quelles sources", toujours : (1) identifier le notebook, (2) cocher
le **minimum** de sources qui couvrent la question, (3) si la question touche plusieurs domaines
(ex : "agent IA appliqué à mon scoring SMC"), faire le pont entre 2-3 livres ciblés, pas balancer
tout le notebook. Source serrée = réponse nette.
