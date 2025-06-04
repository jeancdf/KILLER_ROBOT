#!/usr/bin/env python3
"""
Script de test pour la caméra du PiDog
Affiche les images capturées et permet de tester différentes méthodes de capture
"""

import cv2
import time
import argparse
import os
import sys
import traceback
import numpy as np
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Test de la caméra du PiDog')
    parser.add_argument('--width', type=int, default=640, help='Largeur de l\'image')
    parser.add_argument('--height', type=int, default=480, help='Hauteur de l\'image')
    parser.add_argument('--fps', type=int, default=30, help='Images par seconde souhaitées')
    parser.add_argument('--save', action='store_true', help='Enregistrer les images capturées')
    parser.add_argument('--save-dir', type=str, default='./camera_test', help='Dossier pour enregistrer les images')
    parser.add_argument('--device', type=int, default=0, help='ID du périphérique de caméra (default: 0)')
    parser.add_argument('--picamera', action='store_true', help='Utiliser PiCamera au lieu d\'OpenCV')
    parser.add_argument('--duration', type=int, default=0, help='Durée du test en secondes (0=infini)')
    parser.add_argument('--debug', action='store_true', help='Afficher plus d\'informations de débogage')
    args = parser.parse_args()

    # Créer le dossier de sauvegarde si nécessaire
    if args.save:
        os.makedirs(args.save_dir, exist_ok=True)
        print(f"Les images seront enregistrées dans: {args.save_dir}")
    
    # Initialiser la caméra
    camera = None
    camera_type = "unknown"
    
    # 1. Essayer d'utiliser PiCamera2 si spécifié et disponible
    if args.picamera:
        try:
            print("Tentative d'initialisation avec PiCamera2...")
            from picamera2 import Picamera2
            
            picam2 = Picamera2()
            config = picam2.create_preview_configuration(
                main={"size": (args.width, args.height), "format": "RGB888"},
                lores={"size": (320, 240), "format": "YUV420"},
                display="lores"
            )
            picam2.configure(config)
            picam2.start()
            camera = picam2
            camera_type = "picamera2"
            print("PiCamera2 initialisée avec succès")
        except Exception as e:
            print(f"Erreur lors de l'initialisation de PiCamera2: {e}")
            if args.debug:
                traceback.print_exc()
            print("Passage à OpenCV pour la capture...")
    
    # 2. Si PiCamera a échoué ou n'est pas spécifiée, utiliser OpenCV
    if camera is None:
        try:
            print(f"Tentative d'initialisation de la caméra OpenCV (device {args.device})...")
            cap = cv2.VideoCapture(args.device)
            
            if not cap.isOpened():
                print("Erreur: Impossible d'ouvrir la caméra")
                sys.exit(1)
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            cap.set(cv2.CAP_PROP_FPS, args.fps)
            
            # Vérifier les paramètres réels
            actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            
            print(f"Caméra OpenCV initialisée:")
            print(f"- Résolution demandée: {args.width}x{args.height}")
            print(f"- Résolution obtenue: {actual_width}x{actual_height}")
            print(f"- FPS demandés: {args.fps}")
            print(f"- FPS obtenus: {actual_fps}")
            
            camera = cap
            camera_type = "opencv"
        except Exception as e:
            print(f"Erreur lors de l'initialisation de la caméra OpenCV: {e}")
            if args.debug:
                traceback.print_exc()
            sys.exit(1)
    
    print("\nTest de capture d'image...")
    
    # Fonction pour capturer une image selon le type de caméra
    def capture_frame():
        if camera_type == "opencv":
            ret, frame = camera.read()
            if not ret:
                return None
            return frame
        elif camera_type == "picamera2":
            # PiCamera2 capture
            frame = camera.capture_array("main")
            return frame
        return None
    
    # Tester la capture
    test_frame = capture_frame()
    if test_frame is None:
        print("Erreur: Impossible de capturer une image")
        if camera_type == "opencv":
            camera.release()
        elif camera_type == "picamera2":
            camera.stop()
        sys.exit(1)
    
    print(f"Image de test capturée avec succès:")
    print(f"- Dimensions: {test_frame.shape[1]}x{test_frame.shape[0]}")
    print(f"- Canaux: {test_frame.shape[2] if len(test_frame.shape) > 2 else 1}")
    
    if args.save:
        test_filename = os.path.join(args.save_dir, f"test_frame_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        cv2.imwrite(test_filename, test_frame)
        print(f"Image de test enregistrée: {test_filename}")
    
    print("\nDémarrage du flux vidéo. Appuyez sur 'q' pour quitter.")
    
    # Variables pour le calcul des FPS
    frame_count = 0
    start_time = time.time()
    last_fps_time = start_time
    fps = 0
    
    while True:
        # Vérifier si la durée du test est atteinte
        if args.duration > 0 and (time.time() - start_time) > args.duration:
            print("\nDurée du test atteinte. Arrêt...")
            break
        
        # Capturer une image
        frame = capture_frame()
        
        if frame is None:
            print("Erreur: Impossible de capturer l'image")
            time.sleep(0.1)
            continue
        
        # Incrémenter le compteur d'images
        frame_count += 1
        
        # Calculer et afficher les FPS
        current_time = time.time()
        elapsed_time = current_time - last_fps_time
        
        if elapsed_time > 1.0:  # Mise à jour des FPS chaque seconde
            fps = frame_count / elapsed_time
            frame_count = 0
            last_fps_time = current_time
        
        # Ajouter le texte des FPS à l'image
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Ajouter un horodatage
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Afficher l'image
        cv2.imshow('Test Camera', frame)
        
        # Enregistrer l'image si demandé (à intervalle régulier)
        if args.save and frame_count % 10 == 0:  # Enregistrer une image sur 10
            filename = os.path.join(args.save_dir, f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            cv2.imwrite(filename, frame)
        
        # Sortir si 'q' est pressé
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Libérer les ressources
    if camera_type == "opencv":
        camera.release()
    elif camera_type == "picamera2":
        camera.stop()
    
    cv2.destroyAllWindows()
    print("Test de caméra terminé.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"Erreur: {e}")
        traceback.print_exc()
        cv2.destroyAllWindows() 