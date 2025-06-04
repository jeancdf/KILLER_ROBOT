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
    parser.add_argument('--debug', action='store_true', help='Afficher plus d\'informations de débogage')
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

    # Vérifier les attributs du PiDog pour trouver le capteur ultrasonique
    ultrasonic_attribute = None
    if hasattr(dog, 'ultrasonic'):
        ultrasonic_attribute = 'ultrasonic'
        print("Capteur ultrasonique trouvé via l'attribut 'ultrasonic'")
    elif hasattr(dog, 'sonar'):
        ultrasonic_attribute = 'sonar'
        print("Capteur ultrasonique trouvé via l'attribut 'sonar'")
    elif hasattr(dog, 'distance'):
        ultrasonic_attribute = 'distance'
        print("Capteur ultrasonique trouvé via l'attribut 'distance'")
    else:
        print("AVERTISSEMENT: Attribut du capteur ultrasonique non trouvé!")
        if args.debug:
            print("Attributs disponibles:")
            for attr in dir(dog):
                if not attr.startswith('_'):  # Ignorer les attributs privés
                    print(f"- {attr}")
        print("Tentative d'utilisation directe du capteur...")

    # Tester la fonction de lecture de distance
    print("Test de lecture du capteur...")
    test_successful = False
    
    try:
        if ultrasonic_attribute:
            sensor = getattr(dog, ultrasonic_attribute)
            if hasattr(sensor, 'read_distance'):
                test_value = sensor.read_distance()
                print(f"Lecture de test via {ultrasonic_attribute}.read_distance(): {test_value}")
                test_successful = True
            elif hasattr(sensor, 'read'):
                test_value = sensor.read()
                print(f"Lecture de test via {ultrasonic_attribute}.read(): {test_value}")
                test_successful = True
            elif hasattr(sensor, 'get_distance'):
                test_value = sensor.get_distance()
                print(f"Lecture de test via {ultrasonic_attribute}.get_distance(): {test_value}")
                test_successful = True
        
        # Si les méthodes standards échouent, essayer d'accéder directement
        if not test_successful and hasattr(dog, 'read_distance'):
            test_value = dog.read_distance()
            print(f"Lecture de test via dog.read_distance(): {test_value}")
            test_successful = True
        elif not test_successful and hasattr(dog, 'get_distance'):
            test_value = dog.get_distance()
            print(f"Lecture de test via dog.get_distance(): {test_value}")
            test_successful = True
            
    except Exception as e:
        print(f"ERREUR lors du test de lecture: {e}")
        traceback.print_exc()
    
    if not test_successful:
        print("ERREUR: Impossible de trouver une méthode de lecture du capteur ultrasonique!")
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
    
    # Fonction pour lire la distance en fonction de ce qui a été trouvé
    def read_distance():
        if ultrasonic_attribute:
            sensor = getattr(dog, ultrasonic_attribute)
            if hasattr(sensor, 'read_distance'):
                return sensor.read_distance()
            elif hasattr(sensor, 'read'):
                return sensor.read()
            elif hasattr(sensor, 'get_distance'):
                return sensor.get_distance()
        if hasattr(dog, 'read_distance'):
            return dog.read_distance()
        elif hasattr(dog, 'get_distance'):
            return dog.get_distance()
        return None
    
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
                        raw_value = read_distance()
                        if args.debug:
                            print(f"Valeur brute: {raw_value}, type: {type(raw_value)}")
                        if raw_value is not None and isinstance(raw_value, (int, float)) and raw_value > 0 and raw_value < 1000:
                            distance = raw_value
                            break
                    except Exception as e:
                        if args.debug:
                            print(f"Erreur de lecture: {e}")
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
                    if args.debug and raw_value is not None:
                        print(f"  Valeur brute reçue: {raw_value}, type: {type(raw_value)}")
            
            except Exception as e:
                print(f"[{timestamp}] ERREUR lors de la lecture: {e}")
                if args.debug:
                    traceback.print_exc()
            
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