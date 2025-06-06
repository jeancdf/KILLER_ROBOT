#!/usr/bin/env python3
"""
API Cloud pour la détection de personnes - PiDog Tracker
Exécuté sur Google Cloud Run

Endpoints:
- /health: Vérification que le service est opérationnel
- /detect: Reçoit une image et retourne les détections de personnes
"""

import os
import io
import time
import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import threading

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin

# Variables globales
model = None
model_loading = False
model_loaded = False
model_load_time = 0
model_type = os.environ.get('MODEL_TYPE', 'nano')  # Utiliser une variable d'environnement pour le type de modèle

# Lancer le chargement du modèle dans un thread séparé pour ne pas bloquer le démarrage de l'app
def load_model_thread():
    """Fonction de chargement du modèle dans un thread séparé"""
    logger.info("Démarrage du thread de chargement du modèle...")
    load_model()

def load_model():
    """Charge le modèle YOLOv8 une seule fois"""
    global model, model_loading, model_loaded, model_load_time
    
    if model_loading:
        return False
    
    if model_loaded:
        return True
    
    model_loading = True
    start_time = time.time()
    
    try:
        logger.info(f"Chargement du modèle YOLOv8 {model_type}...")
        from ultralytics import YOLO
        
        # Utiliser le modèle spécifié par la variable d'environnement
        model_name = f"yolov8{model_type}.pt"
        logger.info(f"Utilisation du modèle: {model_name}")
        
        # Attendre un moment pour s'assurer que l'application a eu le temps de démarrer
        time.sleep(2)
        
        model = YOLO(model_name)
        
        # Optimisation des performances
        try:
            import torch
            if torch.cuda.is_available():
                model.to('cuda')
                logger.info("Modèle chargé sur CUDA")
            else:
                # Utiliser demi-précision pour CPU
                model.to('cpu')
                logger.info("Modèle chargé sur CPU")
        except Exception as e:
            logger.warning(f"Erreur lors de l'optimisation du modèle: {e}")
        
        # Échauffement du modèle avec une image vide
        logger.info("Échauffement du modèle avec une image test...")
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        model(dummy_img, conf=0.25, classes=0, verbose=False)
        
        model_loaded = True
        model_loading = False
        model_load_time = time.time() - start_time
        logger.info(f"Modèle YOLOv8 chargé en {model_load_time:.2f} secondes")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors du chargement du modèle: {e}")
        model_loading = False
        return False

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint pour vérifier que le service est opérationnel"""
    status = {
        "status": "ok",
        "model_loaded": model_loaded,
        "model_loading": model_loading,
        "model_load_time": f"{model_load_time:.2f}s" if model_loaded else None,
        "model_type": model_type
    }
    return jsonify(status)

@app.route('/', methods=['GET'])
def index():
    """Page d'accueil simple"""
    return """
    <html>
        <head>
            <title>PiDog Cloud API</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #333; }
                .endpoint { background: #f4f4f4; padding: 10px; border-radius: 5px; margin-bottom: 10px; }
                code { background: #e0e0e0; padding: 2px 4px; border-radius: 3px; }
            </style>
        </head>
        <body>
            <h1>PiDog Cloud API</h1>
            <p>API pour la détection de personnes utilisant YOLOv8.</p>
            <h2>Endpoints disponibles:</h2>
            <div class="endpoint">
                <h3>GET /health</h3>
                <p>Vérifier l'état du service</p>
            </div>
            <div class="endpoint">
                <h3>POST /detect</h3>
                <p>Détecter des personnes dans une image</p>
                <p>Paramètres: <code>image</code> (fichier), <code>confidence</code> (optionnel, float)</p>
            </div>
        </body>
    </html>
    """

@app.route('/detect', methods=['POST'])
def detect_persons():
    """Endpoint pour la détection de personnes dans une image"""
    global model, model_loaded, model_loading
    
    # Si le modèle n'est pas chargé et pas en cours de chargement, lancer le chargement
    if not model_loaded and not model_loading:
        logger.info("Démarrage du chargement du modèle suite à une requête de détection...")
        threading.Thread(target=load_model).start()
        return jsonify({"error": "Le modèle est en cours de chargement, veuillez réessayer dans quelques instants"}), 503
    
    # Si le modèle est en cours de chargement
    if model_loading:
        return jsonify({"error": "Le modèle est en cours de chargement, veuillez réessayer dans quelques instants"}), 503
    
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image n'a été envoyée"}), 400
    
    # Récupérer l'image depuis la requête
    file = request.files['image']
    img_bytes = file.read()
    
    # Seuil de confiance et autres paramètres (peuvent être envoyés dans la requête)
    confidence = float(request.form.get('confidence', 0.25))
    
    try:
        # Convertir les bytes en image numpy
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({"error": "Image invalide"}), 400
        
        # Mesure du temps d'inférence
        start_time = time.time()
        
        # Exécuter l'inférence
        results = model(img, conf=confidence, classes=0, verbose=False)  # classe 0 = personne
        
        inference_time = time.time() - start_time
        logger.info(f"Inférence effectuée en {inference_time:.4f} secondes")
        
        # Extraire les informations des boîtes détectées
        detections = []
        
        for result in results:
            boxes = result.boxes.cpu().numpy()
            
            for box in boxes:
                # Obtenir l'ID de classe
                class_id = int(box.cls[0])
                
                # Si l'objet détecté est une personne (classe 0)
                if class_id == 0:
                    # Obtenir les coordonnées de la boîte
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Obtenir le score de confiance
                    confidence_score = float(box.conf[0])
                    
                    # Ajouter à la liste des détections
                    detection = {
                        "class_id": class_id,
                        "class_name": "person",
                        "confidence": confidence_score,
                        "bbox": {
                            "x1": x1,
                            "y1": y1,
                            "x2": x2,
                            "y2": y2,
                            "width": x2 - x1,
                            "height": y2 - y1,
                            "center_x": (x1 + x2) // 2,
                            "center_y": (y1 + y2) // 2
                        }
                    }
                    detections.append(detection)
        
        # Préparer la réponse
        response = {
            "success": True,
            "inference_time": inference_time,
            "detections": detections,
            "image_size": {
                "width": img.shape[1],
                "height": img.shape[0]
            }
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Erreur lors de la détection: {e}")
        return jsonify({"error": str(e)}), 500

# Démarrer le chargement du modèle dans un thread séparé au démarrage de l'application
@app.before_first_request
def before_first_request():
    """Fonction exécutée avant la première requête pour initialiser le modèle"""
    if not model_loaded and not model_loading:
        logger.info("Initialisation du chargement du modèle avant la première requête...")
        threading.Thread(target=load_model).start()

if __name__ == "__main__":
    # Démarrer le chargement du modèle dans un thread séparé
    threading.Thread(target=load_model_thread).start()
    
    # Récupérer le port depuis les variables d'environnement (requis par Cloud Run)
    port = int(os.environ.get('PORT', 8080))
    
    # Démarrer le serveur
    app.run(host='0.0.0.0', port=port, debug=False) 