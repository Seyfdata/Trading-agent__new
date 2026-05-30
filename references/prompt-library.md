# Bibliothèque de prompts NotebookLM — projet SMC-AI

> Chaque template indique : l'objectif, le notebook, les sources à cocher, le prompt à coller,
> et comment exploiter la sortie. Coller dans le bloc de chat NotebookLM après avoir coché les
> bonnes sources. Toujours adapter le bloc CONTEXTE aux règles réelles du projet.

Bloc CONTEXTE à mettre en tête de presque tous les prompts :
```
CONTEXTE : système de trading semi-automatique. LONG only, compte cash, swing actions US.
Données OHLCV daily + intraday via yfinance. R:R minimum 1:2.5, risque 0.5-1%/trade, exposition
max 3%, killzone 14h30-16h30 CET, pas de trade les jours FOMC/NFP/CPI. L'IA propose, l'humain
valide et exécute. Backtestable obligatoire, sans repaint ni look-ahead bias.
```

---

## 1. Formalisation d'un concept SMC

**Notebook** : NB-SMC-FORMALIZATION · **Sources** : Grimes + Kaufman (+ Harris si "liquidité")

```
[CONTEXTE]

Transforme le concept SMC suivant en logique algorithmique stricte et testable : [BOS / CHoCH /
Order Block / Fair Value Gap / liquidity sweep / displacement].

Contraintes : aucune interprétation visuelle subjective, déterministe, compatible OHLCV pandas,
confirmation à la clôture obligatoire, pas de repaint, pas de look-ahead bias.

Donne, en t'appuyant sur les sources (avec citations) :
1. définition mathématique précise
2. conditions d'invalidation
3. pseudo-code logique (PAS de code Python, juste la logique)
4. risques de faux signaux
5. filtres de robustesse possibles (ATR, volume, structure)
6. ce que les sources confirment vs ce qui relève du folklore SMC non étayé
```
**Exploitation** : la sortie devient une spec → Claude traduit en prompt Claude Code pour créer
le module (ex : `smc/bos_choch.py`) avec tests.

---

## 2. Critique du scoring (redondance de facteurs)

**Notebook** : NB-SCORING-RISK · **Sources** : López de Prado (Causal Factor Investing) + Grinold & Kahn

```
[CONTEXTE]

Mon scoring composite 0-100 mélange : SMA200, volume, momentum, sentiment Reddit, news, et signaux
SMC (structure, OB, FVG).

En t'appuyant sur les sources (citations) :
1. quels signaux sont probablement corrélés / mesurent la même information sous-jacente
2. où il y a double-comptage (ex : plusieurs proxys de momentum)
3. quels facteurs sont réellement indépendants
4. les biais statistiques de cette construction
5. propose une hiérarchie context / setup / confirmation
6. propose une méthode de pondération robuste calibrable SANS sur-optimisation
```
**Exploitation** : refonte de `analysis/scoring.py` et `unified_scorer.py` — supprimer les facteurs
redondants avant d'en ajouter.

---

## 3. Conception du moteur de risk

**Notebook** : NB-SCORING-RISK · **Sources** : Carver (Systematic + Leveraged) + Vince

```
[CONTEXTE]

Conçois un moteur de risk management pour ce système.

Objectif, en t'appuyant sur les sources (citations) :
1. logique de position sizing (fixe vs volatilité — recommande et justifie)
2. gestion de la corrélation entre positions ouvertes (exposition 3% max)
3. réduction de taille en marché instable (VIX élevé, régime BEAR)
4. gestion des drawdowns (réduction progressive)
5. hard stops globaux / kill switch (max loss jour, max trades jour)
6. métriques à journaliser pour auditer le risk a posteriori
7. erreurs classiques de risk des systèmes quant retail
Donne l'architecture logique d'un module risk (responsabilités), PAS le code.
```
**Exploitation** : spec pour un module `risk/` chez Claude Code.

---

## 4. Méthode de validation (le prompt de départ recommandé)

**Notebook** : NB-VALIDATION · **Sources** : Aronson + Pardo + López de Prado (Advances)

```
[CONTEXTE]

Je veux savoir si mon système a un edge réel AVANT d'investir plus de développement.

En t'appuyant sur les sources (citations), réponds sans complaisance :
1. l'analyse technique de type Smart Money Concepts a-t-elle un edge empiriquement démontrable
   sur actions US en daily/intraday, ou est-ce surtout de l'illusion rétrospective ? Que disent
   réellement les sources ?
2. quelle est la procédure minimale et honnête pour tester MON système : in-sample / out-of-sample,
   walk-forward, taille d'échantillon nécessaire, déflation de Sharpe, contrôle du data-mining bias ?
3. quels pièges méthodologiques détruisent silencieusement un backtest (look-ahead, survivorship,
   coûts/slippage, p-hacking) et comment les neutraliser ?
4. combien de trades / quelle durée avant que mes statistiques (winrate, profit factor) soient
   statistiquement significatives et pas du bruit ?
5. un protocole de test concret, étape par étape, applicable à mon système avec ~0 trade validé.
```
**Exploitation** : définit la Phase de validation. Devient le cahier des charges du backtester et
du snapshot logging. C'est la première chose à faire — voir le message d'accompagnement.

---

## 5. Review adverse (détruire le système)

**Notebook** : NB-ADVERSARY · **Sources** : Taleb + Aronson + López de Prado

```
[CONTEXTE]

Tu es un risk officer dans un hedge fund. Ton job n'est PAS de m'aider, c'est de détruire ce système
et de me montrer pourquoi il va échouer.

En t'appuyant sur les sources (citations), identifie sans ménagement :
- biais statistiques et risques d'overfitting
- facteurs redondants / fausse robustesse
- dépendances cachées et fragilités structurelles
- risques opérationnels (data périmée, bugs timezone, yfinance down, cache corrompu)
- la part de hasard dans une éventuelle performance passée
- les biais cognitifs qui vont pourrir mes décisions discrétionnaires
Puis : les 5 stress tests que je devrais faire passer au système avant de lui faire confiance.
```
**Exploitation** : checklist de garde-fous + stress tests. À relancer après chaque grosse évolution.

---

## 6. Audit de biais cognitif sur une décision

**Notebook** : NB-ADVERSARY · **Sources** : Kahneman + Duke

```
[CONTEXTE]

Voici une décision de trading que j'ai prise / que je m'apprête à prendre : [décrire le raisonnement].

En t'appuyant sur les sources (citations) : quels biais cognitifs sont à l'œuvre dans ce raisonnement
(confirmation, ancrage, disponibilité, aversion à la perte, resulting) ? Comment reformuler la
décision en pari probabiliste honnête ? Quelle information me manque pour décider proprement ?
```
**Exploitation** : discipline de décision ; à intégrer éventuellement comme check dans l'onglet Coach.

---

## 7. Clarification de concept (que dit vraiment le livre X)

**Notebook** : selon le sujet · **Sources** : 1 à 2 livres ciblés seulement

```
[CONTEXTE si pertinent]

Que disent précisément ces sources sur [concept] ? Donne la définition exacte, les conditions,
les nuances et les désaccords entre auteurs s'il y en a. Citations obligatoires. Distingue ce qui
est étayé empiriquement de ce qui est une opinion d'auteur.
```
**Exploitation** : lever une ambiguïté avant de formaliser ou d'implémenter.

---

## Rappels transverses

- **Sélection serrée** : pour un prompt pointu, ne cocher que les 2-3 sources nommées, pas tout le notebook.
- **Citations systématiques** : si NotebookLM n'arrive pas à citer, c'est que l'info n'est pas dans
  les sources — ne pas la prendre pour argent comptant.
- **Jamais de code** demandé à NotebookLM. La sortie est une *logique* / *méthode* à passer à Claude Code.
- **Économie de quota** (50 req/jour) : préparer les prompts dans un fichier, les lancer groupés.
