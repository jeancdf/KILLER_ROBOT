#!/usr/bin/env python3
# Script de test pour la connexion WebSocket avec le serveur PiDog

import websocket
import json
import sys
import time
import argparse

def on_message(ws, message):
    print(f"Message reçu: {message}")

def on_error(ws, error):
    print(f"Erreur: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Connexion fermée: {close_status_code} - {close_msg}")

def on_open(ws):
    print("Connexion établie!")
    # Envoyer un message de statut initial
    ws.send(json.dumps({
        "type": "status_response",
        "has_camera": True,
        "has_imu": True,
        "has_rgb": True,
        "has_distance_sensor": True,
        "ip_address": "127.0.0.1",
        "timestamp": time.time()
    }))
    print("Message de statut envoyé")

def main():
    parser = argparse.ArgumentParser(description='Test de connexion WebSocket')
    parser.add_argument('--url', type=str, default='wss://killerrobot-production.up.railway.app/ws/test-client',
                        help='URL du serveur WebSocket')
    parser.add_argument('--client-id', type=str, default=f"test-client-{int(time.time())}",
                        help='ID client à utiliser pour la connexion')
    parser.add_argument('--secure', action='store_true', 
                        help='Utiliser wss:// au lieu de ws://')
    parser.add_argument('--port', type=int, default=None,
                        help='Port spécifique (facultatif)')
    
    args = parser.parse_args()
    
    # Construire l'URL complète
    url = args.url
    
    # S'assurer que l'URL contient un ID client
    if url.endswith('/ws'):
        url = f"{url}/{args.client_id}"
    
    if args.port:
        # Remplacer le port dans l'URL si spécifié
        if '://' in url:
            protocol, rest = url.split('://', 1)
            if '/' in rest:
                host, path = rest.split('/', 1)
                if ':' in host:
                    host = host.split(':', 1)[0]
                url = f"{protocol}://{host}:{args.port}/{path}"
            else:
                if ':' in rest:
                    rest = rest.split(':', 1)[0]
                url = f"{protocol}://{rest}:{args.port}"
    
    print(f"Tentative de connexion à {url}")
    print(f"Client ID: {args.client_id}")
    
    # Activer le mode trace pour le débogage
    websocket.enableTrace(True)
    
    # Créer la connexion WebSocket
    ws = websocket.WebSocketApp(url,
                               on_open=on_open,
                               on_message=on_message,
                               on_error=on_error,
                               on_close=on_close)
    
    # Options SSL pour ignorer la validation du certificat
    ws.run_forever(sslopt={"cert_reqs": 0})

if __name__ == "__main__":
    main() 