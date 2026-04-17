# 🚀 Guide Claude Code — Utilisation Optimale

> Ce guide est pour Seyf. Il explique comment tirer le maximum de Claude Code sur le projet SMC-AI Trading Agent.

---

## 1. Architecture Claude Code — Comment ça marche

```
Quand tu lances Claude Code dans VS Code, il lit automatiquement :

1. CLAUDE.md (racine du projet)     → contexte global du projet
2. .claude/settings.local.json      → paramètres locaux
3. Les fichiers ouverts dans VS Code → contexte immédiat
4. Les skills dans le projet         → compétences spécialisées
```

Claude Code a accès à :
- Tous tes fichiers du projet (lecture + écriture)
- Le terminal (il peut exécuter des commandes)
- Git (il peut commit, push, pull)
- pip/npm (il peut installer des packages)

---

## 2. Structure recommandée pour les skills

Place tes skills dans un dossier `.claude/skills/` à la racine du projet :

```
trading-agent/
├── .claude/
│   ├── settings.local.json    # Paramètres Claude Code
│   └── skills/                # Tes skills personnalisés
│       ├── trading-smc.md     # Skill analyse SMC
│       ├── react-dashboard.md # Skill React/dashboard
│       ├── python-data.md     # Skill Python data science
│       └── pinescript.md      # Skill Pine Script
├── CLAUDE.md                  # Contexte projet (déjà créé)
└── ... (reste du projet)
```

### Comment ajouter un skill trouvé sur internet :
1. Télécharge le fichier .md depuis GitHub
2. Place-le dans `.claude/skills/`
3. Claude Code le lira automatiquement

### Comment créer un skill custom :
Crée un fichier .md dans `.claude/skills/` avec cette structure :
```markdown
# Nom du Skill

## Quand utiliser ce skill
(description des cas d'usage)

## Règles
(les règles à suivre)

## Exemples
(exemples concrets)
```

---

## 3. Les 10 commandements du prompt efficace

### ❌ MAUVAIS prompt :
```
Améliore le dashboard
```

### ✅ BON prompt :
```
Dans dashboard/index.html, composant RedditTab :

PROBLÈME : les tickers avec 0 mentions s'affichent en grisé, ça donne l'impression que rien ne marche.

SOLUTION : 
1. Masquer les tickers avec 0 mentions par défaut
2. Afficher "X/22 tickers mentionnés aujourd'hui"
3. Ajouter un toggle "Voir tous" pour les afficher si besoin

CONTRAINTES :
- PAS de localStorage (utiliser un state React)
- Hooks useState EN PREMIER dans le composant
- Vérifier le balance des <div> après modification

TESTE : relance le dashboard et montre le résultat
```

### La formule magique d'un bon prompt :
```
FICHIER : quel fichier modifier
PROBLÈME : qu'est-ce qui ne va pas
SOLUTION : ce que tu veux (en étapes numérotées)
CONTRAINTES : ce qu'il ne faut PAS faire
TESTE : comment vérifier que ça marche
```

---

## 4. Commandes Claude Code essentielles

### Dans la fenêtre Claude Code (VS Code) :

**Navigation :**
- Tape ta demande en français, Claude comprend
- Il peut lire, modifier, créer des fichiers
- Il peut exécuter des commandes terminal

**Raccourcis utiles :**
- `Ctrl+Shift+P` → "Claude" pour ouvrir Claude Code
- Coller un prompt long : copie depuis ce guide, colle dans Claude Code

**Commandes fréquentes pour notre projet :**

```
# Lancer le dashboard
"Lance le dashboard et dis-moi s'il y a des erreurs"

# Tester les imports
"Teste tous les imports Python du projet et dis-moi lesquels échouent"

# Audit syntaxe HTML
"Compte les <div> ouvrantes et fermantes dans dashboard/index.html"

# Git
"Commit tout avec le message 'description' et push"

# Diagnostic
"Le dashboard affiche [erreur]. Diagnostique et corrige."
```

---

## 5. Workflows optimaux pour notre projet

### Workflow A — Corriger un bug
```
1. "Le dashboard affiche [erreur exacte]. Voici la capture/le message d'erreur."
2. Claude Code diagnostique
3. Claude Code corrige
4. "Teste que ça marche"
5. "Commit et push"
```

### Workflow B — Ajouter une fonctionnalité
```
1. "Je veux ajouter [fonctionnalité]. Voici ce que ça doit faire : [description]"
2. Claude Code propose une approche
3. Tu valides ou ajustes
4. Claude Code code
5. "Teste"
6. "Commit et push"
```

### Workflow C — Optimiser du code existant
```
1. "Audite [fichier/composant]. Dis-moi ce qui peut être amélioré."
2. Claude Code analyse
3. "Applique les améliorations [X et Y]"
4. "Teste"
5. "Commit et push"
```

### Workflow D — Début de session
```
1. "git pull origin main" (si tu as bossé sur l'autre poste)
2. "Lance le dashboard et vérifie que tout marche"
3. Commence à travailler
```

### Workflow E — Fin de session
```
1. "Commit tout et push"
2. "Résume ce qu'on a fait"
```

---

## 6. Prompts types pour notre projet

### Dashboard :
```
"Dans dashboard/index.html, [composant] :
- Problème : [description]
- Corrige en respectant : pas de <form>, hooks en premier, vérifier les div"
```

### API :
```
"Dans dashboard/api.py, endpoint [route] :
- Problème : [description]
- Ajouter try/except et clean_for_json()
- Tester avec curl ou dans le navigateur"
```

### Pine Script :
```
"Dans pinescripts/smc_all_in_one.pine :
- Modifier : [description]
- RAPPEL : pas de '?' ternaire, pas de '+' en début de ligne
- crossover/crossunder au niveau global uniquement"
```

### Analyse/Scoring :
```
"Dans analysis/[fichier].py :
- Modifier : [description]
- Tester avec : python -c 'from analysis.[module] import [fonction]; ...'"
```

---

## 7. Erreurs fréquentes et solutions rapides

| Erreur | Cause | Solution rapide |
|--------|-------|-----------------|
| "Script error" (dashboard) | Syntaxe JSX cassée | "Compte les div et accolades dans index.html" |
| "Rendered more hooks" | useState après un return | "Vérifie que tous les hooks sont AVANT tout return conditionnel dans [composant]" |
| "numpy.bool not iterable" | yfinance types numpy | "Ajoute clean_for_json() avant le return dans [endpoint]" |
| Port 8000 occupé | Ancien serveur | "Tue le process sur le port 8000 et relance" |
| "LineChart not defined" | Recharts pas importé | "Vérifie le destructuring Recharts en haut du script" |
| Pine Script "?" error | Opérateur ternaire | "Remplace les ? par des if/else dans le .pine" |
| Pine Script "+" error | Continuation de ligne | "Mets la concaténation sur une ligne ou utilise :=" |

---

## 8. Skills recommandés à ajouter

### Skills que tu peux chercher sur GitHub :

1. **FastAPI best practices** — pour optimiser l'API
   - Cherche : "claude code skill fastapi" ou "fastapi CLAUDE.md"

2. **React patterns** — pour le dashboard
   - Cherche : "claude code skill react hooks"

3. **Python data analysis** — pour le scoring/backtest
   - Cherche : "claude code skill pandas yfinance"

4. **Git workflow** — pour les bonnes pratiques Git
   - Cherche : "claude code skill git workflow"

### Comment évaluer un skill trouvé sur internet :
- ✅ BON : fichier .md structuré avec des règles claires et des exemples
- ❌ MAUVAIS : fichier trop long (>5000 lignes), trop générique, pas de règles concrètes
- ⚠️ ATTENTION : ne jamais installer de skills qui demandent des clés API ou des accès sensibles

---

## 9. Optimiser la vitesse de Claude Code

### Garder le contexte court :
- Ne PAS ouvrir 20 fichiers en même temps dans VS Code
- Ouvrir seulement le fichier sur lequel tu travailles
- Claude Code lit tout ce qui est ouvert → plus de fichiers = plus lent

### Prompts efficaces :
- Court et précis > long et vague
- Un fichier à la fois > "modifie partout"
- Tester après chaque modification > faire 10 modifications d'un coup

### Quand Claude Code est lent :
- Fermer et rouvrir la fenêtre Claude Code
- Fermer les fichiers non nécessaires dans VS Code
- Si le projet est très gros : préciser le fichier exact à modifier

---

## 10. Checklist avant chaque session

```
□ VS Code ouvert sur le bon dossier (trading-agent/)
□ CLAUDE.md présent à la racine
□ Terminal accessible
□ Git à jour (pull si nécessaire)
□ Dashboard fonctionnel (python launch_dashboard.py)
```

---

## 11. Checklist après chaque session

```
□ Tester que le dashboard fonctionne
□ Commit avec un message descriptif
□ Push vers GitHub
□ Noter ce qui a été fait (pour la prochaine session)
```
