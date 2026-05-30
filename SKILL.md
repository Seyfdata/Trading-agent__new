---
name: notebooklm-trading-research
description: >
  Rend Claude expert dans l'exploitation de NotebookLM pour le projet SMC-AI Trading Agent de Seyf :
  choisir le bon notebook thématique et le bon sous-ensemble de sources, puis rédiger des prompts
  NotebookLM tranchants et ancrés (grounded) à partir de sa bibliothèque quant. Utiliser cette skill
  dès que Seyf parle de NotebookLM, veut préparer/rédiger un prompt NotebookLM, demande quels livres
  consulter pour une question trading/SMC/scoring/risk/validation, veut formaliser un concept SMC,
  challenger son scoring ou son système, concevoir un moteur de risk management, valider une stratégie
  (walk-forward, out-of-sample, overfitting, déflation de Sharpe), ou auditer des biais cognitifs —
  même s'il ne dit pas explicitement "NotebookLM" mais cherche manifestement à raisonner à partir de
  sa bibliothèque de trading. Utiliser aussi pour créer ou restructurer ses notebooks.
---

# NotebookLM — Recherche quant pour SMC-AI

## Rôle de cette skill

Seyf a chargé ~56 livres quant/finance/software dans NotebookLM. Le risque n'est pas le manque
d'information, c'est la **dispersion** : un notebook fourre-tout produit des réponses moyennées et
molles. Cette skill transforme NotebookLM en instrument de précision pour SON projet précis
(LONG only, SMC, swing actions US, validation humaine, stack FastAPI/React CDN/SQLite/yfinance).

Quand cette skill se déclenche, le travail de Claude est de produire **l'un de ces trois livrables**,
jamais du vague :
1. **Un prompt NotebookLM prêt à coller** + le notebook à ouvrir + les sources exactes à cocher.
2. **Une recommandation de structure** (quel notebook, quelles sources) pour un besoin donné.
3. **La traduction d'une sortie NotebookLM** en spécification d'implémentation pour Claude Code.

## La règle non négociable : séparation des rôles

NotebookLM, Claude.ai et Claude Code ne font PAS la même chose. Les confondre est l'erreur n°1.

- **NotebookLM = RAISONNER.** Formaliser un concept à partir des livres, critiquer une logique,
  synthétiser une méthode de validation, attaquer le système. Réponses *ancrées* dans les sources,
  avec citations. Il ne sait que ce qui est dans ses sources — c'est une force (rigueur), pas un défaut.
- **Claude.ai (moi) = ORCHESTRER.** Préparer les prompts NotebookLM, choisir notebooks/sources,
  challenger Seyf, traduire les sorties NotebookLM en specs, séquencer le travail.
- **Claude Code = FAIRE.** Implémenter le code, refactorer, tester, commit/push.

**Ne JAMAIS demander de code à NotebookLM.** Il n'exporte pas de code propre et ce n'est pas son job.
On lui demande la *logique*, les *conditions d'invalidation*, les *risques de faux signaux* — pas du Python.

## Contraintes opérationnelles NotebookLM (gratuit, à jour 2026, Gemini 3)

Ces limites dictent la méthode. Les respecter, c'est gagner en qualité ET en quota.

- **50 sources max par notebook.** Donc notebooks *thématiques*, jamais un notebook unique.
- **500 000 mots / source** : un livre entier tient dans une seule source. Pas besoin de découper.
- **Sélection de sous-ensemble par requête** : dans un notebook, on peut cocher seulement 2-3 livres
  pour une question pointue. **Technique centrale** : plus la sélection est étroite, plus la réponse
  est nette. Un notebook large pour explorer, une sélection serrée pour trancher.
- **~50 requêtes/jour, 3 audio/jour.** Préparer les prompts à l'avance (Seyf travaille déjà comme ça
  pour Claude Code). Ne pas gaspiller en questions vagues.
- **Pas d'export propre, formatage limité** : copier les sorties manuellement, les retravailler dans
  Claude.ai. NotebookLM produit de la matière brute à raffiner, pas un livrable final.
- **Notebooks isolés** : pas de contexte partagé entre notebooks. D'où l'importance de la curation.

## Architecture de notebooks recommandée

Quatre notebooks cœur + deux optionnels. Le détail des sources par notebook (et la liste explicite
des livres qui sont du **bruit** pour ce projet) est dans `references/corpus-map.md` — le lire avant
de recommander quoi que ce soit sur la composition des notebooks.

1. **NB-VALIDATION** — *le plus important.* Tester si le système a un edge réel. Aronson, Pardo,
   López de Prado, Davey. C'est le "banc d'étalonnage" du projet.
2. **NB-SMC-FORMALIZATION** — transformer les concepts SMC flous (BOS, CHoCH, OB, FVG, liquidity)
   en règles déterministes testables. Grimes, Kaufman, Harris, O'Hara.
3. **NB-SCORING-RISK** — scoring multi-facteurs non redondant + moteur de risk. López de Prado
   (Causal Factor Investing), Carver, Vince, Grinold & Kahn.
4. **NB-ADVERSARY** — le reviewer hostile dont le seul job est de détruire le système. Taleb,
   Kahneman, Duke, + un livre "marché efficient" (Malkiel) comme contre-poison.
5. **NB-IMPLEMENTATION** *(optionnel)* — comprendre les patterns d'implémentation Python (Hilpisch,
   Clenow, Jansen). Rappel : la logique ici, le code chez Claude Code.
6. **NB-ARCHITECTURE** *(optionnel, phase refactor)* — Martin, Fowler, Nygard.

## Le workflow (lean, pas de cérémonie)

Pour tout besoin technique du projet :

1. **Identifier le besoin** précisément (ex : "formaliser le BOS", "mon scoring double-compte-t-il
   le momentum ?", "est-ce que mon approche a un edge ?").
2. **NotebookLM** : ouvrir le bon notebook, cocher les sources serrées, coller le prompt préparé.
   → définition rigoureuse / critique / méthode, ancrée dans les livres, avec citations.
3. **Claude.ai (moi)** : transformer la sortie en spec d'implémentation (FICHIER / PROBLÈME /
   SOLUTION / CONTRAINTES / TESTE), en respectant la stack et les règles métier du projet.
4. **Claude Code** : implémenter + tester + commit.
5. **NotebookLM (NB-ADVERSARY)** : critiquer l'implémentation ("où ça casse ?").
6. Boucler.

L'ordre n'est pas figé. Mais NotebookLM ne définit JAMAIS l'architecture de production directement :
il propose la logique, Seyf et Claude valident, Claude Code implémente.

## Comment rédiger un bon prompt NotebookLM

NotebookLM répond mieux à des prompts *structurés* qui exigent une sortie actionnable. La bibliothèque
complète de templates est dans `references/prompt-library.md` (formalisation SMC, critique de scoring,
moteur de risk, méthode de validation, review adverse, audit de biais, clarification de concept).
Lire ce fichier avant de produire un prompt.

Principes systématiques pour tout prompt NotebookLM de ce projet :
- **Donner le contexte projet en tête** : LONG only, swing actions US, validation humaine, R:R ≥ 2.5,
  killzone, OHLCV daily/intraday via yfinance. Sinon NotebookLM répond pour un système générique.
- **Exiger une sortie structurée** : définition / conditions d'invalidation / pseudo-code logique /
  risques de faux signaux / filtres de robustesse. Pas "explique-moi le BOS".
- **Interdire l'interprétation visuelle subjective** pour le SMC : tout doit être déterministe,
  backtestable, sans repaint ni look-ahead bias.
- **Demander les citations** : "appuie chaque affirmation sur les sources".
- **Pour critiquer, mettre NotebookLM en posture hostile** : "tu es un risk officer de hedge fund,
  ton job est de détruire ce système, pas de m'aider".

## Triage de la bibliothèque

La moitié des 56 livres est du bruit pour ce projet (pricing d'options, value investing, calcul
stochastique, culture trading). Ne jamais charger un notebook avec des sources hors-sujet : ça dilue
la réponse. La cartographie complète livre → notebook → usage, et la liste des livres à NE PAS
utiliser (avec la raison), sont dans `references/corpus-map.md`. **Toujours consulter ce fichier
avant de répondre sur "quel livre / quelles sources".**

## Garde-fou final (esprit métrologue)

Un facteur, un signal ou une feature n'entre dans le système que s'il peut être : expliqué clairement,
backtesté correctement, journalisé, reproduit, et survivre à la critique statistique de NB-ADVERSARY.
Sinon il reste dehors. C'est l'équivalent trading d'un instrument qu'on n'accepte pas sans budget
d'incertitude et raccordement à un étalon. Le trading comporte un risque de perte en capital ; un
système non validé l'augmente.
