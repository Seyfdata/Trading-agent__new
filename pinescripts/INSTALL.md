# SMC-AI All-in-One v3 — Guide d'installation TradingView

Compatible compte **GRATUIT** TradingView · 1 indicateur · 1 alerte consolidée.

---

## 1. Installation rapide

1. Sur TradingView, ouvre un graphique (ex. NVDA, 1D)
2. En bas : clique **"Pine Editor"**
3. `Ctrl+A` → `Suppr` → colle le contenu de `smc_all_in_one.pine` → `Ctrl+S`
4. Clique **"Ajouter au graphique"**
5. L'indicateur apparaît immédiatement en overlay

---

## 2. Mode Simple vs Mode Expert

### 🔰 Mode Simple — activé par défaut (recommandé pour débuter)

Graphique propre avec seulement l'essentiel :

```text
Affiché :
  SMA200 (orange épaisse) + SMA50 (bleue fine)
  Order Blocks (zones vertes = support, rouges = résistance)
  Zone Discount (fond vert léger) / Premium (fond rouge léger)
  Signaux BUY (grandes flèches vertes)
  Signaux TARGET (grandes flèches rouges)
  Signaux DANGER (grandes croix rouges)
  Trail Stop (lignes jaunes pointillées)
  Niveaux Entry / Stop / Target
  Panneau récapitulatif (haut droite)

Masqué (superflu pour commencer) :
  Fair Value Gaps
  Labels BOS / CHoCH
  Lignes swing High/Low
```

### 🔬 Mode Expert — décoche "🔰 Mode Simple"

```text
Affichage supplémentaire :
  Labels BOS UP / BOS DOWN / CHoCH
  Fair Value Gaps (zones translucides)
  Lignes swing pointillées
```

---

## 3. Comprendre les signaux

### 🟢 Flèche verte sous la bougie (BUY)

Le système détecte une opportunité d'achat.

**Quand apparaît-elle ?** Les 4 conditions sont réunies simultanément :

- Prix en zone DISCOUNT (sous le milieu du range 20j)
- Prix dans un Bull OB non mitigé (zone de support institutionnelle)
- SMA50 au-dessus de SMA200 (tendance haussière)
- Bougie verte (confirmation du rebond)

**Que faire ?**
Vérifie sur le dashboard (onglet Coach) avant d'agir.
Ce signal est rare — c'est voulu. Qualité > quantité.

---

### 🔴 Flèche rouge au-dessus de la bougie (TARGET)

Ton objectif de prix est atteint.

**Que faire ?**

1. Va sur IBKR
2. Le bracket order prend profit automatiquement
3. Clôture le trade dans l'onglet Journal du dashboard

---

### ❌ Croix rouge sous la bougie (DANGER)

Quelque chose d'important a changé. Ce n'est PAS un ordre automatique — c'est un avertissement.

**Déclenché par l'une de ces 3 situations :**

- SMA200 cassée vers le bas → perte de support majeur
- CHoCH baissier → retournement de tendance possible
- Prix dans un Bear OB avec volume élevé (>1.5x la moyenne)

**Que faire ?**
Évalue si tu dois sortir de ta position. Vérifie le dashboard.
Ne panique pas — c'est une information, pas un ordre.

---

### 📈 Ligne jaune pointillée (Trail Stop)

Ton trade est en profit. Le système suggère de remonter ton stop pour sécuriser des gains.

**Niveaux suggérés :**

| Prix atteint | Stop suggéré     | Ce que ça sécurise        |
| ------------ | ---------------- | ------------------------- |
| Entry + 1R   | Breakeven (entry)| Tu ne peux plus perdre    |
| Entry + 1.5R | Entry + 0.5R     | Tu sécurises 0.5R de gain |
| Entry + 2R   | Entry + 1R       | Tu sécurises 1R de gain   |

**Important :** Le trail stop est une **suggestion visuelle uniquement**.
Va sur IBKR et modifie ton stop manuellement au niveau affiché.

---

### ⚠️ Triangle orange (Résistance)

Le prix approche une zone de résistance (Bear OB ou zone Premium).
Ne pas ouvrir de nouveau trade dans cette configuration.

---

## 4. Configuration pour ton premier trade

### Exemple : Setup AMZN depuis le dashboard

1. Le dashboard (onglet Coach) te donne :
   - Entry : $207.67
   - Stop : $201.50
   - Target : $223.09
   - Quantité suggérée : 16 actions

2. Sur TradingView, ouvre AMZN en timeframe 1D ou 4H

3. Double-clique sur l'indicateur → **⚙️ Paramètres** → groupe **🎯 Trade Levels** :

   | Paramètre          | Valeur |
   | ------------------ | ------ |
   | Entry Price        | 207.67 |
   | Stop Loss          | 201.50 |
   | Take Profit        | 223.09 |
   | Nombre d'actions   | 16     |
   | Activer Trail Stop | ✅     |

4. Clique **OK** → tu verras :

```text
TARGET $223.09 (+$246) ──── ligne verte
[zone verte = gain]
R:R  2.50x   Risque: -$98 | Gain: +$246
ENTRY  $207.67 ─────────── ligne bleue
[zone rouge = risque]
STOP   $201.50 (-$98) ──── ligne rouge
```

1. **Workflow en temps réel :**
   - Une flèche verte BUY apparaît → c'est le moment d'entrer
   - Une ligne jaune apparaît à +1R → monte ton stop sur IBKR au breakeven
   - Une flèche rouge TARGET → tes gains sont sécurisés automatiquement
   - Un X rouge DANGER → évalue si tu dois sortir

---

## 5. Activer l'alerte unique (compte gratuit)

1. Clique sur l'icône **⏰ Alertes** dans la barre latérale
2. Clique **"Créer une alerte"**
3. **Condition** : sélectionne **"SMC-AI All-in-One"**
4. Sous-menu : sélectionne **"SMC-AI Signal"**
5. Notification : Popup + Email recommandé
6. Clique **"Créer"**

**Cette unique alerte couvre :**

| Événement               | Signal                                  |
| ----------------------- | --------------------------------------- |
| Flèche verte BUY        | Les 4 conditions réunies                |
| Flèche rouge TARGET     | Prix >= ton objectif                    |
| Croix rouge DANGER      | SMA200 cassée / CHoCH / Bear OB volume  |
| Trail +1R               | Propose de monter le stop au breakeven  |
| Trail +1.5R             | Propose de monter le stop à +0.5R       |
| Trail +2R               | Propose de monter le stop à +1R         |
| BOS haussier / baissier | Changement de structure                 |
| Prix proche SMA200      | Distance < 0.5%                         |

---

## 6. Lire le panneau récapitulatif

```text
+-----------------------------------+
|  SMC-AI          AMZN             |
|  Signal     BUY actif             |  <- Signal prioritaire
|  Tendance   BULL                  |
|  Zone       DISCOUNT              |
|  SMA200     +2.31%                |
|  Volume     x2.4                  |
|  OB proche  Bull OB               |
|  FVG proche OUI                   |
|  PnL        +$92 (+0.94R)         |  <- Si trade actif
|  Trail      +1R — Breakeven       |  <- Si trail activé
|  VERDICT    ACHETER SI SIGNAL     |
+-----------------------------------+
```

**PnL** : calculé automatiquement si tu as renseigné Entry + Nombre d'actions.
**Trail** : affiche le niveau de stop suggéré actuel.

---

## 7. Timeframes recommandés

| Timeframe | Usage                                       |
| --------- | ------------------------------------------- |
| 1D        | Vue principale, structure, OB significatifs |
| 4H        | Confirmation entry, détail du setup         |
| 1H        | Killzone 14h30–16h30, timing précis         |

---

## 8. Réglage de la sensibilité (swing_length)

| Valeur | Usage |
|--------|-------|
| 3–4 | Intraday, beaucoup de signaux |
| 5 (défaut) | Swing, équilibre signal/bruit |
| 8–10 | Position, signaux rares mais solides |

---

## 9. Dépannage

**"Aucun signal BUY ne s'affiche"**
Les 4 conditions doivent être réunies. C'est rare — c'est voulu.
Vérifie que le prix est sur fond vert (discount) et dans un Bull OB.

**"Le trail stop ne s'affiche pas"**
Vérifie que "📈 Activer Trail Stop" est coché ET que Entry Price > 0.
Le trail apparaît seulement quand le prix dépasse Entry + 1R.

**"L'alerte ne se déclenche pas"**
Sur compte gratuit, 1 seule alerte active. Vérifie qu'aucune autre alerte n'est en conflit.

**"Trop d'éléments — le graphique rame"**
Réduis la période affichée (moins de barres) ou désactive FVG en mode Expert.

---

## 10. Backtester TradingView (fichier séparé)

> ⚠️ Utilise `smc_strategy_backtest.pine` UNIQUEMENT pour le backtest.
> Pour le trading live, utilise `smc_all_in_one.pine`.
> Tu ne peux pas avoir les deux en même temps sur le même graphique.

### Charger le script de backtest

1. Ouvre Pine Editor → `Ctrl+A` → `Suppr`
2. Colle le contenu de `smc_strategy_backtest.pine`
3. `Ctrl+S` → clique **"Ajouter au graphique"**
4. L'onglet **"Strategy Tester"** apparaît automatiquement en bas du chart

### Ce que tu verras

```text
Sur le chart :
  Flèches vertes ▲ BUY — entrées en position
  Flèches rouges ▼ WIN/LOSS — sorties
  Fond vert = trade gagnant en cours
  Fond rouge = trade perdant en cours
  SMA200 orange épaisse + SMA50 bleue fine

En bas (Strategy Tester natif TradingView) :
  Equity curve (courbe de capital)
  Liste de tous les trades
  Statistiques complètes

En haut à gauche (tableau SMC-AI) :
  Stratégie active
  Trades W/L
  Winrate %
  Profit Factor
  Net PnL $
  Rendement %
  Max Drawdown
  Verdict : VALIDE / PASSABLE / NON RENTABLE
```

### Paramètres disponibles

| Paramètre | Défaut | Rôle |
| --------- | ------ | ---- |
| Stratégie | Les 3 | Tester une ou toutes les stratégies |
| Risque % | 1.0% | Pourcentage du capital par trade |
| R:R minimum | 2.5x | Ratio Risk/Reward du target |
| Max jours | 20 | Sortie forcée après N bougies |
| Année début | 2023 | Filtrer la période de test |

### Les 3 stratégies testées

**Discount Zone (DZ)**
Prix sous le midpoint du range 20j + SMA50>SMA200 + volume normal.
Entrée au close, stop sous le plus bas des 5 dernières bougies.

**SMA200 Bounce (SMA)**
Prix qui touche la SMA200 (à 2% près) et rebondit au-dessus.
Entrée au close, stop à -1.5% sous la SMA200.

**Volume Momentum (MOM)**
Volume > 2× la moyenne + bougie verte > 1.5% + prix sous SMA200×1.15.
Entrée au close, stop sous le plus bas de la bougie.

### Workflow de test

1. **Choisir un ticker** — commence par NVDA ou AMZN (1D)
2. **Tester "Les 3"** pour voir quelle stratégie fonctionne le mieux
3. **Changer la stratégie** dans les paramètres pour isoler chacune
4. **Changer le timeframe** — 1D pour swing, 4H pour intraday
5. **Changer l'année** pour tester sur différentes périodes de marché
6. **Comparer** — un Profit Factor > 1.3 et Winrate > 40% = stratégie valide

### Interpréter le tableau de résultats

| Verdict | Critères |
| ------- | -------- |
| ✅ VALIDE | Profit Factor ≥ 1.3 ET Winrate ≥ 40% |
| ⚠️ PASSABLE | Profit Factor ≥ 1.0 (rentable mais fragile) |
| ❌ NON RENTABLE | Profit Factor < 1.0 (pertes nettes) |

> Un Winrate de 40% avec un R:R de 2.5x est **rentable**.
> Exemple : 10 trades → 4 wins × $250 = $1000 / 6 losses × $100 = $600 → net +$400
