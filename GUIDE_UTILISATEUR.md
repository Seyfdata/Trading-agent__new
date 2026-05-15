# Guide Utilisateur — SMC-AI Trading Agent v2

> **Pour qui ?** Ce guide s'adresse à un utilisateur qui débute en trading. Aucune connaissance préalable n'est nécessaire pour suivre les étapes.

> ⚠️ **Avertissement** : Le trading comporte des risques de perte en capital. Cet outil propose des analyses, mais **l'humain décide toujours**. Ne risque jamais d'argent que tu ne peux pas te permettre de perdre.

---

## Table des matières

1. [C'est quoi ce dashboard ?](#1-cest-quoi-ce-dashboard)
2. [Lancer l'application](#2-lancer-lapplication)
3. [Routine quotidienne — vue d'ensemble](#3-routine-quotidienne)
4. [Onglet Vue d'ensemble](#4-onglet-vue-densemble)
5. [Onglet Coach ← commencer ici](#5-onglet-coach)
6. [Onglet Propositions](#6-onglet-propositions)
7. [Onglet Watchlist](#7-onglet-watchlist)
8. [Onglet Pullback Scanner](#8-onglet-pullback-scanner)
9. [Onglet RS Scout](#9-onglet-rs-scout)
10. [Onglet Setups](#10-onglet-setups)
11. [Onglet Analyse SMC](#11-onglet-analyse-smc)
12. [Onglet Reddit](#12-onglet-reddit)
13. [Onglet News](#13-onglet-news)
14. [Onglet Alertes](#14-onglet-alertes)
15. [Onglet Journal](#15-onglet-journal)
16. [Onglet Performance](#16-onglet-performance)
17. [Workflow complet d'une journée de trading](#17-workflow-complet)
18. [Les 7 règles d'or — à ne jamais violer](#18-les-7-règles-dor)
19. [Cheat sheet : du signal au trade](#19-cheat-sheet)
20. [Problèmes fréquents](#20-problèmes-fréquents)

---

## 1. C'est quoi ce dashboard ?

Le **SMC-AI Trading Agent** est un cockpit de trading personnel. Il tourne entièrement sur ton ordinateur, ne coûte rien à utiliser (0 € / mois), et scanne automatiquement 22 actions US pour détecter des opportunités de trading.

**Ce que fait l'outil :**
- Surveiller le marché en temps réel (SPY, VIX, tendances)
- Classer les meilleures actions à surveiller
- Détecter des signaux d'achat potentiels
- Calculer automatiquement les niveaux d'entrée, stop loss et cible
- Calculer combien d'actions acheter pour ne pas dépasser 1 % de risque
- Journaliser tes trades et mesurer ta performance

**Ce que l'outil ne fait PAS :**
- Passer des ordres à ta place (tu restes aux commandes)
- Garantir des gains (aucun outil ne peut le faire)
- Remplacer ton jugement

---

## 2. Lancer l'application

Double-clique sur **`launch_dashboard.bat`** dans le dossier du projet.

Une fenêtre noire s'ouvre, puis le navigateur se lance automatiquement sur `http://localhost:8000`.

> Si le navigateur ne s'ouvre pas tout seul, ouvre-le manuellement et tape `http://localhost:8000` dans la barre d'adresse.

> Si tu vois une erreur, lis la section [Problèmes fréquents](#20-problèmes-fréquents).

---

## 3. Routine quotidienne

Le dashboard est conçu pour être utilisé en 3 temps dans la journée :

### 🌅 Le matin (9h–12h) — 20 à 30 minutes

1. Lance le dashboard
2. Regarde l'onglet **Vue d'ensemble** : le marché est-il favorable ?
3. Vérifie l'onglet **News** : y a-t-il une annonce macro aujourd'hui (FOMC, NFP, CPI) ?
4. Si oui → **NO TRADE pour la journée entière**
5. Si non → prépare tes candidats

### 🎯 Avant la killzone (14h–14h30) — 10 minutes

La « killzone » est la fenêtre optimale pour trader : **14h30–16h30 heure française (CET)**.  
C'est l'ouverture de Wall Street, le moment où les volumes sont les plus forts.

1. Ouvre **Pullback Scanner** → quels tickers sont en survente ?
2. Croise avec **RS Scout** → lesquels surperforment le marché ?
3. Vérifie les **Setups** → y a-t-il un signal valide ?
4. Analyse le meilleur candidat dans **Analyse SMC**
5. Choisis **UN seul ticker** — celui avec le meilleur setup

### 🔴 Killzone (14h30–16h30) — trade ou attente

1. Attends que le prix arrive sur la zone d'entrée
2. Vérifie qu'il n'y a pas de news de dernière minute
3. Passe l'ordre sur IBKR (bracket order : entrée + stop + cible)
4. Surveille, mais **n'interviens pas sans raison**

### 🌙 Post-market (après 22h) — 5 minutes

1. Clôture tes trades ouverts dans le **Journal**
2. Note ce qui s'est bien ou mal passé

---

## 4. Onglet Vue d'ensemble

C'est le **tableau de bord principal**. Il s'affiche en premier quand tu ouvres le dashboard.

### Régime du marché

Le dashboard calcule automatiquement si le marché est en mode :

| Régime | Signification | Action |
|--------|--------------|--------|
| ✅ **BULL** | Tendance haussière — contexte favorable | Tu peux chercher des trades |
| ⚠️ **NEUTRAL** | Indécis — prudence | Risque réduit de moitié |
| 🔴 **BEAR** | Tendance baissière — contexte défavorable | **NO TRADE** |

### Le VIX — indicateur de peur du marché

Le VIX mesure la nervosité des investisseurs :

| VIX | Signification |
|-----|--------------|
| < 20 | ✅ Calme — bonnes conditions |
| 20–30 | ⚠️ Prudence — risque modéré |
| > 30 | 🔴 Danger — évite de trader |

### Top 3 du jour

Le dashboard affiche les 3 meilleures opportunités du moment selon un score composite 0–100. Ce ne sont que des suggestions — vérifie toujours dans les onglets dédiés avant d'agir.

### Verdict GO / NO TRADE

Un encadré en haut de l'écran te donne le verdict immédiat :
- **✅ JOURNÉE FAVORABLE** → tu peux chercher des trades
- **⚠️ JOURNÉE PRUDENTE** → réduis ton risque à 0.5 % par trade
- **🚫 NO TRADE** → ne trade pas, quelle que soit l'opportunité

---

## 5. Onglet Coach

> **Si tu démarres, commence toujours par l'onglet Coach.**

Le Coach est un assistant pas-à-pas qui te guide à travers les 5 étapes d'un trade. Il t'empêche d'oublier des étapes importantes.

### Barre de temps de la journée

En haut du Coach, une barre visuelle indique où tu en es dans la journée :

```
☀️ PRÉ-MARCHÉ ————————————— 🔴 KILLZONE 14h30–16h30 ————————————— 🌙 CLÔTURE
```

Un curseur blanc se déplace en temps réel. C'est utile pour savoir combien de temps il te reste avant la killzone.

### Les 5 étapes du Coach

**Étape 1 — Mettre à jour les données**
Clique sur "Rafraîchir maintenant". Le dashboard scanne le marché (30–60 secondes). Quand c'est fait, passe à l'étape suivante.

**Étape 2 — Trouver les meilleures opportunités**
Clique sur "Scanner maintenant". Le Coach affiche les setups du jour avec :
- Le ticker (ex : NVDA, AAPL)
- Le **Grade** : A+ ou A = excellent, B = correct, C = à éviter
- Le **score 0–10** : plus c'est élevé, plus le setup est fort
- Les niveaux de trade : entrée, stop loss, cible, nombre d'actions
- Les raisons positives et négatives

**Étape 3 — Vérifier sur TradingView**
Ouvre le graphique du ticker sur TradingView (lien fourni) et vérifie visuellement que le setup a du sens.  
Coche les 4 cases de validation :
- [ ] Tendance confirmée
- [ ] Zone d'entrée visible sur le graphique
- [ ] Stop loss logique (sous un support)
- [ ] Cible réaliste (résistance visible)

**Étape 4 — Passer l'ordre sur IBKR**
Le Coach te donne les instructions exactes pour créer un bracket order sur Interactive Brokers :
- Prix d'achat limite
- Stop loss automatique
- Take profit automatique

**Étape 5 — Enregistrer dans le Journal**
Note le trade dans l'onglet Journal pour pouvoir mesurer ta performance sur la durée.

---

## 6. Onglet Propositions

> **Le point d'entrée idéal pour un débutant.**

L'onglet Propositions fait tout le travail à ta place. Il analyse l'ensemble de la watchlist et te présente directement les meilleurs trades du moment.

### Comment l'utiliser

1. Entre ton capital disponible (ex : 10 000 €)
2. Clique sur **"🎯 Analyser les meilleures opportunités"**
3. Attends 30–60 secondes
4. Lis les cartes de propositions

### Lire une carte de proposition

Chaque carte contient :

```
NVDA  ★★★★☆  Grade B
━━━━━━━━━━━━━━━━━━━━━━
💰 Acheter à : 875,00 $
🛑 Stop loss  : 848,75 $   (perte max : 52 $)
🎯 Cible      : 940,63 $   (gain potentiel : 131 $)
📦 Quantité   : 2 actions — investissement : 1 750 $
📊 R:R : 2.5×
```

**Explication des niveaux :**

- **Acheter à** : prix auquel tu passes l'ordre d'achat (ordre limite)
- **Stop loss** : niveau auquel tu vends automatiquement si ça tourne mal — limite ta perte
- **Cible (TP)** : niveau où tu prends tes bénéfices
- **R:R (Risk/Reward)** : ratio gain potentiel / perte potentielle. **Minimum 2.5** — si la cible vaut 2.5× le risque, le trade vaut la peine même avec 50 % de succès

**Les étoiles :**
- ★★★★★ = Grade A+ (setup exceptionnel)
- ★★★★☆ = Grade A (très bon)
- ★★★☆☆ = Grade B (correct)
- ★★☆☆☆ = Grade C (faible)

### Boutons d'action

- **🧠 Analyser SMC** → ouvre l'analyse détaillée du ticker
- **📝 → Journal** → pré-remplit le formulaire du journal pour enregistrer ce trade

---

## 7. Onglet Watchlist

La watchlist contient les 22 actions US suivies en permanence par le dashboard.

### Score composite 0–100

Chaque ticker reçoit un score calculé automatiquement :

| Score | Signification |
|-------|--------------|
| 0–40 | ⬜ Faible — à ignorer |
| 40–60 | 🔵 Moyen — surveillance |
| 60–75 | 🟡 Intéressant — à surveiller |
| 75–100 | 🟢 Opportunité — à analyser |

### Les barres SHAP

Quand tu cliques sur un ticker, des barres colorées apparaissent. Elles montrent **pourquoi** le score est élevé :

```
Score 85 = SMA200: +25 | Volume: +18 | Reddit: +20 | News: +22
```

- **SMA200** : le prix est au-dessus de la moyenne long terme → signal positif
- **Volume** : les volumes sont anormalement élevés → signe d'intérêt institutionnel
- **Reddit** : le ticker est beaucoup mentionné sur les réseaux → buzz
- **News** : des actualités positives circulent

### Bouton "🧠 Analyser SMC →"

Présent sur chaque ticker. Clique dessus pour basculer directement vers l'analyse complète.

---

## 8. Onglet Pullback Scanner

Le Pullback Scanner détecte les actions qui ont **trop baissé** et qui pourraient rebondir.

### Comment ça fonctionne

L'algorithme vérifie 3 indicateurs de survente :

```
RSI < 35      → L'action a trop baissé (indicateur de momentum)
BB%B < 0      → Le prix est sous la bande basse de Bollinger
Stoch < 20    → Le stochastique est en zone de survente
```

> **C'est quoi le RSI ?** C'est un chiffre entre 0 et 100 qui mesure si une action est survendue (< 35) ou surachetée (> 70). En dessous de 35, l'action a souvent baissé trop vite et pourrait rebondir.

### Les 4 statuts

| Statut | Signification |
|--------|--------------|
| 🚨 **Alert** | 2 ou 3 critères déclenchés → survente confirmée |
| 👁 **Watch** | 1 critère déclenché → signal faible, surveille |
| ⬜ **Neutral** | Aucun critère → rien à faire |
| 📈 **Overbought** | RSI > 70 → l'action a trop monté, évite |

### Breadth du S&P 500

En haut du scanner, un indicateur montre l'état général des 50 premières actions du S&P 500. Si le marché global est haussier (BULLISH) **et** qu'un ticker est en alerte, le rebond est plus probable.

### Pièges à éviter

> ⚠️ **Survente en marché baissier = couteau qui tombe**  
> Si le régime général est BEAR, ne pas acheter même si le RSI est < 35.  
> Attends toujours une confirmation technique (voir Analyse SMC).

---

## 9. Onglet RS Scout

RS Scout classe les tickers par **force relative** par rapport au marché (SPY).

### C'est quoi l'alpha ?

L'alpha mesure à quel point un titre fait mieux que le marché général :

```
Alpha sur 1 mois = performance du ticker - performance de SPY
Exemple : NVDA +16% - SPY +4% = alpha +12%
```

Un alpha positif signifie que l'action bat le marché. C'est exactement le genre de titre qu'on cherche : fort dans un marché fort.

### Les verdicts

| Verdict | Alpha | Signification |
|---------|-------|--------------|
| 🟢 **Outperforming** | > +2 % | Plus fort que le marché |
| ⬜ **In line** | -2 % à +2 % | Suit le marché |
| 🔴 **Underperforming** | < -2 % | Plus faible que le marché |

### Périodes disponibles

Utilise le sélecteur pour changer la période d'analyse :
- **1W** (1 semaine) : momentum très court terme
- **1M** (1 mois) : momentum court terme ← le plus utilisé
- **3M** (3 mois) : tendance structurelle

### Deep Analysis — comment lire les indicateurs

Pour les meilleures actions du classement, le dashboard affiche une analyse approfondie :

```
✅ ADX > 25   → Tendance forte, momentum intact
✅ Short < 3% → Peu de pression vendeuse
⚠️ RSI > 70   → Surachat — zone d'entrée risquée
⚠️ BB%B > 1   → Prix au-dessus de la bande supérieure — possible repli
```

**Candidat idéal :** alpha fort + ADX > 25 + RSI < 65 + short intérêt faible

> ⚠️ Un ticker en tête du RS Scout peut être "trop cher" si le RSI dépasse 75.  
> Dans ce cas, préfère le 2e ou le 3e du classement.

---

## 10. Onglet Setups

L'onglet Setups détecte automatiquement 3 types de configurations sur la watchlist.

### Les 3 types de setups

**DISCOUNT_ZONE** — Prix en zone de valeur
Le prix est sous le milieu du range récent (les 50 derniers jours). On achète "en soldes".

**SMA200_BOUNCE** — Rebond depuis la moyenne long terme
Le prix est revenu toucher la SMA200 (moyenne mobile sur 200 jours) avec un volume anormal. Signal fiable : les grands investisseurs défendent ce niveau.

**VOLUME_MOMENTUM** — Volume explosif avec prix haussier
Les volumes sont 2× supérieurs à la normale et le prix monte. Signe que des institutions achètent massivement.

> ✅ **Signal le plus fiable** : SMA200_BOUNCE + VOLUME_MOMENTUM ensemble sur le même ticker.

### Position sizing automatique

Entre ton capital dans le champ prévu. Le dashboard calcule automatiquement combien d'actions acheter pour ne jamais risquer plus de 1 % de ton capital par trade.

Exemple avec 10 000 € :
```
Capital : 10 000 €
Risque max par trade : 1 % = 100 €
Entry : 875 $ | Stop : 850 $ → risque/action = 25 $
Shares à acheter = 100 / 25 = 4 actions
```

---

## 11. Onglet Analyse SMC

L'onglet le plus puissant du dashboard. Il applique les **Smart Money Concepts** — une méthode d'analyse qui cherche à reproduire les mouvements des grands investisseurs institutionnels.

### Les concepts SMC expliqués simplement

**BOS — Break of Structure** *(Cassure de structure)*  
Quand le prix dépasse un sommet précédent, la tendance est confirmée haussière. C'est le signal que les "grands" sont en train d'acheter.

**CHoCH — Change of Character** *(Changement de caractère)*  
Quand la tendance s'inverse. Signal d'alerte : les institutions ont peut-être changé de camp.

**Order Block (OB)** *(Bloc d'ordres)*  
Zone de prix où les institutions ont acheté massivement. Souvent, le prix revient sur ces zones pour "recharger". C'est là qu'on cherche à entrer.

**FVG — Fair Value Gap** *(Déséquilibre)*  
Écart entre deux bougies qui n'a pas encore été "comblé". Le prix a tendance à revenir combler ces zones.

**Discount Zone** *(Zone de valeur)*  
La partie basse du range de prix. Acheter dans le discount, c'est acheter en soldes.

**Liquidity (BSL/SSL)** *(Liquidité)*  
Niveaux de prix où beaucoup d'ordres stop sont placés. Les institutions "chassent" ces stops pour récupérer de la liquidité avant un mouvement fort.

### Comment lire le score unifié 0–10

| Score | Grade | Signification |
|-------|-------|--------------|
| 8–10 | **A+** | Setup exceptionnel — fonce avec conviction |
| 6–8 | **A** | Très bon setup — trade normal |
| 4–6 | **B** | Setup correct — réduis le risque de moitié |
| 2–4 | **C** | Setup faible — mieux vaut passer |
| < 2 | **NO TRADE** | Pas de setup valide |

### Mode Simple vs Mode Expert

- **Mode Simple** : les indicateurs clés — biais BULL/BEAR, zone, niveaux de trade. Parfait pour démarrer.
- **Mode Expert** : structure complète, options flow, toutes les confluences. Pour les traders avancés.

### R:R validé ≥ 2.5

Le dashboard **rejette ou ajuste automatiquement** les setups où le ratio gain/risque est inférieur à 2.5. Si tu vois "Target ajusté", c'est normal : le niveau initial était trop proche et a été recalculé.

> ✅ **Setup valide :** biais BULL + prix en DISCOUNT + Bull OB non mitigé + R:R ≥ 2.5

---

## 12. Onglet Reddit

Le dashboard surveille Reddit (r/wallstreetbets, r/stocks, etc.) sans API payante.

### Deux sections

**Mentions watchlist** : nombre de fois qu'un ticker de ta watchlist est cité aujourd'hui. Signal de buzz social, pas un signal technique.

**Trouvailles** : tickers hors watchlist qui font parler d'eux. Peuvent mériter une analyse rapide avec le bouton "Analyser SMC".

### Piège à éviter

> ⚠️ Un ticker très mentionné sur Reddit peut être en train de monter avant de s'effondrer.  
> Utilise Reddit comme **confirmation supplémentaire** uniquement, jamais comme signal principal.

---

## 13. Onglet News

Le dashboard agrège automatiquement les actualités financières depuis CNBC, Reuters, Bloomberg, le SEC et la Fed.

### Filtrage automatique

Les news sont filtrées par ticker et par événements macro. Tu vois uniquement ce qui concerne ta watchlist.

### Breaking news — 30 minutes

Alerte sur les nouvelles parues dans les 30 dernières minutes. **Vérifie toujours cette section avant chaque trade.**

> ⚠️ **Règle absolue** : aucun trade dans les 30 minutes avant ou après une annonce macro (FOMC, NFP, CPI, résultats trimestriels).

### Événements macro à connaître

| Événement | Fréquence | Impact |
|-----------|-----------|--------|
| **FOMC** | 8 fois/an | Décisions taux Fed — très fort |
| **NFP** | 1er vendredi du mois | Emploi US — fort |
| **CPI** | Mensuel | Inflation US — fort |
| **Earnings** | Trimestriel | Résultats d'entreprise — fort |

---

## 14. Onglet Alertes

### Killzone live

Une barre rouge pulsante s'allume quand tu es entre 14h30 et 16h30 CET. Un compteur indique combien de temps il reste.

### Alertes positions

Si tu as des positions ouvertes enregistrées dans le Journal, le dashboard te prévient quand :
- Le prix approche du stop loss (danger)
- Le prix approche de la cible (bientôt le moment de sortir)

### Alertes automatiques

Le dashboard détecte en temps réel sur les tickers de la watchlist :
- Volume anormal (× 2 ou plus)
- Franchissement de la SMA200
- Mouvement de prix significatif

---

## 15. Onglet Journal

Le Journal est l'outil le plus important pour progresser sur le long terme. Il te permet de mesurer ta performance réelle.

### Enregistrer un trade

Remplis les champs :
- **Ticker** : l'action achetée (ex : NVDA)
- **Setup type** : DISCOUNT_ZONE, SMA200_BOUNCE ou VOLUME_MOMENTUM
- **Direction** : LONG (achat)
- **Entry** : prix d'achat
- **Stop** : niveau de stop loss
- **Target** : niveau de cible
- **Shares** : nombre d'actions

Le R:R est calculé automatiquement. S'il apparaît en **rouge**, c'est que le ratio est < 2.5 — repousse le target ou annule le trade.

### Suivi des positions ouvertes

Le dashboard affiche le PnL en temps réel, la distance au stop et à la cible pour chaque position ouverte.

### Clôturer un trade

Quand tu as vendu, clique sur "Clôturer" et entre le prix de sortie. Le PnL final est calculé automatiquement en dollars et en R:R réalisé.

> ✅ **Objectif** : utilise le journal dès le premier trade. Plus tu enregistres, plus les métriques de performance sont précises.

---

## 16. Onglet Performance

Tableau de bord complet de ta performance sur l'ensemble des trades enregistrés.

### Métriques disponibles

| Métrique | Ce que ça mesure |
|----------|-----------------|
| **Equity curve** | Courbe de ton PnL cumulé — doit monter de gauche à droite |
| **Heatmap mensuel** | PnL par mois — vert = mois gagnant, rouge = mois perdant |
| **Drawdown** | Perte maximale depuis le point le plus haut — à minimiser |
| **Win rate** | Pourcentage de trades gagnants |
| **Profit factor** | Gains totaux / pertes totales — doit être > 1.5 |
| **Sharpe ratio** | Rendement ajusté au risque — doit être > 1.0 |
| **Monte Carlo** | Simulation de 1000 scénarios futurs — montre les risques possibles |

### Edge tracker par setup

Le dashboard analyse tes résultats **par type de setup**. Tu verras quel type de configuration fonctionne le mieux pour toi personnellement.

### Objectifs minimum à atteindre

```
Sharpe ratio   > 1.0
Win rate       > 40 %  (avec R:R 2.5, c'est suffisant pour être profitable)
Profit factor  > 1.5
```

### Backtest 3 stratégies

Le dashboard peut tester tes stratégies sur des données historiques pour valider si ton edge est réel avant de risquer de l'argent réel.

---

## 17. Workflow complet

Voici la séquence exacte d'une bonne journée de trading :

```
MATIN (9h–12h)
─────────────────────────────────────────────────────
1. Lance le dashboard (double-clic launch_dashboard.bat)
2. Vue d'ensemble → Régime BULL ? VIX < 20 ?
3. News → Événement macro aujourd'hui ?
   Si OUI → NO TRADE, ferme le dashboard, reviens demain
4. Verdict GO → continuer | NO TRADE → repos

AVANT KILLZONE (14h–14h30)
─────────────────────────────────────────────────────
5. Pullback Scanner → tickers en alert ou watch ?
6. RS Scout → croiser avec les outperformers (alpha > +2 %)
7. Setups → y a-t-il un setup valide sur le(s) ticker(s) retenus ?
8. Analyse SMC → R:R ≥ 2.5 ? Biais BULL ? OB actif ?
9. Choisir UN seul ticker — le meilleur setup uniquement

KILLZONE (14h30–16h30)
─────────────────────────────────────────────────────
10. Attends que le prix arrive sur la zone d'entrée (OB ou FVG)
11. Vérifie breaking news dans les 30 min
12. Passe l'ordre sur IBKR : bracket order entry / stop / target
13. Surveille — n'interviens pas sans raison valable

POST-MARKET (après 22h)
─────────────────────────────────────────────────────
14. Clôture les trades fermés dans le Journal
15. Note tes observations de la journée
```

> ✅ Ce workflow prend **20–30 min le matin + 10 min avant la killzone + 5 min post-market**.

---

## 18. Les 7 règles d'or

Ces règles ne sont pas négociables. Les violer garantit des pertes à long terme.

### 1. R:R minimum 1:2.5 🔴

> Le dashboard rejette automatiquement les setups qui ne respectent pas ce ratio. Ne jamais forcer un trade en dessous de 2.5.

Si ton stop est à 10 $ de l'entrée, ta cible doit être à **minimum 25 $** de l'entrée.  
Pourquoi ? Parce que même avec seulement 40 % de trades gagnants, tu es profitable avec un R:R de 2.5.

### 2. Maximum 2 trades par jour 🟡

Au-delà, la qualité de décision baisse fortement. Mieux vaut rater une opportunité que forcer un mauvais trade.

### 3. Risque 0.5–1 % par trade maximum 🟡

Avec 10 000 € de capital : risque max = **100 €** par trade.  
Le journal calcule automatiquement le nombre d'actions pour respecter ce seuil.

### 4. Exposition maximum 3 % simultané 🟡

Si tu as 2 positions ouvertes à 1 % chacune, tu ne peux pas en ouvrir une 3e (total > 3 %).

### 5. Killzone 14h30–16h30 CET uniquement 🔵

Hors killzone, les spreads sont plus larges et les mouvements plus erratiques. Ne jamais trader hors de cette fenêtre.

### 6. Zéro trade avant FOMC / NFP / CPI / earnings 🔴

Les annonces macro créent des sauts de prix imprévisibles. Le calendrier macro est visible dans l'onglet News.

### 7. Long only — actions US uniquement ⬜

Compte cash IBKR. Pas de short, pas de levier, pas de crypto, pas de forex, pas d'options.

---

## 19. Cheat sheet

### Filtres à passer avant chaque trade

```
[1] PULLBACK SCANNER  →  Alert ou Watch ? + marché BULLISH ?
       ↓ OUI : ticker retenu

[2] RS SCOUT          →  Alpha 1M > +2 % + ADX > 25 + short < 5 % ?
       ↓ OUI : candidat fort

[3] SETUP DETECTOR    →  DISCOUNT_ZONE ou SMA200_BOUNCE détecté ?
       ↓ OUI : setup validé

[4] ANALYSE SMC       →  BOS BULL + OB actif + R:R ≥ 2.5 ?
       ↓ OUI : setup tradeable

[5] IBKR BRACKET      →  Entry limit + Stop loss + Take profit
```

### Arbre de décision

```
À chaque étape :
  SI non → WAIT (ticker éliminé pour cette session)
  SI oui → passer à l'étape suivante
  SI doute → aller dans l'onglet Coach pour vérification

Résultat :
  0/4 étapes → NO TRADE (journée repos)
  2/4 étapes → WATCH uniquement
  3/4 étapes → Analyser en profondeur
  4/4 étapes → Trade avec conviction
```

> ✅ **Un trade raté est une perte de 0 €. Un mauvais trade peut être −100 €.  
> Attendre est toujours la meilleure option par défaut.**

---

## 20. Problèmes fréquents

### Le dashboard ne se lance pas

**Symptôme** : la fenêtre noire s'ouvre puis se ferme immédiatement.

**Solution** :
1. Ouvre PowerShell dans le dossier du projet
2. Tape : `python launch_dashboard.py`
3. Lis le message d'erreur qui apparaît

### Erreur "No module named ..."

**Solution** : le `.venv` n'est pas activé. Lance le dashboard via `launch_dashboard.bat` (ne pas utiliser directement `python`).

### Port 8000 déjà utilisé

**Symptôme** : `Address already in use` dans les logs.

**Solution** :
```
tasklist | findstr python
taskkill /PID <le_numero> /F
```
Puis relance le dashboard.

### Le dashboard s'ouvre mais les données ne se chargent pas

**Solution** : clique sur le bouton **"🔄 Rafraîchir"** dans l'onglet Coach ou en haut du dashboard.

### Les données sont vieilles

Le dashboard cache les données pendant 5 minutes. Clique sur Rafraîchir pour forcer une mise à jour.

---

## Glossaire rapide

| Terme | Définition simple |
|-------|------------------|
| **RSI** | Indicateur de survente/surachat (0–100). < 35 = possible rebond |
| **SMA200** | Moyenne mobile sur 200 jours. Support/résistance majeur |
| **Bollinger** | Bandes qui entourent le prix. Sortir par le bas = survente |
| **ADX** | Force de la tendance. > 25 = tendance forte |
| **MACD** | Croisement = changement de momentum |
| **BOS** | Le prix dépasse un sommet → tendance confirmée |
| **OB** | Zone où les institutions ont acheté — zone d'entrée |
| **FVG** | Vide de prix que le marché tendra à combler |
| **R:R** | Ratio gain potentiel / perte potentielle (min 2.5) |
| **Alpha** | Performance d'une action moins la performance du marché |
| **Killzone** | 14h30–16h30 CET — fenêtre optimale de trading |
| **Bracket order** | Ordre d'achat avec stop et target automatiques |
| **SPY** | ETF qui réplique le S&P 500 — le "marché" de référence |
| **VIX** | Indice de peur du marché. < 20 = calme |

---

*Guide mis à jour : mai 2026 — SMC-AI Trading Agent v2*
