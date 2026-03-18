# SMC-AI All-in-One — Guide d'installation TradingView

Script Pine Script v5 all-in-one compatible compte **GRATUIT** TradingView.
1 seul indicateur = 1 slot utilisé sur les 3 disponibles en compte gratuit.

---

## 1. Ouvrir Pine Editor

1. Va sur [tradingview.com](https://tradingview.com) et ouvre un graphique
2. En bas de l'écran, clique sur **"Pine Editor"** (onglet en bas)
3. Une fenêtre d'édition de code s'ouvre

```
┌─────────────────────────────────────────────────────────────┐
│  [Graphique principal]                                       │
│                                                              │
│                                                              │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Pine Editor  │  Stratégie  │  ...                    [▲][▼] │
│                                                              │
│  //@version=5                                                │
│  indicator("Mon script"...)                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Coller le script

1. Dans Pine Editor, **sélectionne tout** le code existant : `Ctrl+A` (Windows) ou `Cmd+A` (Mac)
2. **Supprime-le** avec `Suppr` ou `Backspace`
3. Ouvre le fichier `smc_all_in_one.pine` et **copie tout son contenu** : `Ctrl+A` puis `Ctrl+C`
4. **Colle** dans Pine Editor : `Ctrl+V`
5. Clique sur **"Enregistrer"** (icône disquette ou `Ctrl+S`)

```
┌──────────────────────────────────────────────────────────────┐
│  Pine Editor                              [Enregistrer] [▶]  │
│                                                              │
│  //@version=5                                                │
│  indicator("SMC-AI All-in-One", overlay=true,                │
│      max_boxes_count=500, ...)                               │
│                                                              │
│  show_structure = input.bool(true, ...)                      │
│  ...                                                         │
│                                             [Ajouter au graph]│
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Ajouter l'indicateur au graphique

1. Clique sur le bouton **"Ajouter au graphique"** en bas à droite de Pine Editor
2. L'indicateur apparaît immédiatement sur le graphique (overlay)
3. Tu verras :
   - Des lignes pointillées aux niveaux swing highs/lows
   - Des labels **BOS ▲** / **BOS ▼** / **CHoCH ⚠** sur les cassures
   - Des rectangles verts (Bull OB) et rouges (Bear OB)
   - Des zones translucides verts/rouges (FVG)
   - La SMA200 en orange et la SMA50 en bleu
   - Un fond vert léger (discount) ou rouge léger (premium)
   - Un tableau récapitulatif en haut à droite

```
┌──────────────────────────────────────────────────────────────┐
│  NVDA — 1D                              ┌──────────────────┐ │
│                                         │ SMC-AI Dashboard │ │
│         BOS ▲         ┌──────────────┐  │ Biais   BULL     │ │
│  ─────────────────────│  Bull OB     │  │ Zone    DISCOUNT  │ │
│                        └──────────────┘  │ SMA200  +2.3%   │ │
│  ░░░░░░░░░░░░░░ FVG ░░░░░░░░░░░░░░░░░  │ Volume  Normal  │ │
│  ─────────── SMA 200 (orange) ─────────  └──────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Configurer les paramètres

Pour accéder aux paramètres :
1. Sur le graphique, double-clique sur le nom de l'indicateur en haut à gauche
   — OU — clique sur l'icône ⚙️ à côté du nom
2. Une fenêtre "Paramètres" s'ouvre avec tous les groupes

### Groupes disponibles

| Groupe | Paramètre | Description |
|--------|-----------|-------------|
| 📈 Structure | BOS/CHoCH ON/OFF | Afficher les labels de structure |
| 📈 Structure | Longueur du swing | Sensibilité des pivots (défaut : 5) |
| 🟢 Order Blocks | OB ON/OFF | Afficher les rectangles OB |
| 🟢 Order Blocks | OB Mitigés ON/OFF | Griser les OB mitigés (vs supprimer) |
| 📊 FVG | FVG ON/OFF | Afficher les Fair Value Gaps |
| 📊 FVG | Taille min (× ATR) | Filtrer les petits FVG (défaut : 0.1) |
| 📏 MM | SMA200/50 ON/OFF | Afficher les moyennes mobiles |
| 📏 MM | Zone D/P ON/OFF | Fond discount/premium |
| 🎯 Trade Levels | Entry Price | Prix d'entrée (0 = désactivé) |
| 🎯 Trade Levels | Stop Loss | Stop loss |
| 🎯 Trade Levels | Take Profit | Objectif |
| 📋 Tableau | Tableau ON/OFF | Afficher le dashboard en haut droite |

### Configurer un trade (Entry / Stop / Target)

1. Dans les paramètres, groupe **🎯 Trade Levels**
2. Coche **"Niveaux Entry/Stop/Target"**
3. Entre les prix :
   - **Entry Price** : ex. `207.67`
   - **Stop Loss** : ex. `201.50`
   - **Take Profit** : ex. `223.09`
4. Clique **OK** — les lignes apparaissent immédiatement

Le script calcule et affiche automatiquement le **R:R** :
```
ENTRY  $207.67  ←── ligne bleue
R:R    2.50×    ←── label au milieu (vert si ≥ 2.5, orange sinon)
TARGET $223.09  ←── ligne verte
        ↑ zone verte (gain)
ENTRY  $207.67
        ↓ zone rouge (risque)
STOP   $201.50  ←── ligne rouge
```

---

## 5. Créer des alertes

Les alertes se déclenchent automatiquement quand les conditions sont remplies.

### Étapes

1. Clique sur l'icône **⏰ Alertes** dans la barre d'outils (ou `Alt+A`)
2. Clique **"Créer une alerte"**
3. Dans **"Condition"**, sélectionne **"SMC-AI All-in-One"**
4. Dans le menu déroulant suivant, choisis le type :

| Alerte | Se déclenche quand |
|--------|--------------------|
| BOS Haussier | Nouveau BOS bull (cassure haut) |
| BOS Baissier | Nouveau BOS bear (cassure bas) |
| CHoCH | Retournement potentiel détecté |
| Prix proche SMA200 | Distance < 0.5% de la SMA200 |
| Prix dans un Bull OB | Le prix touche un OB haussier non mitigé |
| Prix sur Entry | Le prix atteint ton niveau d'entrée |
| Stop Loss touché | 🛑 Stop atteint |
| Target atteint | 🎯 Objectif atteint |

5. Configure la notification : **Email**, **Popup**, ou **Webhook**
6. Clique **"Créer"**

> **Conseil** : Active au minimum "BOS Haussier", "Prix dans un Bull OB",
> "Stop Loss touché" et "Target atteint" pour chaque ticker que tu surveilles.

---

## 6. Ce que tu dois voir

### Vue complète avec tous les modules actifs

```
┌─────────────────────────────────────────────────────────────────┐
│  NVDA — 1D                               ┌────────────────────┐ │
│                                          │ SMC-AI  Dashboard  │ │
│  CHoCH ⚠   BOS ▲   BOS ▼               │ Biais   BULL       │ │
│  ←·······→ ←·····→ ←·····→             │ Zone    DISCOUNT   │ │
│                                          │ SMA200  +2.31%    │ │
│  ┌─────────────────────────┐             │ SMA200  $124.08   │ │
│  │     Bull OB (teal)      │             │ Volume  🔥 ÉLEVÉ  │ │
│  └─────────────────────────┘             └────────────────────┘ │
│                                                                   │
│  ░░░░░░░░ Bull FVG (vert translucide) ░░░░░░░░░░░░░░░░░░░░░░   │
│                                                                   │
│  ─────────────── SMA 50 (bleu) ─────────────────────────────   │
│                                                                   │
│  ═══════════════ SMA 200 (orange, épaisse) ══════════════════   │
│                                                                   │
│  ·  ·  ·  ·  ·  ·  Midpoint 50% (pointillé gris)  ·  ·  ·  ·  │
│                                                                   │
│  [fond vert très léger = DISCOUNT ZONE]                          │
│                                                                   │
│                     TARGET $223.09 ─── ←── ligne verte + label  │
│  [zone verte gain]                                                │
│                     ENTRY  $207.67 ─── ←── ligne bleue + label  │
│  [zone rouge risque]               R:R 2.50×                    │
│                     STOP   $201.50 ─── ←── ligne rouge + label  │
└─────────────────────────────────────────────────────────────────┘
```

### Codes couleur

| Couleur | Signification |
|---------|---------------|
| 🟢 Teal/Vert | Haussier (Bull OB, BOS ↑, Discount zone, SMA50) |
| 🔴 Rouge | Baissier (Bear OB, BOS ↓, Premium zone, Stop) |
| 🟠 Orange | SMA200, attention (CHoCH) |
| 🔵 Bleu | Neutre/Entry (SMA50, Entry price) |
| ⬜ Gris | Éléments mitigés/comblés, midpoint |

---

## 7. Conseils d'utilisation

### Timeframes recommandés

- **1D** : vue principale, structure HTF, OB/FVG significatifs
- **4H** : détail de la structure, entry précis
- **1H** : killzone, timing d'entrée

### Workflow avec le dashboard Python

1. **Dashboard Python** → identifie les tickers Grade A/B + entry/stop/target
2. **TradingView** → ouvre le ticker, colle l'indicateur SMC-AI
3. **Entre les niveaux** dans les paramètres 🎯 Trade Levels
4. **Vérifie visuellement** :
   - Le prix est-il dans une Discount Zone ? (fond vert)
   - Y a-t-il un Bull OB non mitigé proche ?
   - Y a-t-il un FVG haussier à combler ?
   - La SMA200 est-elle proche (support) ?
5. Si tout est aligné → **prends le trade**

### Régler la sensibilité des pivots

| Swing Length | Utilisation |
|-------------|-------------|
| 3–4 | Scalping / intraday — beaucoup de BOS |
| 5 (défaut) | Swing trading — équilibre signal/bruit |
| 8–10 | Position trading — signaux rares mais forts |
| 15–20 | Macro structure — BOS/CHoCH majeurs uniquement |

---

## 8. Dépannage

**"Trop de labels/boîtes" — l'indicateur est lent**
→ Désactive les modules dont tu n'as pas besoin (FVG, OB mitigés)
→ Réduis la période affichée sur le graphique

**"Les OB ne s'affichent pas"**
→ Il faut d'abord avoir un BOS sur la période affichée
→ Essaie un timeframe plus large (1D au lieu de 1H)

**"Le tableau ne s'affiche pas"**
→ Vérifie que "Tableau récapitulatif" est coché dans les paramètres
→ Attends que la barre courante soit chargée (`barstate.islast`)

**"Erreur max_boxes_count"**
→ Normale sur des historiques très longs — va dans les paramètres
   Pine Editor → désactive "OB Mitigés" et "FVG Comblés"

**"R:R ne s'affiche pas"**
→ Les 3 champs Entry, Stop ET Target doivent tous être > 0
→ Entry doit être différent de Stop
