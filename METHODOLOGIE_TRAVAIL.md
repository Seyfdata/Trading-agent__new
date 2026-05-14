# 🎯 Méthodologie de travail — SMC-AI Trading Agent

> Comment travailler efficacement avec Claude Pro sans épuiser ta barre d'utilisation.
> Optimisé pour le projet trading-agent, 2 postes (pro + perso).

---

## 1. Comprendre tes limites Claude Pro

```
Claude Pro = ~45 messages par fenêtre de 5 heures
           = ~200 messages par jour (si bien répartis)

ATTENTION :
- Claude.ai + Claude Code = MÊME compteur
- Un message dans une longue conversation coûte PLUS cher
- Message 1 = ~500 tokens | Message 15 = ~15,000 tokens | Message 30 = ~40,000 tokens
- Heures de pointe (14h-20h CET) = limites réduites
- Heures creuses (nuit, week-end) = limites plus généreuses
```

---

## 2. La règle d'or : MEGA-PROMPTS

### ❌ Ce qui GASPILLE ton quota (7 messages) :
```
Toi : "Salut, on reprend le projet"
Claude : "Oui, où en étions-nous..."
Toi : "Le Reddit ne marche pas"
Claude : "Quel est le problème exact..."
Toi : "Les données ne se rafraîchissent pas"
Claude : "Je vais diagnostiquer..."
Toi : "Ok lance le fix"
```

### ✅ Ce qui ÉCONOMISE ton quota (1 message) :
```
Dans scrapers/reddit.py :

PROBLÈME : les données Reddit ne se rafraîchissent pas, MRVL est toujours le seul ticker affiché.

CAUSE PROBABLE : le wrapper appelle un vieux CSV au lieu de scraper le JSON public à chaque refresh.

SOLUTION :
1. Créer une fonction scan_reddit_direct() qui scrape /r/stocks/hot.json et /r/wallstreetbets/hot.json
2. Extraire les tickers mentionnés dans les titres
3. Filtrer avec TICKER_BLACKLIST
4. Retourner watchlist_results et discovery_results séparément

CONTRAINTES :
- PAS d'API Reddit (on utilise le JSON public)
- Try/except sur chaque subreddit
- clean_for_json() sur le résultat

TESTE : lance le scan et montre les résultats dans le terminal
PUIS : commit et push avec le message "Fix Reddit scan direct"
```

**Un seul message = diagnostic + solution + contraintes + test + commit.**
Tu économises 6 messages d'un coup.

---

## 3. Workflow quotidien optimisé

### MATIN (Claude.ai — cette conversation)
```
Durée : 15-30 min | Messages : 3-5 max

1. Dire où tu en es et ce que tu veux faire
2. Recevoir les prompts à copier dans Claude Code
3. C'est tout — la vraie action se passe dans Claude Code
```

### JOURNÉE (Claude Code dans VS Code)
```
Durée : 1-2h | Messages : 10-15 max (MEGA-PROMPTS)

1. Ouvrir VS Code sur trading-agent/
2. Ouvrir Claude Code
3. Coller les prompts préparés le matin
4. Tester chaque modification
5. Commit + push quand ça marche
```

### SOIR (optionnel — heures creuses)
```
Durée : 30 min | Messages : 5-8 (quota plus généreux le soir)

1. Fixes, optimisations, tests
2. Les heures creuses (après 20h CET) offrent plus de messages
```

---

## 4. Répartition Claude.ai vs Claude Code

| Tâche | Où | Pourquoi |
|-------|-----|---------|
| Planifier la session | Claude.ai | Je connais le contexte du projet |
| Discuter stratégie/architecture | Claude.ai | Pas besoin de toucher aux fichiers |
| Créer/modifier du code | Claude Code | Il voit et modifie tes fichiers directement |
| Débugger | Claude Code | Il peut exécuter et voir les erreurs |
| Git (commit/push/pull) | Claude Code | Accès terminal direct |
| Préparer des prompts | Claude.ai | Je formate les prompts optimaux pour Claude Code |
| Auditer le projet | Claude Code | Il peut scanner tous les fichiers |

**Règle** : Claude.ai pour PENSER, Claude Code pour FAIRE.

---

## 5. Économiser les messages — Techniques avancées

### A. Préparer tes prompts AVANT d'ouvrir Claude
Écris tes demandes dans un fichier texte (Notepad/VS Code) AVANT de les envoyer.
Ça évite les "euh, en fait je voulais dire..." qui gaspillent des messages.

### B. Combiner les tâches
Au lieu de 3 prompts séparés :
- "Fixe le Reddit"
- "Ajoute un bouton"  
- "Commit et push"

Un seul prompt :
- "1) Fixe le Reddit 2) Ajoute le bouton 3) Commit et push"

### C. Démarrer de nouvelles conversations souvent
Message 1 d'une conversation = ~500 tokens
Message 30 = ~40,000 tokens (80x plus cher !)

→ Toutes les 10-15 messages, démarre une NOUVELLE conversation.
→ Le CLAUDE.md dans ton projet donne le contexte automatiquement.

### D. Utiliser le bon modèle
- Sonnet (par défaut) : rapide, économe — pour 90% des tâches
- Opus : puissant mais consomme 3-5x plus — réserver pour les tâches complexes

### E. Travailler en heures creuses
- Peak : 14h-20h CET (limites réduites)
- Creux : 20h-08h CET + week-ends (limites doublées)
- Planifie le gros travail le soir ou le week-end

---

## 6. Configuration VS Code optimale

### Extensions recommandées :
1. Claude Code (déjà installé)
2. GitLens — pour voir l'historique Git visuel
3. Python — pour l'autocomplétion et le debugging
4. Prettier — pour formater le code automatiquement
5. Error Lens — pour voir les erreurs inline

### Paramètres VS Code recommandés :
```json
// settings.json (Ctrl+Shift+P → "Open Settings JSON")
{
    "editor.fontSize": 14,
    "editor.wordWrap": "on",
    "editor.formatOnSave": true,
    "files.autoSave": "afterDelay",
    "files.autoSaveDelay": 5000,
    "terminal.integrated.defaultProfile.windows": "Command Prompt",
    "explorer.confirmDelete": true,
    "git.autofetch": true
}
```

### Raccourcis VS Code essentiels :
| Raccourci | Action |
|-----------|--------|
| Ctrl+` | Ouvrir/fermer le terminal |
| Ctrl+P | Ouvrir un fichier rapidement |
| Ctrl+Shift+F | Rechercher dans tous les fichiers |
| Ctrl+Shift+G | Vue Git |
| Ctrl+/ | Commenter/décommenter du code |
| Ctrl+Z | Annuler |
| Ctrl+S | Sauvegarder |

### Organisation des fenêtres :
```
┌─────────────────────────────────────────────┐
│ VS Code                                     │
│ ┌──────────┬────────────────────────────────┐│
│ │ Explorer │ Fichier en cours d'édition     ││
│ │ (gauche) │                                ││
│ │          │                                ││
│ │          │                                ││
│ │          ├────────────────────────────────┤│
│ │          │ Terminal (en bas)              ││
│ │          │ python launch_dashboard.py     ││
│ └──────────┴────────────────────────────────┘│
│ Claude Code (panneau latéral droit)          │
└─────────────────────────────────────────────┘

+ Navigateur avec le dashboard ouvert à côté
```

---

## 7. Flux de travail entre 2 postes

### PC PRO (non admin) :
```
Début de session :
  git pull origin main
  python launch_dashboard.py

Fin de session :
  git add . && git commit -m "description" && git push origin main
```

### PC PERSO (admin, fixe) :
```
Début de session :
  git pull origin main
  python launch_dashboard.py

Fin de session :
  git add . && git commit -m "description" && git push origin main
```

**Règle** : TOUJOURS pull avant de travailler, TOUJOURS push avant d'arrêter.
**Ne JAMAIS travailler sur les deux postes en même temps** sans pull/push entre.

---

## 8. Template de session de travail

### Copie ce template au début de chaque session Claude.ai :

```
Salut, on reprend le projet trading-agent.
PC : [pro/perso]
Dernier push depuis : [ce PC / l'autre PC]

Aujourd'hui je veux :
1. [Objectif principal]
2. [Objectif secondaire si temps]

Prépare-moi les prompts Claude Code.
```

### Template fin de session :
```
On arrête. Résume ce qu'on a fait et prépare les prompts pour la prochaine session.
Push final.
```

---

## 9. Checklist d'optimisation

```
AVANT chaque session :
□ Pull Git si nécessaire
□ CLAUDE.md à la racine du projet
□ Objectifs clairs en tête
□ Prompts préparés dans un fichier texte

PENDANT la session :
□ MEGA-PROMPTS (1 message = 1 tâche complète)
□ Nouvelle conversation toutes les 10-15 messages
□ Tester après chaque modification
□ Ne pas ouvrir trop de fichiers dans VS Code

APRÈS la session :
□ Tester le dashboard
□ Commit avec message descriptif
□ Push vers GitHub
□ Noter les tâches restantes
```

---

## 10. Planning hebdomadaire recommandé

| Jour | Durée | Focus |
|------|-------|-------|
| Lundi | 30 min | Pull + vérifier que tout marche + 1 amélioration |
| Mardi | 30 min | 1 bug fix ou 1 amélioration |
| Mercredi | 30 min | Utiliser le dashboard + enregistrer trades |
| Jeudi | 30 min | 1 amélioration ou nouvelle fonctionnalité |
| Vendredi | 15 min | Push final + noter les priorités week-end |
| Week-end | 1-2h | Session longue (heures creuses = plus de quota) |

**Le week-end est le meilleur moment pour les gros chantiers** (quota doublé).

---

*"Un bon prompt vaut 10 mauvais prompts. Économise ton quota, maximise ton impact."*
