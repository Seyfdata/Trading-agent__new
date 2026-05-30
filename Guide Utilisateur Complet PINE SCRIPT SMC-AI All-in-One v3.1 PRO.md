# 📘 Guide Utilisateur — SMC-AI All-in-One v3.1 PRO
### Guide simple, clair et pratique pour TradingView

Bienvenue dans le guide du script **SMC-AI All-in-One v3.1 PRO**.

Ce script a été conçu pour :
- simplifier les concepts du Smart Money (SMC),
- filtrer les faux signaux,
- aider à trouver des zones d’achat/vente plus propres,
- assister la gestion du trade automatiquement.

Même si vous débutez sur TradingView, vous pouvez l’utiliser facilement grâce au **Mode Simple**.

---

# 1. 🎯 À quoi sert ce script ?

Le script analyse automatiquement :

✅ la tendance du marché  
✅ les zones où les institutions achètent/vendent  
✅ les cassures de structure (BOS / CHoCH)  
✅ les zones Premium / Discount  
✅ le volume  
✅ les zones de liquidité (FVG / Order Blocks)

Puis il transforme tout cela en :

🟢 Signaux BUY  
🔴 Signaux DANGER  
🎯 Gestion automatique du trade  
📊 Tableau récapitulatif intelligent

---

# 2. 🚀 Installation sur TradingView

## Étape 1 — Ajouter le script

Dans TradingView :

1. Ouvrir un graphique.
2. Cliquer sur **Pine Editor** en bas.
3. Coller le script.
4. Cliquer sur **Ajouter au graphique**.

---

## Étape 2 — Paramètres importants TradingView

Pour que le script fonctionne de manière fluide :

### 📌 Ouvrir les paramètres du graphique
Clique droit → Paramètres

Puis :

---

## 📊 Onglet "Échelle"

✅ Cocher :
- Ajuster les indicateurs à l’échelle

---

## 📈 Onglet "Apparence"

✅ Recommandé :
- Fond sombre
- Bougies classiques

Pourquoi ?
Le script utilise beaucoup de couleurs institutionnelles (teal, rouge, orange).

---

## ⚡ Onglet "Trading"

❌ Désactiver :
- Positions
- Ordres
- Exécutions

Pourquoi ?
Le script gère déjà ses propres niveaux visuels.

---

## 🔔 Alertes TradingView

Pour recevoir les signaux :

1. Appuyer sur `Alt + A`
2. Condition :
   `SMC-AI All-in-One`
3. Sélectionner :
   `SMC-AI Signal`
4. Fréquence :
   ✅ "Une fois par clôture de barre"

⚠️ Très important :
Toujours utiliser **"clôture de barre"** pour éviter les faux signaux intrabar.

---

# 3. 🧠 Mode Simple vs Mode Expert

---

# 🔰 MODE SIMPLE (RECOMMANDÉ)

## À activer si :
- vous débutez,
- vous voulez un graphique propre,
- vous voulez seulement les signaux importants.

### Ce que vous verrez :
✅ SMA 50 / 200  
✅ Signaux BUY / DANGER  
✅ Tableau récapitulatif  
✅ Zones importantes

### Ce qui est caché :
❌ FVG  
❌ Order Blocks détaillés  
❌ BOS / CHoCH visuels  
❌ Swings

---

# 🔬 MODE EXPERT

Pour les utilisateurs avancés.

Affiche :
- structure complète du marché,
- Order Blocks,
- FVG,
- liquidité,
- BOS/CHoCH.

⚠️ Plus puissant mais plus chargé visuellement.

---

# 4. 📊 Comprendre les signaux

---

# 🟢 SIGNAL BUY

Le signal BUY apparaît uniquement si plusieurs confirmations sont réunies.

Le script vérifie :

✅ tendance haussière  
✅ volume fort  
✅ cassure de structure  
✅ retour institutionnel sur OB  
✅ zone Discount  
✅ prix au-dessus de la SMA50

👉 Résultat :
Le signal BUY est volontairement rare mais plus qualitatif.

---

# 🔴 SIGNAL DANGER

Alerte de faiblesse du marché.

Le script détecte :
- cassure de SMA200,
- CHoCH baissier,
- rejet institutionnel,
- volume agressif vendeur.

👉 En pratique :
- éviter les achats,
- sécuriser les profits,
- remonter le stop.

---

# 🎯 SIGNAL TARGET

Le prix a atteint votre Take Profit.

Le script affiche :
- un signal visuel,
- le gain potentiel,
- la validation du trade.

---

# ⚠️ SIGNAL ATTENTION

Simple avertissement.

Le prix arrive dans :
- une résistance,
- une zone Premium,
- un Bear Order Block.

👉 Souvent :
pas idéal pour acheter.

---

# 5. 📏 Réglages recommandés selon votre style

---

# ⚡ Scalping (1m / 5m)

## Réglages :
- Swing Length : `3`
- Min FVG ATR : `0.05`
- Mode Simple : ✅

## Pourquoi ?
Le marché est rapide.
Le script devient plus réactif.

⚠️ Plus de bruit possible.

---

# 📈 Day Trading (15m / 1H)

## Réglages recommandés :
- Swing Length : `5`
- Min FVG ATR : `0.1`
- Trail Stop : ✅

👉 Meilleur équilibre.

---

# 🏦 Swing Trading (4H / Daily)

## Réglages :
- Swing Length : `8 à 10`
- Min FVG ATR : `0.15`
- Trail Stop : ✅

👉 Signaux plus rares mais beaucoup plus solides.

---

# 6. 🧩 Comprendre les éléments du graphique

---

# 📏 SMA 50 / SMA 200

## SMA50 > SMA200
🟢 Marché haussier

## SMA50 < SMA200
🔴 Marché baissier

Le script privilégie les achats dans les tendances haussières.

---

# 🟢 Zone Discount

Zone intéressante pour acheter.

Le prix est considéré "bon marché".

---

# 🔴 Zone Premium

Zone risquée pour acheter.

Le prix est considéré "cher".

---

# 🟦 Order Blocks (OB)

Zones institutionnelles.

Souvent :
- support,
- résistance,
- réaction du prix.

---

# 📊 Fair Value Gaps (FVG)

Zones de déséquilibre.

Le marché revient souvent les combler.

---

# 7. 🎯 Comment utiliser le script concrètement

---

# ✅ Méthode SIMPLE (débutant)

## Étape 1
Activer :
✅ Mode Simple

---

## Étape 2
Attendre :

🟢 BUY actif dans le tableau

ET

🟢 Signal BUY sur le graphique

---

## Étape 3
Entrer votre trade.

Puis renseigner :
- Entry
- Stop
- Target

dans les paramètres du script.

---

## Étape 4
Activer :
✅ Trail Stop

Le script vous aidera automatiquement à :
- sécuriser,
- remonter le stop,
- suivre le trade.

---

## Étape 5
Sortir :
- sur TARGET,
- ou si DANGER apparaît.

---

# 8. 📊 Le panneau récapitulatif (en haut à droite)

Le tableau vous donne :

| Élément | Signification |
|---|---|
| Signal | Situation actuelle |
| Tendance | Bull ou Bear |
| Zone | Discount ou Premium |
| SMA200 | Distance au marché |
| Volume | Force du mouvement |
| OB proche | Zone institutionnelle |
| FVG proche | Déséquilibre proche |
| PnL | Gain/perte actuelle |
| Trail | Niveau du stop conseillé |
| Verdict | Acheter / Attendre |

---

# 9. ⚙️ Réglages recommandés pour de meilleures performances

Pour garder TradingView fluide :

---

## ✅ Recommandé

### Sur le graphique :
- Mode Simple activé
- 1 seul indicateur SMC-AI par graphique
- Timeframes : 5m → Daily

---

## ❌ À éviter

- 10 indicateurs simultanés
- Tick charts
- Trop de scripts SMC ensemble
- Replay ultra rapide avec Mode Expert

---

# 10. 🧠 Conseils importants

---

## ✅ Ce que le script fait bien

- filtrer les faux signaux,
- identifier les zones institutionnelles,
- aider la gestion du risque,
- suivre la tendance.

---

## ❌ Ce qu’il ne faut PAS faire

- acheter chaque signal sans contexte,
- ignorer le stop loss,
- trader contre la tendance,
- utiliser le 1m sans expérience.

---

# 11. 📌 Configuration recommandée pour débuter

## La configuration la plus simple :

| Paramètre | Valeur |
|---|---|
| Mode Simple | ✅ |
| Swing Length | 5 |
| Min FVG ATR | 0.1 |
| SMA | ✅ |
| Trail Stop | ✅ |
| Timeframe | 15m ou 1H |

👉 C’est le meilleur équilibre entre :
- simplicité,
- clarté,
- qualité des signaux.

---

# 12. 🚀 Workflow conseillé

## Avant ouverture :
1. Vérifier le panneau.
2. Vérifier la tendance.
3. Attendre un BUY propre.

---

## Pendant le trade :
1. Remplir Entry / Stop / TP.
2. Laisser le Trail Stop actif.
3. Suivre les alertes.

---

## Après le trade :
1. Analyser :
   - pourquoi le signal a fonctionné,
   - ou échoué.
2. Ajuster les paramètres progressivement.

---

# 13. 🧠 Conseils avancés (mais simples)

Même sans être expert :

✅ privilégier :
- indices,
- grosses actions,
- crypto majeures.

❌ éviter :
- marchés illiquides,
- penny stocks,
- altcoins faibles.

Le script fonctionne mieux là où il y a :
- du volume,
- de la liquidité,
- des mouvements propres.

---

# 14. 📌 Conclusion

SMC-AI v3.1 PRO n’est pas juste un indicateur visuel.

C’est :
- un filtre de contexte,
- un assistant de gestion,
- un système de confirmation,
- un outil de discipline.

Le plus important :
✅ attendre les bons signaux  
✅ respecter le risque  
✅ rester simple au début

Commencez en :
🔰 Mode Simple  
📈 Timeframe 15m ou 1H  
🟢 uniquement les meilleurs BUY signals