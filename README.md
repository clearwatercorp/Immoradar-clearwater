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

> **⚠️ À lire si vous hébergez l'outil en ligne.** Leboncoin (DataDome), PAP et
> SeLoger (Cloudflare) bloquent les adresses IP de **datacenter** dès la première
> requête — c'est le cas de tous les hébergeurs (Render, etc.). Depuis un
> hébergeur, **seule Bien'ici répond** sans configuration. Pour débloquer les
> trois autres **gratuitement**, une clé Scrapfly suffit (compte gratuit, 1000
> requêtes/mois) — voir [Débloquer les 4 sources](#débloquer-les-4-sources-gratuit).
> En local (option B), depuis votre connexion personnelle, les quatre sources
> fonctionnent sans rien configurer.

---

## Option A — En ligne, sans rien installer (accès PC + téléphone)

À privilégier si vous ne pouvez rien installer sur votre machine, ou si vous
voulez consulter depuis votre téléphone. Tout se fait au navigateur.

1. Créer un compte gratuit sur [render.com](https://render.com) (connexion via GitHub).
2. **`New +`** → **`Blueprint`** → sélectionner ce dépôt → **`Apply`**.
   Render lit le fichier `render.yaml` et configure tout seul.
3. Au bout de quelques minutes, une URL du type `https://immoradar-xxxx.onrender.com`
   est disponible : ouvrez-la sur PC **et** sur téléphone (l'interface s'adapte).
4. Dans l'interface, le bouton **« Rechercher »** interroge les 4 sites **à la
   demande** ; la page suit l'avancement et se remplit toute seule.

**Ce qu'il faut savoir sur le plan gratuit :**

| Limite | Conséquence concrète |
|---|---|
| Mise en veille après ~15 min sans visite | La 1ʳᵉ ouverture prend ~30 s à se réveiller |
| Disque effacé à chaque redémarrage | L'historique des annonces vues repart de zéro, donc tout réapparaît en « NOUVEAU » |
| IP de datacenter | Les sites immobiliers bloquent plus volontiers qu'une connexion perso — certaines sources peuvent renvoyer 0 annonce |

Le plan payant « starter » (~7 $/mois) + un disque persistant supprime les deux
premières limites. La troisième (IP de datacenter) se règle avec un proxy
résidentiel — voir ci-dessous.

> L'URL Render est publique (non indexée mais accessible à qui la connaît). Les
> données affichées sont des annonces immobilières publiques ; demandez-moi si
> vous souhaitez malgré tout protéger l'accès par un mot de passe.

---

## Débloquer les 4 sources (gratuit)

En hébergement, Leboncoin, PAP et SeLoger refusent l'IP de datacenter. La solution
la plus simple et **gratuite** est de faire passer ces requêtes par **Scrapfly**,
un service qui franchit ces protections via ses propres IP résidentielles. Son
palier gratuit (1000 requêtes/mois, **sans carte bancaire**, renouvelé chaque mois)
suffit largement pour un usage « je rafraîchis de temps en temps ».

**Mise en place (3 minutes, une seule fois) :**

1. Créer un compte gratuit sur **[scrapfly.io](https://scrapfly.io)**.
2. Dans le tableau de bord Scrapfly, copier la **clé d'API** (*API Key*).
3. Dans Render : **Dashboard → votre service → Environment → Add Environment
   Variable**, clé `SCRAPFLY_KEY`, valeur = la clé copiée. Enregistrer (le service
   redémarre tout seul).
4. Ouvrir l'outil, cliquer **Rechercher** : les quatre sources répondent.

C'est tout. Bien'ici continue de passer en direct (elle ne consomme aucun crédit
Scrapfly) ; seules les trois sources protégées utilisent Scrapfly. Vous pouvez
suivre votre consommation sur le tableau de bord Scrapfly — un rafraîchissement
complet coûte quelques dizaines de crédits, soit largement dans les 1000/mois pour
une consultation occasionnelle.

Laisser `SCRAPFLY_KEY` vide revient au comportement sans clé (seule Bien'ici répond
en hébergement ; les quatre fonctionnent en local).

> **Pourquoi c'est nécessaire.** Les protections anti-robot (DataDome pour
> Leboncoin, Cloudflare pour PAP/SeLoger) classent les plages d'adresses de
> datacenter comme « robot » avant même de lire la requête. Aucune technique de
> scraping ne contourne ça depuis un hébergeur ; il faut passer par une IP
> résidentielle — ce que fait Scrapfly. C'est aussi pourquoi **en local, tout
> fonctionne sans clé** : votre connexion personnelle est déjà résidentielle.

> **Alternative :** si vous disposez déjà d'un **proxy résidentiel**, vous pouvez
> le renseigner dans la variable `PROXY_URL`
> (`http://identifiant:motdepasse@hote:port`) au lieu de Scrapfly.

---

## Option B — En local (sans terminal, mais Python requis)

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
- **Bouton « Rechercher »** : interroge les 4 sites **à la demande** (compter 1 à
  2 min). La page affiche « Recherche en cours… » et se met à jour toute seule ;
  cliquer plusieurs fois n'empile pas les recherches.
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

## Local ou en ligne : que choisir ?

- **En local** (option B) : meilleur taux de réussite du scraping, car la requête
  part de votre connexion personnelle — les sites bloquent nettement moins. Mais
  il faut Python sur la machine, et l'outil n'est accessible que depuis celle-ci.
- **En ligne** (option A) : rien à installer, accessible depuis n'importe quel
  appareil dont votre téléphone, mais l'IP de datacenter est davantage bloquée
  et le plan gratuit efface l'historique.

Si l'hébergement en ligne fait remonter 0 annonce sur une ou plusieurs sources,
c'est ce blocage qui est en cause. Deux réponses possibles : passer cette source
par un service de contournement anti-robot (payant), ou lancer l'outil en local
quand vous voulez une collecte complète. Dites-le-moi et j'adapte.
