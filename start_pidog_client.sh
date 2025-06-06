#!/bin/bash
# Script de lancement pour PiDog Client
# 
# Rend l'utilisation du client plus simple sur le Raspberry Pi
# Vous pouvez exécuter ce script avec ./start_pidog_client.sh

echo "Démarrage du client PiDog..."

# Options disponibles
echo "Choisissez un serveur pour la connexion:"
echo "1) Production Railway (wss://killerrobot-production.up.railway.app/ws)"
echo "2) Serveur local (ws://localhost:8000/ws)"
echo "3) Production Railway avec port spécifique (ws://killerrobot-production.up.railway.app:8080/ws)"
echo "4) URL personnalisée"
read -p "Votre choix (1-4): " server_choice

case $server_choice in
    1)
        SERVER_URL="wss://killerrobot-production.up.railway.app/ws"
        ;;
    2)
        SERVER_URL="ws://localhost:8000/ws"
        ;;
    3)
        SERVER_URL="ws://killerrobot-production.up.railway.app:8080/ws"
        ;;
    4)
        read -p "Entrez l'URL complète du serveur WebSocket: " SERVER_URL
        ;;
    *)
        echo "Choix invalide. Utilisation de l'URL par défaut."
        SERVER_URL="wss://killerrobot-production.up.railway.app/ws"
        ;;
esac

echo "Se connecte au serveur: $SERVER_URL"

# Options supplémentaires
read -p "Désactiver la caméra? (o/n): " no_cam
if [ "$no_cam" == "o" ] || [ "$no_cam" == "O" ]; then
    OPTIONS="--no-camera"
    echo "Option --no-camera activée"
else
    OPTIONS=""
fi

# Lancement du client Python
echo "Exécution de: python3 pidog_client.py --server $SERVER_URL $OPTIONS"
python3 pidog_client.py --server "$SERVER_URL" $OPTIONS

# En cas d'erreur
if [ $? -ne 0 ]; then
    echo "Erreur lors du démarrage du client PiDog."
    echo "Vérifiez que le client est correctement installé et que les dépendances sont satisfaites."
    echo "Dépendances requises: pip install websocket-client opencv-python numpy"
    echo ""
    echo "Pour tester uniquement la connexion WebSocket sans le hardware:"
    echo "python3 test_websocket.py --url $SERVER_URL"
    exit 1
fi 