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
        logger.info("Chargement du modèle YOLOv8...")
        from ultralytics import YOLO
        
        # Utiliser le modèle nano pour la performance
        model = YOLO("yolov8n.pt")
        
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
        "model_load_time": f"{model_load_time:.2f}s" if model_loaded else None
    }
    return jsonify(status)

@app.route('/detect', methods=['POST'])
def detect_persons():
    """Endpoint pour la détection de personnes dans une image"""
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image n'a été envoyée"}), 400
    
    # Récupérer l'image depuis la requête
    file = request.files['image']
    img_bytes = file.read()
    
    # Seuil de confiance et autres paramètres (peuvent être envoyés dans la requête)
    confidence = float(request.form.get('confidence', 0.25))
    
    # Charger le modèle si ce n'est pas déjà fait
    if not model_loaded and not load_model():
        return jsonify({"error": "Impossible de charger le modèle"}), 500
    
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

if __name__ == "__main__":
    # Charger le modèle au démarrage
    load_model()
    
    # Récupérer le port depuis les variables d'environnement (requis par Cloud Run)
    port = int(os.environ.get('PORT', 8080))
    
    # Démarrer le serveur
    app.run(host='0.0.0.0', port=port, debug=False) 