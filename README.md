# ImmoRadar Invest

Outil de veille sur les biens **à vendre** dans un rayon de 10 km autour de
Villeneuve-Loubet (06), qui évalue chaque annonce selon **deux stratégies
d'investissement** :

- 🎓☀️ **Location saisonnière** — bail étudiant 8 mois + Airbnb l'été (juin→sept.),
  profil studio/T2. Rendement brut, cash-flow, loyer étudiant et revenu Airbnb estimés.
- 🏗️ **Marchand de biens** — achat / (division) / travaux / revente. Marge estimée,
  scénarios de négociation (-5 / -10 / -15 %), potentiel de division, et rendement
  locatif classique en alternative.

Sources : Leboncoin · PAP · SeLoger · Bien'ici. Aucune clé d'API n'est nécessaire.

---

## Lancer l'outil (sans terminal)

1. **Télécharger le projet** : sur la page GitHub du dépôt, bouton vert **`Code`**
   → **`Download ZIP`**. Décompressez le dossier où vous voulez.
2. **Double-cliquer sur le lanceur** correspondant à votre machine :
   - macOS → `Lancer-ImmoRadar-macOS.command`
   - Windows → `Lancer-ImmoRadar-Windows.bat`
3. Une fenêtre s'ouvre, installe ce qu'il faut au premier lancement (~1 min),
   puis **le navigateur s'ouvre automatiquement** sur `http://localhost:3000`.

**Gardez la fenêtre ouverte** tant que vous utilisez l'outil (c'est elle qui fait
tourner le serveur). Pour arrêter : fermez-la.

> **Prérequis unique** : Python 3 doit être installé. Si ce n'est pas le cas, le
> lanceur vous l'indique avec le lien de téléchargement
> ([python.org/downloads](https://www.python.org/downloads/)).
> Sur Windows, pensez à cocher **« Add Python to PATH »** pendant l'installation.

**Au premier lancement**, la page peut être vide 1 à 2 minutes : le serveur
interroge les 4 sites. Elle se remplit toute seule (rafraîchissement auto).

### macOS : « impossible d'ouvrir car il provient d'un développeur non identifié »

Clic **droit** sur le fichier `.command` → **Ouvrir** → **Ouvrir** dans la boîte de
dialogue. À faire une seule fois.

---

## Utilisation

- **Les deux onglets en haut** basculent entre les deux stratégies : les mêmes
  annonces, mais triées et évaluées selon la logique de chaque stratégie.
- **Vue Liste / Carte** : la carte colore chaque bien selon son score.
- **Filtres** : prix max, surface min, type (appartement/maison), nouveautés.
- **Cliquer sur une annonce** déplie le détail (calculs, scénarios de négociation,
  état détecté, potentiel de division).
- Le badge vert **NOUVEAU** signale une annonce vue pour la première fois il y a
  moins de 24 h.

---

## Régler les critères

Tout est dans `config.py` (ouvrable avec n'importe quel éditeur de texte) :
zone et rayon, plafond de prix, durée des baux, taux d'occupation Airbnb,
paramètres du crédit, coûts de travaux au m².

Les références de marché par commune (prix de revente, loyers, tarifs Airbnb)
sont dans `references.py`, et la liste des communes surveillées dans `zones.py`.

⚠️ **Ces valeurs sont des ordres de grandeur de départ**, pas des données
mesurées : l'estimation de l'état d'un bien se fait par mots-clés dans l'annonce
(« à rénover », « refait à neuf »…) complétée par le DPE. C'est la partie destinée
à être remplacée par un modèle entraîné. Les marges et rendements affichés sont
donc des **indications de tri**, à vérifier bien par bien avant toute décision.

---

## Vérifier que les sources répondent

En cas de doute (aucune annonce, une source à zéro), un script de diagnostic
affiche pour chaque site le code HTTP, le nombre d'annonces récupérées et un
échantillon :

```
python3 test_scrapers.py            # les 4 sources
python3 test_scrapers.py leboncoin  # une seule
```

Les sites changent régulièrement leur structure et leurs protections anti-robot ;
**SeLoger est la source la plus fragile** (captcha fréquent) — elle se désactive
proprement pour le cycle sans empêcher les trois autres de fonctionner.

---

## Hébergement en ligne (optionnel)

Un `Procfile` est présent pour un déploiement type Render/Heroku, mais **ce n'est
pas recommandé ici** : depuis une IP de datacenter, les sites immobiliers bloquent
beaucoup plus agressivement le scraping, et les offres gratuites effacent le disque
à chaque redémarrage — ce qui ferait perdre l'historique des annonces déjà vues,
donc la détection des nouveautés. Une exécution depuis votre machine donne de
bien meilleurs résultats.
