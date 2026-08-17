#!/bin/bash
# Double-cliquez sur ce fichier pour lancer ImmoRadar.
# (Aucun terminal à utiliser : une fenêtre s'ouvre, le navigateur aussi.)

cd "$(dirname "$0")" || exit 1

echo "=========================================="
echo "  ImmoRadar Invest"
echo "=========================================="
echo

# 1. Python installé ?
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python 3 n'est pas installé sur ce Mac."
    echo
    echo "   Téléchargez-le ici (bouton jaune 'Download Python') :"
    echo "   https://www.python.org/downloads/"
    echo
    echo "   Puis double-cliquez à nouveau sur ce fichier."
    echo
    read -r -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# 2. Environnement isolé (créé une seule fois, réutilisé ensuite)
if [ ! -d ".venv" ]; then
    echo "⚙️  Première installation (une minute environ)..."
    python3 -m venv .venv || {
        echo "❌ Impossible de créer l'environnement Python."
        read -r -p "Appuyez sur Entrée pour fermer..."
        exit 1
    }
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# 3. Dépendances (rapide si déjà installées)
echo "⚙️  Vérification des dépendances..."
pip install --quiet --upgrade pip >/dev/null 2>&1
if ! pip install --quiet -r requirements.txt; then
    echo "❌ Installation des dépendances impossible (connexion internet ?)."
    read -r -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi

# 4. Ouverture du navigateur une fois le serveur prêt
( sleep 4; open "http://localhost:3000" >/dev/null 2>&1 ) &

echo
echo "✅ Démarrage… le navigateur va s'ouvrir sur http://localhost:3000"
echo
echo "   Les annonces arrivent progressivement (1 à 2 min au premier lancement)."
echo "   ⚠️  Gardez CETTE FENÊTRE OUVERTE tant que vous utilisez l'outil."
echo "   Pour arrêter : fermez cette fenêtre, ou appuyez sur Ctrl+C."
echo
echo "=========================================="
echo

python3 server.py

echo
read -r -p "Serveur arrêté. Appuyez sur Entrée pour fermer..."
