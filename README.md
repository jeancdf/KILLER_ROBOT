# PiDog Cloud Control

Architecture cloud pour la détection de personnes et le contrôle à distance du robot PiDog.

## 📋 Vue d'ensemble

Ce projet fournit une architecture client-serveur pour contrôler un robot PiDog via une interface web hébergée dans le cloud, avec détection de personnes en temps réel.

* **Serveur cloud** : Héberge l'interface web, l'API et exécute la détection d'objets avec YOLOv8
* **Client Raspberry Pi** : S'exécute sur le PiDog, capture les images et exécute les commandes reçues du serveur

## 🔍 Caractéristiques

* **Interface web moderne** : Contrôle complet du robot depuis n'importe quel navigateur
* **Détection IA dans le cloud** : Traitement des images par YOLOv8 pour détecter les personnes
* **Tolérance aux erreurs** : Fonctionne même si certains composants matériels sont défaillants
* **WebSockets** : Communication bidirectionnelle en temps réel
* **Architecture résiliente** : Reconnexion automatique, gestion des erreurs, etc.

## 🚀 Déploiement

### Déploiement du serveur cloud sur Railway

1. Assurez-vous d'avoir [Git](https://git-scm.com/) installé

2. Clonez ce dépôt :
   ```bash
   git clone https://votre-repo/pidog-cloud.git
   cd pidog-cloud
   ```

3. Installez Railway CLI (ou utilisez le script `deploy_railway.sh`) :
   ```bash
   npm install -g @railway/cli
   railway login
   ```

4. Déployez sur Railway :
   ```bash
   railway up
   ```

5. Obtenez l'URL de votre service :
   ```bash
   railway domain
   ```

### Configuration du client Raspberry Pi

1. Copiez les fichiers `pidog_client.py`, `start_pidog_client.sh` et `test_websocket.py` sur votre Raspberry Pi

2. Installez les dépendances :
   ```bash
   pip install websocket-client opencv-python requests
   ```

3. Rendez le script de démarrage exécutable :
   ```bash
   chmod +x start_pidog_client.sh
   ```

4. Exécutez le script de démarrage qui vous guidera pour la connexion :
   ```bash
   ./start_pidog_client.sh
   ```

5. Alternativement, exécutez le client directement en spécifiant l'URL du serveur cloud :
   ```bash
   python pidog_client.py --server wss://VOTRE_URL_RAILWAY/ws
   ```

## 🛠️ Développement local

### Serveur cloud

1. Créez un environnement virtuel :
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows : venv\Scripts\activate
   ```

2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   pip install fastapi uvicorn websockets python-multipart
   ```

3. Lancez le serveur :
   ```bash
   uvicorn cloud_server:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Accédez à l'interface web : http://localhost:8000

### Client Raspberry Pi

1. Exécutez en mode développement avec le serveur local :
   ```bash
   python pidog_client.py --server ws://IP_LOCALE:8000/ws --debug
   ```

## 📊 Architecture

```
┌─────────────────────┐       WebSocket       ┌─────────────────────┐
│                     │<─────Connection─────> │                     │
│   Cloud Server      │                       │   Raspberry Pi      │
│   - Web Interface   │      HTTP/REST        │   - Camera Capture  │
│   - YOLOv8 Model    │<─────API Calls─────>  │   - Hardware Control│
│   - WebSocket Server│                       │   - WebSocket Client│
└─────────────────────┘                       └─────────────────────┘
         ▲                                              ▲
         │                                              │
         │                                              │
         ▼                                              ▼
┌─────────────────────┐                       ┌─────────────────────┐
│                     │                       │                     │
│   Web Browser       │                       │   PiDog Hardware    │
│   - Control Panel   │                       │   - Motors          │
│   - Video Feed      │                       │   - LEDs            │
│   - Stats Dashboard │                       │   - Distance Sensor │
└─────────────────────┘                       └─────────────────────┘
```

## 🔧 Configuration

### Options du serveur cloud

```bash
python cloud_server.py --host 0.0.0.0 --port 8000 --reload
```

### Options du client Raspberry Pi

```bash
python pidog_client.py --server ws://URL:PORT/ws --no-camera --debug
```

## 🔍 Dépannage de la connexion WebSocket

Si vous rencontrez des problèmes de connexion WebSocket entre le client et le serveur, voici quelques étapes de dépannage :

### 1. Vérifiez l'URL WebSocket correcte

Le format de l'URL dépend de l'environnement :
- **Local** : `ws://localhost:8000/ws/CLIENT_ID` ou `ws://IP_LOCALE:8000/ws/CLIENT_ID`
- **Production (Railway)** : `wss://killerrobot-production.up.railway.app/ws/CLIENT_ID`

**IMPORTANT** : L'URL WebSocket doit toujours inclure un ID client dans le chemin après `/ws/`. Sans cela, vous recevrez une erreur 403 Forbidden.

### 2. Problèmes courants et solutions

- **Erreur `403 Forbidden`** :
  ```
  WebSocket error: Handshake status 403 Forbidden
  ```
  Cette erreur se produit lorsque l'URL WebSocket ne contient pas d'ID client après `/ws/`. Assurez-vous que votre URL se termine par un identifiant unique, par exemple `/ws/pidog-client-1`.

- **Erreur `module 'websocket' has no attribute 'WebSocketApp'`** :
  ```bash
  pip uninstall websocket websocket-client
  pip install websocket-client
  ```

- **Erreur de connexion au serveur Railway** :
  - Vérifiez que vous utilisez le protocole sécurisé `wss://` au lieu de `ws://`
  - Les WebSockets sur Railway utilisent le port par défaut (443) et non 8080
  - Utilisez le script `test_websocket.py` pour tester la connexion sans le hardware

- **Erreur de certificat SSL** :
  - Le client est déjà configuré pour ignorer les vérifications SSL avec `sslopt={"cert_reqs": 0}`
  - Si nécessaire, ajoutez l'option `--no-check-certificate` dans les appels réseau

### 3. Utilisation de l'outil de test

```bash
python test_websocket.py --url wss://killerrobot-production.up.railway.app/ws/test-client
```

Ou pour un serveur local :
```bash
python test_websocket.py --url ws://localhost:8000/ws/test-client
```

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier LICENSE pour plus de détails.

## 🙏 Remerciements

* [SunFounder](https://www.sunfounder.com/) pour le robot PiDog
* [Ultralytics](https://ultralytics.com/) pour YOLOv8
* [FastAPI](https://fastapi.tiangolo.com/) pour le framework web
* [Railway](https://railway.app/) pour l'hébergement cloud 