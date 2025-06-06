FROM python:3.10-slim

WORKDIR /app

# Installer les dépendances système requises
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-télécharger les modèles YOLOv8
RUN mkdir -p /app/models && \
    python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Copier le code de l'application
COPY app.py .

# Exposer le port pour le serveur web
EXPOSE 8080

# Variable d'environnement pour port Cloud Run
ENV PORT=8080
ENV MODEL_TYPE=nano
ENV PYTHONUNBUFFERED=1

# Démarrer l'application avec gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app 