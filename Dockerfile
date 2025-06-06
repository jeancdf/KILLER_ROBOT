FROM python:3.11-slim

WORKDIR /app

# Installation des dépendances systèmes nécessaires pour OpenCV et autres packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers de dépendances avant le reste du code pour mieux utiliser le cache de Docker
COPY requirements.txt .

# Installation des dépendances Python avec des versions spécifiques
RUN pip install --no-cache-dir -r requirements.txt

# Installation des packages supplémentaires pour le serveur cloud
RUN pip install --no-cache-dir fastapi uvicorn websockets python-multipart

# Télécharger le modèle YOLOv8n au lieu de le copier
RUN wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt

# Créer les répertoires nécessaires
RUN mkdir -p templates static

# Copier les fichiers de l'application
COPY cloud_server.py .
COPY templates/ templates/
COPY static/ static/

# Variable d'environnement pour indiquer l'environnement de déploiement
ENV DEPLOYMENT_ENV=production

# Exposer le port sur lequel l'application va s'exécuter
EXPOSE 8000

# Script de démarrage pour gérer correctement la variable d'environnement PORT
RUN echo '#!/bin/bash\n\
PORT="${PORT:-8000}"\n\
echo "Starting server on port $PORT"\n\
exec uvicorn cloud_server:app --host 0.0.0.0 --port $PORT\n\
' > /app/start.sh && chmod +x /app/start.sh

# Command pour exécuter l'application
CMD ["/app/start.sh"] 