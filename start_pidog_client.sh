#!/bin/bash
# Script de lancement pour PiDog Client
# 
# Rend l'utilisation du client plus simple sur le Raspberry Pi
# Vous pouvez exécuter ce script avec ./start_pidog_client.sh

echo "Démarrage du client PiDog..."
echo "Se connecte au serveur cloud sur killerrobot-production.up.railway.app:8080"

# Si vous avez une erreur avec la webcam, décommentez cette ligne
# OPTION="--no-camera"

# Lancement du client Python
python3 pidog_client.py $OPTION

# En cas d'erreur
if [ $? -ne 0 ]; then
    echo "Erreur lors du démarrage du client PiDog."
    echo "Vérifiez que le client est correctement installé et que les dépendances sont satisfaites."
    echo "Consultez le fichier README.md pour plus d'informations."
    exit 1
fi 