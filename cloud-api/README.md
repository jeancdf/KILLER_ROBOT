# PiDog Cloud API

API Cloud pour la détection de personnes destinée au projet PiDog Tracker.

## Description

Ce service est conçu pour fonctionner sur Google Cloud Run et fournit une API pour la détection de personnes dans les images. Il utilise le modèle YOLOv8 pour la détection et renvoie les résultats dans un format JSON standardisé.

## Points d'accès (Endpoints)

- **GET /health** : Vérifie que le service est opérationnel et que le modèle est chargé
- **POST /detect** : Reçoit une image et retourne les détections de personnes

## Utilisation

### Vérification de l'état du service

```
GET /health
```

Réponse:
```json
{
  "status": "ok",
  "model_loaded": true,
  "model_load_time": "1.25s"
}
```

### Détection de personnes

```
POST /detect
```

Paramètres:
- `image` (fichier) : L'image dans laquelle détecter des personnes
- `confidence` (optionnel) : Seuil de confiance pour la détection (par défaut: 0.25)

Réponse:
```json
{
  "success": true,
  "inference_time": 0.1234,
  "detections": [
    {
      "class_id": 0,
      "class_name": "person",
      "confidence": 0.95,
      "bbox": {
        "x1": 100,
        "y1": 200,
        "x2": 300,
        "y2": 500,
        "width": 200,
        "height": 300,
        "center_x": 200,
        "center_y": 350
      }
    }
  ],
  "image_size": {
    "width": 640,
    "height": 480
  }
}
```

## Déploiement sur Google Cloud Run

1. Construire l'image Docker:
```
docker build -t pidog-cloud-api .
```

2. Tester localement:
```
docker run -p 8080:8080 pidog-cloud-api
```

3. Pousser vers Google Container Registry:
```
docker tag pidog-cloud-api gcr.io/[PROJECT-ID]/pidog-cloud-api
docker push gcr.io/[PROJECT-ID]/pidog-cloud-api
```

4. Déployer sur Cloud Run:
```
gcloud run deploy pidog-cloud-api --image gcr.io/[PROJECT-ID]/pidog-cloud-api --platform managed
```

## Utilisation avec le client PiDog

Pour utiliser cette API avec le PiDog, exécutez le script client avec l'option `--cloud-api`:

```
python pidog_person_tracker.py --cloud-api https://[URL-CLOUD-RUN]/
```

## Développement local

Pour exécuter l'API localement:

```
pip install -r requirements.txt
python app.py
```

L'API sera accessible à l'adresse: http://localhost:8080 