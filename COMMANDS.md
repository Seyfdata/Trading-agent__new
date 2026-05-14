# Référence des commandes Claude Code — SMC-AI Trading Agent

## Commandes globales (disponibles partout)

| Commande | Description |
|----------|-------------|
| `/init` | Analyser le projet et créer/améliorer le CLAUDE.md |
| `/help` | Aide Claude Code |
| `/clear` | Vider le contexte de la conversation |
| `/doctor` | Diagnostiquer la configuration Claude Code |

## Commandes de développement (globales)

| Commande | Description |
|----------|-------------|
| `/plan` | Créer un plan d'implémentation pour une feature complexe |
| `/tdd` | Workflow TDD : écrire tests → implémenter → refactorer |
| `/code-review` | Revue du code local non commité (ou `/code-review 123` pour une PR GitHub) |
| `/python-review` | Revue spécifique Python : PEP8, type hints, sécurité, idiomes |
| `/review-pr` | Revue complète d'une Pull Request GitHub |
| `/refactor-clean` | Nettoyer le code mort, les doublons, les imports inutiles |

## Commandes de documentation

| Commande | Description |
|----------|-------------|
| `/docs` | Mettre à jour la documentation du projet |
| `/update-docs` | Mettre à jour les README et guides |
| `/update-codemaps` | Mettre à jour les codemaps dans docs/CODEMAPS/ |

## Commandes de session

| Commande | Description |
|----------|-------------|
| `/save-session` | Sauvegarder l'état de la session dans ~/.claude/session-data/ |
| `/sessions` | Lister les sessions sauvegardées |

## Skills locaux — ce projet uniquement

Charger un skill = injecter son contexte dans la conversation.

| Commande | Fichier | Utiliser quand... |
|----------|---------|-------------------|
| `/trading-smc` | `.claude/skills/trading-smc.md` | Toute demande trading, scoring, setups, SMC, analysis/, scrapers/, database/ |
| `/react-dashboard` | `.claude/skills/react-dashboard.md` | Toute modification de dashboard/index.html |
| `/pinescript-v5` | `.claude/skills/pinescript-v5.md` | Toute modification dans pinescripts/ |
| `/code-reviewer` | `.claude/skills/code-reviewer/SKILL.md` | Après avoir écrit ou modifié du code |
| `/frontend-design` | `.claude/skills/frontend-design/SKILL.md` | Refonte visuelle ou nouveau composant UI |

## Usage typique

```
# Feature trading
/trading-smc
→ "Améliore le calcul des OB dans smc_analyzer.py"

# Modification dashboard
/react-dashboard
→ "Ajoute un onglet Macro dans le dashboard"

# Après avoir écrit du code
/code-reviewer
→ revue automatique

# Plannification
/plan
→ "Planifie la connexion IBKR API pour Phase 4"
```
