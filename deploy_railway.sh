#!/bin/bash

# Script de déploiement pour Railway

echo "🚀 Déploiement du PiDog Cloud Server sur Railway..."

# Vérifier si Railway CLI est installé
if ! command -v railway &> /dev/null
then
    echo "❌ Railway CLI n'est pas installé. Installation en cours..."
    npm i -g @railway/cli
    
    if [ $? -ne 0 ]; then
        echo "❌ Échec de l'installation de Railway CLI. Assurez-vous que Node.js et npm sont installés."
        exit 1
    fi
fi

# Vérifier si l'utilisateur est connecté à Railway
railway whoami &> /dev/null
if [ $? -ne 0 ]; then
    echo "❌ Vous n'êtes pas connecté à Railway. Connexion en cours..."
    railway login
    
    if [ $? -ne 0 ]; then
        echo "❌ Échec de la connexion à Railway."
        exit 1
    fi
fi

# Vérifier si les fichiers nécessaires existent
if [ ! -f "cloud_server.py" ]; then
    echo "❌ Fichier cloud_server.py manquant!"
    exit 1
fi

if [ ! -d "templates" ] || [ ! -d "static" ]; then
    echo "❌ Dossiers templates ou static manquants!"
    exit 1
fi

# Déployer sur Railway
echo "⏳ Initialisation du projet Railway..."
railway init

echo "⏳ Déploiement en cours..."
railway up

if [ $? -eq 0 ]; then
    echo "✅ Déploiement réussi!"
    echo "🌐 URL du service (utilisez cette URL pour configurer le client PiDog):"
    railway domain
else
    echo "❌ Échec du déploiement."
    exit 1
fi

echo "📝 Instructions pour le client Raspberry Pi:"
echo "Sur votre Raspberry Pi, exécutez:"
echo "python pidog_client.py --server ws://VOTRE_URL_RAILWAY/ws"
echo ""
echo "Remplacez VOTRE_URL_RAILWAY par l'URL affichée ci-dessus." 