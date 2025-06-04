#!/usr/bin/env python3
"""
Script de test pour le capteur ultrasonique du PiDog
Affiche les lectures de distance en temps réel avec des statistiques
"""

import time
import traceback
import argparse
import numpy as np
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Test du capteur ultrasonique du PiDog')
    parser.add_argument('--interval', type=float, default=0.1, help='Intervalle entre les mesures (secondes)')
    parser.add_argument('--duration', type=int, default=0, help='Durée du test en secondes (0=infini)')
    parser.add_argument('--stats', type=int, default=10, help='Nombre de lectures pour calculer les statistiques')
    parser.add_argument('--log', action='store_true', help='Enregistrer les données dans un fichier log')
    args = parser.parse_args()

    print("Initialisation du PiDog...")
    try:
        from pidog import Pidog
        dog = Pidog()
        print("PiDog initialisé avec succès")
    except Exception as e:
        print(f"ERREUR: Impossible d'initialiser le PiDog: {e}")
        traceback.print_exc()
        return

    print(f"\nTest du capteur ultrasonique:")
    print(f"- Intervalle: {args.interval} seconde(s)")
    print(f"- Statistiques calculées toutes les {args.stats} lectures")
    if args.duration > 0:
        print(f"- Durée totale du test: {args.duration} seconde(s)")
    else:
        print("- Test exécuté jusqu'à interruption (Ctrl+C)")
    
    if args.log:
        log_file = f"distance_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(log_file, 'w') as f:
            f.write("timestamp,distance_cm,raw_value\n")
        print(f"- Enregistrement des données dans: {log_file}")

    print("\nDémarrage du test. Appuyez sur Ctrl+C pour arrêter.\n")
    
    # Variables pour les statistiques
    readings = []
    start_time = time.time()
    
    try:
        count = 0
        while True:
            # Vérifier si la durée du test est atteinte
            if args.duration > 0 and (time.time() - start_time) > args.duration:
                print("\nDurée du test atteinte. Arrêt...")
                break
            
            # Lire la distance
            count += 1
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            
            try:
                # Plusieurs tentatives pour avoir une lecture fiable
                raw_value = None
                distance = None
                
                # Essayer jusqu'à 3 fois en cas d'erreur
                for _ in range(3):
                    try:
                        raw_value = dog.ultrasonic.read_distance()
                        if raw_value is not None and raw_value > 0 and raw_value < 1000:
                            distance = raw_value
                            break
                    except:
                        pass
                    time.sleep(0.01)
                
                if distance is not None:
                    readings.append(distance)
                    # Garder uniquement les X dernières lectures pour les statistiques
                    if len(readings) > args.stats * 2:
                        readings = readings[-args.stats:]
                    
                    # Afficher la valeur
                    print(f"[{timestamp}] Lecture #{count}: {distance:.1f} cm")
                    
                    # Enregistrer dans le fichier log si demandé
                    if args.log:
                        with open(log_file, 'a') as f:
                            f.write(f"{timestamp},{distance:.1f},{raw_value}\n")
                    
                    # Afficher les statistiques périodiquement
                    if count % args.stats == 0 and readings:
                        calc_and_show_stats(readings)
                else:
                    print(f"[{timestamp}] Lecture #{count}: ERREUR - Valeur invalide ou capteur non disponible")
            
            except Exception as e:
                print(f"[{timestamp}] ERREUR lors de la lecture: {e}")
            
            # Attendre avant la prochaine lecture
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")
    finally:
        # Afficher les statistiques finales
        if readings:
            print("\nStatistiques finales:")
            calc_and_show_stats(readings)
        
        # Fermer proprement le PiDog
        try:
            dog.close()
            print("PiDog fermé avec succès")
        except:
            pass

def calc_and_show_stats(readings):
    """Calcule et affiche les statistiques sur les lectures"""
    arr = np.array(readings)
    
    # Calcul des statistiques
    min_val = np.min(arr)
    max_val = np.max(arr)
    mean_val = np.mean(arr)
    median_val = np.median(arr)
    std_val = np.std(arr)
    
    # Affichage
    print("\n--- Statistiques sur les dernières lectures ---")
    print(f"Nombre de lectures: {len(readings)}")
    print(f"Min: {min_val:.1f} cm")
    print(f"Max: {max_val:.1f} cm")
    print(f"Moyenne: {mean_val:.1f} cm")
    print(f"Médiane: {median_val:.1f} cm")
    print(f"Écart-type: {std_val:.1f} cm")
    
    # Analyse des fluctuations
    if std_val > 10:
        print("ATTENTION: Fluctuations importantes détectées!")
    elif std_val > 5:
        print("Note: Fluctuations modérées détectées")
    else:
        print("Note: Lectures stables")
    
    print("-------------------------------------------\n")

if __name__ == "__main__":
    main() 