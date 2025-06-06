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

1. Copiez le fichier `pidog_client.py` sur votre Raspberry Pi

2. Installez les dépendances :
   ```bash
   pip install websocket-client opencv-python requests
   ```

3. Exécutez le client en spécifiant l'URL du serveur cloud :
   ```bash
   python pidog_client.py --server ws://VOTRE_URL_RAILWAY/ws
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

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier LICENSE pour plus de détails.

## 🙏 Remerciements

* [SunFounder](https://www.sunfounder.com/) pour le robot PiDog
* [Ultralytics](https://ultralytics.com/) pour YOLOv8
* [FastAPI](https://fastapi.tiangolo.com/) pour le framework web
* [Railway](https://railway.app/) pour l'hébergement cloud 