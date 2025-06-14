#!/usr/bin/env python3
# PiDog Person Tracker - Simplified Version with Cloud Detection
# Controls PiDog robot with failsafe for component initialization failures

import cv2
import numpy as np
import time
import os
import threading
import socket
import argparse
import sys
import traceback
import platform
import requests
from io import BytesIO
from flask import Flask, Response, render_template_string, request, jsonify, send_from_directory
from flask_cors import CORS

# Constants
BARK_DISTANCE = 70  # Distance in cm to start barking
PURSUE_DISTANCE = 200  # Distance in cm to start pursuing
MAX_PURSUIT_DISTANCE = 400  # Maximum pursuit distance
EXPLOSION_DISTANCE = 20  # Distance in cm to trigger explosion warning
FPS_TARGET = 5  # Lower target FPS to save CPU resources
DETECTION_INTERVAL = 0.2  # Interval between detections in seconds
CONFIDENCE_THRESHOLD = 0.25  # Confidence threshold for detection
PERFORMANCE_MODE = "balanced"  # Options: "performance", "balanced", "quality"
DETECTION_PERSISTENCE = 10  # Number of frames to keep detection visible
CLOUD_API_TIMEOUT = 3  # Timeout for cloud API requests in seconds
MAX_RETRIES = 3  # Maximum number of retries for cloud API
USE_LOCAL_FALLBACK = True  # Use local model as fallback if cloud fails

# Global variables for web streaming
app = Flask(__name__)
CORS(app)  # Autoriser les requêtes cross-origin
outputFrame = None
lock = threading.Lock()
latest_distance = 100  # Valeur par défaut
auto_mode = False  # Start in manual mode for testing
my_dog = None  # Global variable for PiDog instance
camera_available = True  # Flag to track camera availability
model = None  # Will hold local YOLO model if available as fallback
cloud_api_url = None  # URL of the cloud API
last_cloud_request_time = 0  # Time of last cloud API request
cloud_api_success_count = 0  # Counter for successful cloud API requests
cloud_api_failure_count = 0  # Counter for failed cloud API requests

# Detection results
current_detections = []  # Current person detections
largest_person_bbox = None  # Current largest person bounding box
last_detection_confidence = 0.0  # Confidence of last detection
frames_since_last_detection = 0  # Frames since last successful detection

# Available components flags
has_rgb = True
has_imu = True
has_camera = True

# Distance sensor variables
ultrasonic_attribute = None
read_distance_method = None

# Function to send image to cloud API for detection
def detect_persons_cloud(image, retry_count=0):
    """Send image to cloud API for person detection"""
    global cloud_api_url, cloud_api_success_count, cloud_api_failure_count, last_cloud_request_time
    
    if cloud_api_url is None:
        print("Cloud API URL not set")
        return None
    
    # Record time of request
    last_cloud_request_time = time.time()
    
    try:
        # Compress the image to JPEG to reduce size
        _, img_encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 70])
        img_bytes = img_encoded.tobytes()
        
        # Prepare the request
        files = {'image': ('image.jpg', img_bytes, 'image/jpeg')}
        data = {'confidence': str(CONFIDENCE_THRESHOLD)}
        
        # Send the request to the cloud API
        response = requests.post(
            f"{cloud_api_url}/detect", 
            files=files, 
            data=data, 
            timeout=CLOUD_API_TIMEOUT
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            cloud_api_success_count += 1
            return response.json()
        else:
            print(f"Cloud API error: {response.status_code} - {response.text}")
            cloud_api_failure_count += 1
            
            # Retry if not reached max retries
            if retry_count < MAX_RETRIES:
                print(f"Retrying cloud API request ({retry_count + 1}/{MAX_RETRIES})...")
                time.sleep(0.5)  # Wait before retrying
                return detect_persons_cloud(image, retry_count + 1)
            
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to cloud API: {e}")
        cloud_api_failure_count += 1
        
        # Retry if not reached max retries
        if retry_count < MAX_RETRIES:
            print(f"Retrying cloud API request ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(0.5)  # Wait before retrying
            return detect_persons_cloud(image, retry_count + 1)
        
        return None

# Function to detect persons using local model (fallback)
def detect_persons_local(image):
    """Detect persons using local YOLOv8 model (fallback)"""
    global model
    
    if model is None:
        print("Local model not available for fallback")
        return None
    
    try:
        # Run YOLOv8 inference on the frame
        results = model(image, conf=CONFIDENCE_THRESHOLD, classes=0, verbose=False)  # Class 0 = person
        
        # Process results to match cloud API format
        detections = []
        
        for result in results:
            boxes = result.boxes.cpu().numpy()
            
            for box in boxes:
                # Get class ID
                class_id = int(box.cls[0])
                
                # If the detected object is a person
                if class_id == 0:
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Get confidence score
                    confidence_score = float(box.conf[0])
                    
                    # Add to detections list
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
        
        return {
            "success": True,
            "detections": detections,
            "image_size": {
                "width": image.shape[1],
                "height": image.shape[0]
            }
        }
        
    except Exception as e:
        print(f"Error in local detection: {e}")
        traceback.print_exc()
        return None

# Function to process detection results
def process_detection_results(results, current_frame):
    """Process detection results and update tracking variables"""
    global largest_person_bbox, last_detection_confidence, frames_since_last_detection, current_detections
    
    if results is None or not results.get("success", False):
        # No successful detection
        frames_since_last_detection += 1
        return
    
    # Get detections
    detections = results.get("detections", [])
    current_detections = detections
    
    if not detections:
        # No persons detected
        frames_since_last_detection += 1
        # Only clear after specified number of frames to reduce jitter
        if frames_since_last_detection > DETECTION_PERSISTENCE:
            largest_person_bbox = None
        return
    
    # Find the largest person (closest)
    largest_area = 0
    largest_detection = None
    
    for detection in detections:
        bbox = detection["bbox"]
        area = bbox["width"] * bbox["height"]
        
        if area > largest_area:
            largest_area = area
            largest_detection = detection
    
    if largest_detection:
        bbox = largest_detection["bbox"]
        largest_person_bbox = [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]]
        last_detection_confidence = largest_detection["confidence"]
        frames_since_last_detection = 0
        print(f"Person detected! Confidence: {last_detection_confidence:.2f}")

# Get the local IP address
def get_local_ip():
    try:
        # Create a socket to determine the IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's DNS server
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"  # Fallback to localhost

# HTML template for the web interface (updated with simpler design and no video if camera unavailable)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PiDog Control Interface</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #2a2a2a;
            text-align: center;
            color: #fff;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: #333;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(255,0,0,0.3);
            border: 1px solid #900;
        }
        h1 {
            color: #f00;
            text-shadow: 0 0 5px rgba(255,0,0,0.5);
        }
        .video-container {
            margin: 20px 0;
            position: relative;
            overflow: hidden;
            width: 100%;
            padding-top: 75%; /* 4:3 Aspect Ratio */
            border: 2px solid #f00;
            background-color: #000;
            display: {{ 'block' if has_camera else 'none' }};
        }
        .video-container img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        .no-camera-message {
            margin: 20px 0;
            padding: 20px;
            background-color: #000;
            border: 2px solid #f00;
            display: {{ 'none' if has_camera else 'block' }};
        }
        .controls {
            margin: 20px 0;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
        }
        button {
            padding: 10px 15px;
            font-size: 16px;
            cursor: pointer;
            background-color: #900;
            color: white;
            border: none;
            border-radius: 5px;
            transition: background-color 0.3s;
        }
        button:hover {
            background-color: #f00;
        }
        button:disabled {
            background-color: #555;
        }
        .mode-switch {
            margin: 20px 0;
        }
        .info {
            margin: 20px 0;
            padding: 10px;
            background-color: #444;
            border-radius: 5px;
            border-left: 4px solid #f00;
        }
        .status {
            margin: 20px 0;
            padding: 10px;
            background-color: #444;
            border-radius: 5px;
        }
        .logs {
            margin: 20px 0;
            padding: 10px;
            background-color: #222;
            border-radius: 5px;
            color: #0f0;
            font-family: monospace;
            text-align: left;
            height: 100px;
            overflow-y: auto;
        }
        .explosion-warning {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(255, 0, 0, 0.5);
            z-index: 1000;
            animation: pulse 0.5s infinite alternate;
            text-align: center;
            padding-top: 40vh;
            font-size: 48px;
            font-weight: bold;
            text-shadow: 0 0 10px #fff;
        }
        @keyframes pulse {
            from { background-color: rgba(255, 0, 0, 0.5); }
            to { background-color: rgba(255, 0, 0, 0.8); }
        }
    </style>
</head>
<body>
    <div id="explosion-warning" class="explosion-warning">
        ⚠️ EXPLOSION ⚠️<br>
        <span style="font-size: 24px">CIBLE ÉLIMINÉE</span>
    </div>

    <div class="container">
        <h1>PiDog Control</h1>
        
        <div class="video-container">
            <img src="/video_feed" alt="PiDog Camera">
        </div>
        
        <div class="no-camera-message">
            <p>Caméra non disponible - Contrôle manuel uniquement</p>
        </div>
        
        <div class="status">
            <p>Statut des composants:</p>
            <p>Caméra: <span style="color: {{ '#0f0' if has_camera else '#f00' }}">{{ 'Disponible' if has_camera else 'Non disponible' }}</span></p>
            <p>IMU: <span style="color: {{ '#0f0' if has_imu else '#f00' }}">{{ 'Disponible' if has_imu else 'Non disponible' }}</span></p>
            <p>LEDs RGB: <span style="color: {{ '#0f0' if has_rgb else '#f00' }}">{{ 'Disponible' if has_rgb else 'Non disponible' }}</span></p>
        </div>
        
        <div class="info">
            <p>Distance: <span id="distance">Scanning...</span> cm</p>
            <p>Mode: <span id="mode">{{ 'Autonome' if auto_mode else 'Manuel' }}</span></p>
        </div>
        
        <div class="mode-switch">
            <button onclick="toggleMode()" id="modeBtn" {{ 'disabled' if not has_camera else '' }}>
                {{ 'Passer en mode manuel' if auto_mode else 'Passer en mode autonome' }}
            </button>
        </div>
        
        <div class="controls">
            <button onclick="sendCommand('forward')" id="forwardBtn" {{ 'disabled' if auto_mode and has_camera else '' }}>Avancer</button>
            <button onclick="sendCommand('backward')" id="backwardBtn" {{ 'disabled' if auto_mode and has_camera else '' }}>Reculer</button>
            <button onclick="sendCommand('turn_left')" id="leftBtn" {{ 'disabled' if auto_mode and has_camera else '' }}>Tourner à gauche</button>
            <button onclick="sendCommand('turn_right')" id="rightBtn" {{ 'disabled' if auto_mode and has_camera else '' }}>Tourner à droite</button>
            <button onclick="sendCommand('stand')" id="standBtn" {{ 'disabled' if auto_mode and has_camera else '' }}>Debout</button>
            <button onclick="sendCommand('sit')" id="sitBtn" {{ 'disabled' if auto_mode and has_camera else '' }}>Assis</button>
            <button onclick="sendCommand('bark')" id="barkBtn">Aboyer</button>
            <button onclick="sendCommand('aggressive_mode')" id="aggressiveBtn">MODE ATTAQUE</button>
        </div>
        
        <div class="logs" id="logBox">
            <p>Logs du système:</p>
        </div>
    </div>

    <script>
        let explosionTimeout = null;
        
        // Fonction pour ajouter un message au log
        function log(message) {
            const logBox = document.getElementById('logBox');
            const now = new Date();
            const timestamp = now.toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.textContent = `[${timestamp}] ${message}`;
            logBox.appendChild(logEntry);
            logBox.scrollTop = logBox.scrollHeight;
        }
        
        // Update distance reading
        function updateDistance() {
            fetch('/distance')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('distance').textContent = data.distance;
                    
                    // Check for explosion warning
                    if (data.explosion_warning) {
                        showExplosion();
                        log('🔥 EXPLOSION DÉCLENCHÉE - CIBLE ÉLIMINÉE 🔥');
                    }
                    
                    setTimeout(updateDistance, 1000);
                })
                .catch(error => {
                    console.error('Error fetching distance:', error);
                    log('Erreur lors de la récupération de la distance');
                    setTimeout(updateDistance, 5000);  // Retry after 5 seconds on error
                });
        }
        
        // Show explosion warning
        function showExplosion() {
            const explosionWarning = document.getElementById('explosion-warning');
            explosionWarning.style.display = 'block';
            
            // Clear existing timeout if any
            if (explosionTimeout) {
                clearTimeout(explosionTimeout);
            }
            
            // Hide after 3 seconds
            explosionTimeout = setTimeout(() => {
                explosionWarning.style.display = 'none';
            }, 3000);
        }
        
        // Send command to the PiDog
        function sendCommand(command) {
            log(`Envoi de la commande: ${command}`);
            
            fetch('/command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ command: command }),
            })
            .then(response => response.json())
            .then(data => {
                console.log('Command sent:', data);
                log(`Réponse: ${data.message || data.status}`);
                
                // Check if this command triggered an explosion
                if (data.explosion_warning) {
                    showExplosion();
                    log('🔥 EXPLOSION DÉCLENCHÉE - CIBLE ÉLIMINÉE 🔥');
                }
            })
            .catch(error => {
                console.error('Error sending command:', error);
                log(`Erreur d'envoi de commande: ${error}`);
            });
        }
        
        // Toggle between auto and manual mode
        function toggleMode() {
            log('Changement de mode...');
            
            fetch('/toggle_mode')
                .then(response => response.json())
                .then(data => {
                    const modeBtn = document.getElementById('modeBtn');
                    const modeText = document.getElementById('mode');
                    const controlButtons = ['forwardBtn', 'backwardBtn', 'leftBtn', 'rightBtn', 'standBtn', 'sitBtn'];
                    
                    if (data.auto_mode) {
                        modeBtn.textContent = 'Passer en mode manuel';
                        modeText.textContent = 'Autonome';
                        log('Mode autonome activé');
                        controlButtons.forEach(id => {
                            document.getElementById(id).disabled = true;
                        });
                    } else {
                        modeBtn.textContent = 'Passer en mode autonome';
                        modeText.textContent = 'Manuel';
                        log('Mode manuel activé');
                        controlButtons.forEach(id => {
                            document.getElementById(id).disabled = false;
                        });
                    }
                })
                .catch(error => {
                    console.error('Error toggling mode:', error);
                    log(`Erreur de changement de mode: ${error}`);
                });
        }
        
        // Start updating distance when page loads
        document.addEventListener('DOMContentLoaded', function() {
            log('Interface de contrôle initialisée');
            updateDistance();
        });
    </script>
</body>
</html>
"""

# Fonction pour configurer la lecture du capteur de distance
def setup_distance_sensor(dog, debug=False):
    global ultrasonic_attribute, read_distance_method
    
    # Vérifier les attributs du PiDog pour trouver le capteur ultrasonique
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
        if debug:
            print("Attributs disponibles:")
            for attr in dir(dog):
                if not attr.startswith('_'):  # Ignorer les attributs privés
                    print(f"- {attr}")
        print("Tentative d'utilisation directe du capteur...")

    # Tester la fonction de lecture de distance
    print("Test de lecture du capteur...")
    test_successful = False
    test_value = None
    
    try:
        if ultrasonic_attribute:
            sensor = getattr(dog, ultrasonic_attribute)
            if hasattr(sensor, 'read_distance'):
                test_value = sensor.read_distance()
                print(f"Lecture de test via {ultrasonic_attribute}.read_distance(): {test_value}")
                read_distance_method = "standard"
                test_successful = True
            elif hasattr(sensor, 'read'):
                test_value = sensor.read()
                print(f"Lecture de test via {ultrasonic_attribute}.read(): {test_value}")
                read_distance_method = "read"
                test_successful = True
            elif hasattr(sensor, 'get_distance'):
                test_value = sensor.get_distance()
                print(f"Lecture de test via {ultrasonic_attribute}.get_distance(): {test_value}")
                read_distance_method = "get_distance"
                test_successful = True
        
        # Si les méthodes standards échouent, essayer d'accéder directement
        if not test_successful and hasattr(dog, 'read_distance'):
            test_value = dog.read_distance()
            print(f"Lecture de test via dog.read_distance(): {test_value}")
            ultrasonic_attribute = None
            read_distance_method = "direct_read_distance"
            test_successful = True
        elif not test_successful and hasattr(dog, 'get_distance'):
            test_value = dog.get_distance()
            print(f"Lecture de test via dog.get_distance(): {test_value}")
            ultrasonic_attribute = None
            read_distance_method = "direct_get_distance"
            test_successful = True
            
    except Exception as e:
        print(f"ERREUR lors du test de lecture: {e}")
        traceback.print_exc()
    
    return test_successful, test_value

# Fonction pour lire la distance selon la méthode détectée
def read_distance_sensor():
    global my_dog, ultrasonic_attribute, read_distance_method
    
    try:
        if ultrasonic_attribute:
            sensor = getattr(my_dog, ultrasonic_attribute)
            if read_distance_method == "standard":
                return sensor.read_distance()
            elif read_distance_method == "read":
                return sensor.read()
            elif read_distance_method == "get_distance":
                return sensor.get_distance()
        else:
            if read_distance_method == "direct_read_distance":
                return my_dog.read_distance()
            elif read_distance_method == "direct_get_distance":
                return my_dog.get_distance()
    except:
        pass
    
    return None

# Fonction pour lire la distance de manière fiable
def get_reliable_distance(max_attempts=3, valid_range=(0, 1000)):
    readings = []
    
    for _ in range(max_attempts):
        try:
            value = read_distance_sensor()
            if value is not None and isinstance(value, (int, float)) and value > valid_range[0] and value < valid_range[1]:
                readings.append(value)
        except:
            pass
        time.sleep(0.01)
    
    if readings:
        return round(sum(readings) / len(readings), 2)
    else:
        return None

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='PiDog Person Tracker with Remote Control')
    parser.add_argument('--web', action='store_true', help='Enable web interface')
    parser.add_argument('--port', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--headless', action='store_true', help='Run without displaying local video window')
    parser.add_argument('--no-camera', action='store_true', help='Run without camera (manual control only)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--performance-mode', choices=['performance', 'balanced', 'quality'], 
                        default=PERFORMANCE_MODE, help='Performance mode setting')
    parser.add_argument('--cloud-api', type=str, help='URL of the cloud detection API')
    parser.add_argument('--local-fallback', action='store_true', default=USE_LOCAL_FALLBACK, 
                      help='Use local model as fallback if cloud fails')
    args = parser.parse_args()
    
    # For global access
    global latest_distance, auto_mode, outputFrame, my_dog, has_rgb, has_imu, has_camera, model, cloud_api_url
    
    # Set cloud API URL
    cloud_api_url = args.cloud_api
    if cloud_api_url:
        print(f"Using cloud API for detection: {cloud_api_url}")
        
        # Test cloud API connection
        try:
            response = requests.get(f"{cloud_api_url}/health", timeout=5)
            if response.status_code == 200:
                print("Cloud API connection successful!")
                print(f"API status: {response.json()}")
            else:
                print(f"Cloud API returned status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Cloud API connection failed: {e}")
            print("Will attempt to use it anyway or fall back to local model if enabled.")
    
    # Diagnostic: CPU info
    try:
        import psutil
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        print(f"DIAGNOSTIC - CPU: {cpu_count} cores, Freq: {cpu_freq.current if cpu_freq else 'Unknown'} MHz")
        print(f"DIAGNOSTIC - Memory: Total={memory.total/1024/1024:.1f}MB, Available={memory.available/1024/1024:.1f}MB ({memory.percent}% used)")
    except:
        print("DIAGNOSTIC - Couldn't get system info")
    
    # Set performance parameters based on mode
    global DETECTION_INTERVAL, CONFIDENCE_THRESHOLD
    if args.performance_mode == 'performance':
        DETECTION_INTERVAL = 0.3  # Less frequent detection
        CONFIDENCE_THRESHOLD = 0.4  # Higher confidence needed
        print("PERFORMANCE MODE: Optimized for speed")
    elif args.performance_mode == 'quality':
        DETECTION_INTERVAL = 0.1  # More frequent detection
        CONFIDENCE_THRESHOLD = 0.2  # Lower confidence threshold
        print("QUALITY MODE: Optimized for detection accuracy")
    else:  # balanced
        DETECTION_INTERVAL = 0.2
        CONFIDENCE_THRESHOLD = 0.25
        print("BALANCED MODE: Compromise between speed and accuracy")
    
    # Détection automatique du mode headless
    # Sur Raspberry Pi, exécuter en mode headless par défaut pour éviter les erreurs XCB
    is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')
    if is_raspberry_pi:
        args.headless = True
        print("Système Raspberry Pi détecté - Mode headless activé automatiquement")
    
    # Check if camera should be disabled
    if args.no_camera:
        has_camera = False
    
    # Try to initialize PiDog with component failure handling
    print("Initializing PiDog with failsafe for component errors...")
    try:
        from pidog import Pidog
        my_dog = Pidog()
        print("PiDog initialized successfully")
        
        # Configurer le capteur de distance
        sensor_working, test_distance = setup_distance_sensor(my_dog, debug=args.debug)
        if sensor_working:
            print(f"Capteur de distance configuré avec succès. Valeur de test: {test_distance}")
        else:
            print("ERREUR: Impossible de configurer le capteur de distance!")
        
        # Try to stand - this will fail if IMU is not working
        try:
            my_dog.do_action('stand', speed=300)
            my_dog.wait_all_done()
            print("Stand action successful - IMU working")
        except Exception as e:
            print(f"Warning: Could not perform stand action: {e}")
            traceback.print_exc()
            has_imu = False
        
        # Check if RGB strip is available
        try:
            # Try to access the rgb_strip attribute
            if hasattr(my_dog, 'rgb_strip'):
                # Try to use it
                try:
                    my_dog.rgb_strip.set_mode('breath', 'red', delay=0.1)
                    time.sleep(0.5)
                    print("RGB strip working")
                except Exception as e:
                    print(f"Warning: RGB strip exists but failed to use: {e}")
                    traceback.print_exc()
                    has_rgb = False
            else:
                print("Warning: RGB strip not available on this PiDog")
                has_rgb = False
        except Exception as e:
            print(f"Error checking RGB: {e}")
            traceback.print_exc()
            has_rgb = False
        
        # Check if speaker is available and make a test sound
        try:
            if hasattr(my_dog, 'speak'):
                my_dog.speak('boot', 100)  # Less aggressive startup sound
                time.sleep(0.5)
                print("Speaker working")
            else:
                print("Warning: speak method not found")
        except Exception as e:
            print(f"Warning: Could not play sound: {e}")
            traceback.print_exc()
    except Exception as e:
        print(f"Critical error initializing PiDog: {e}")
        traceback.print_exc()
        print("Exiting...")
        return
    
    # Initialize camera if available
    if has_camera and not args.no_camera:
        try:
            # Try to initialize the camera using the simpler approach from test_cam.py
            print("Initializing camera with improved method...")
            
            # Initialize local model for fallback if requested
            if args.local_fallback and cloud_api_url:
                try:
                    print("Initializing local YOLOv8 model as fallback...")
                    from ultralytics import YOLO
                    model = YOLO("yolov8n.pt")  # Use the smallest model for best performance
                    print("Local YOLOv8 model loaded successfully as fallback")
                except Exception as e:
                    print(f"Warning: Could not load local YOLO model: {e}")
                    traceback.print_exc()
            # If no cloud API specified, initialize local model as primary
            elif not cloud_api_url:
                try:
                    print("Initializing local YOLOv8 model for detection...")
                    from ultralytics import YOLO
                    model = YOLO("yolov8n.pt")  # Use the smallest model for best performance
                    print("Local YOLOv8 model loaded successfully")
                except Exception as e:
                    print(f"Warning: Could not load YOLO model: {e}")
                    traceback.print_exc()
                    print("Running without person detection")
            
            # Initialize the camera with simpler approach
            cap = cv2.VideoCapture(0)
            
            # Wait a moment to allow camera to initialize
            time.sleep(1)
            
            # Test if camera is working by capturing a test frame
            ret, test_frame = cap.read()
            if not ret or test_frame is None:
                print("Error: Could not open camera or capture frame.")
                has_camera = False
            else:
                # Camera is working
                print(f"Camera initialized successfully. Frame size: {test_frame.shape[1]}x{test_frame.shape[0]}")
                
                # Update global frame for web streaming
                with lock:
                    outputFrame = test_frame.copy()
        except Exception as e:
            print(f"Error initializing camera: {e}")
            traceback.print_exc()
            has_camera = False
    else:
        has_camera = False
        cap = None
    
    # Start the Flask server in a separate thread if web interface is enabled
    if args.web:
        local_ip = get_local_ip()
        print(f"Starting web control interface on http://{local_ip}:{args.port}")
        webThread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=args.port, debug=False, use_reloader=False, threaded=True))
        webThread.daemon = True
        webThread.start()
    
    # Main loop - only run if camera is available
    if has_camera and cap is not None:
        print("Starting camera-based tracking.")
        if not args.headless:
            print("Press 'q' to quit.")
        
        # Variables for tracking
        last_detection_time = 0
        last_movement_time = 0
        last_fps_display_time = 0
        frame_count = 0
        detection_count = 0
        
        # Thread function pour capturer en continu
        def capture_frames():
            global outputFrame, lock
            while True:
                try:
                    if cap is None or not cap.isOpened():
                        print("Camera disconnected, attempting to reconnect...")
                        time.sleep(2)
                        continue
                        
                    # Capture frame-by-frame
                    ret, frame = cap.read()
                    
                    if not ret or frame is None:
                        print("Failed to capture frame, retrying...")
                        time.sleep(0.5)
                        continue
                    
                    # Update the frame for web streaming
                    with lock:
                        outputFrame = frame.copy()
                        
                    # Reduce CPU usage
                    time.sleep(0.05)
                except Exception as e:
                    print(f"Error in capture thread: {e}")
                    time.sleep(1)
        
        # Démarrer la capture dans un thread séparé
        capture_thread = threading.Thread(target=capture_frames)
        capture_thread.daemon = True
        capture_thread.start()
        
        # Main loop
        while True:
            # Control the frame rate
            time.sleep(1.0/FPS_TARGET)
            
            # Get the latest frame
            current_frame = None
            with lock:
                if outputFrame is not None:
                    current_frame = outputFrame.copy()
            
            if current_frame is None:
                print("No frame available")
                time.sleep(0.5)
                continue
            
            # Count frames for FPS calculation
            frame_count += 1
            current_time = time.time()
            
            # Measure processing time
            start_time = time.time()
            
            # Run detection at specified intervals
            if current_time - last_detection_time >= DETECTION_INTERVAL:
                detection_count += 1
                last_detection_time = current_time
                
                # Detect persons using cloud API or local fallback
                if cloud_api_url:
                    # Try cloud API
                    cloud_results = detect_persons_cloud(current_frame)
                    
                    if cloud_results:
                        # Process cloud results
                        process_detection_results(cloud_results, current_frame)
                    elif args.local_fallback and model is not None:
                        # Fallback to local model
                        print("Cloud API failed, falling back to local model")
                        local_results = detect_persons_local(current_frame)
                        process_detection_results(local_results, current_frame)
                elif model is not None:
                    # Use local model directly
                    local_results = detect_persons_local(current_frame)
                    process_detection_results(local_results, current_frame)
            else:
                # Not running detection this frame, increment counter
                frames_since_last_detection += 1
            
            # Always draw the bounding box if we have a detection, regardless of auto mode
            if largest_person_bbox is not None:
                x1, y1, x2, y2 = largest_person_bbox
                
                # Calculate center of bbox
                center_x = (x1 + x2) // 2
                
                # Draw bounding box with varying color based on freshness of detection
                # Newer detections are bright red, older ones fade to yellow
                fade_factor = min(1.0, frames_since_last_detection / DETECTION_PERSISTENCE)
                box_color = (0, int(255 * fade_factor), int(255 * (1-fade_factor)))
                
                # Thicker box for newer detections
                box_thickness = max(1, 3 - int(fade_factor * 2))
                
                # Draw bounding box
                cv2.rectangle(current_frame, (x1, y1), (x2, y2), box_color, box_thickness)
                
                # Add label with confidence score
                label = f"TARGET: {last_detection_confidence:.2f}"
                cv2.putText(current_frame, label, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, box_thickness - 1)
                
                # Only perform tracking actions in auto mode
                if auto_mode:
                    # Calculate head position for tracking
                    # Map image x-coordinate (0-640) to head yaw angle (-60 to 60 degrees)
                    frame_width = current_frame.shape[1]
                    head_yaw = ((center_x / frame_width) * 120) - 60
                    
                    # Move head to track person if IMU is available
                    if has_imu:
                        try:
                            my_dog.head_move([[head_yaw, 0, 0]], speed=300)
                        except Exception as e:
                            print(f"Warning: Could not move head: {e}")
                    
                    # Get distance using ultrasonic sensor
                    distance = get_reliable_distance()
                    if distance is not None:
                        latest_distance = distance  # Update global variable for web interface
                        print(f"Target distance: {distance} cm")
                        
                        # Display distance on frame
                        cv2.putText(current_frame, f"Distance: {latest_distance:.1f} cm", (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
                        # Move toward the person if in auto mode and not too close
                        if auto_mode and current_time - last_movement_time > 1.5:
                            last_movement_time = current_time
                            
                            # Person is within pursuit distance - move toward them
                            if distance < PURSUE_DISTANCE and distance > 15:  # 15cm minimum to avoid collision
                                print("Pursuing target...")
                                
                                # First align body with head angle
                                if abs(head_yaw) > 20:
                                    # Turn left or right based on head angle
                                    if head_yaw > 0:
                                        try:
                                            my_dog.do_action('turn_left', step_count=1, speed=300)
                                        except Exception as e:
                                            print(f"Warning: Could not turn left: {e}")
                                    else:
                                        try:
                                            my_dog.do_action('turn_right', step_count=1, speed=300)
                                        except Exception as e:
                                            print(f"Warning: Could not turn right: {e}")
                                else:
                                    # Move forward
                                    try:
                                        my_dog.do_action('forward', step_count=1, speed=300)
                                    except Exception as e:
                                        print(f"Warning: Could not move forward: {e}")
                                
                                # Bark if close enough
                                if distance < BARK_DISTANCE:
                                    try:
                                        if hasattr(my_dog, 'speak'):
                                            my_dog.speak('bark', 100)
                                        else:
                                            print("Warning: speak method not found")
                                    except Exception as e:
                                        print(f"Warning: Could not bark: {e}")

                                # Check for explosion distance
                                if distance < EXPLOSION_DISTANCE:
                                    print("🔥 TARGET TOO CLOSE! EXPLOSION TRIGGERED! 🔥")
                                    # Create visual explosion effect on the frame
                                    cv2.rectangle(current_frame, (0, 0), (current_frame.shape[1], current_frame.shape[0]), (0, 0, 255), 20)
                                    font_scale = 1.5
                                    text = "⚠️ EXPLOSION ⚠️"
                                    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 3)[0]
                                    text_x = (current_frame.shape[1] - text_size[0]) // 2
                                    text_y = (current_frame.shape[0] + text_size[1]) // 2
                                    cv2.putText(current_frame, text, (text_x, text_y), 
                                            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), 3)
                    else:
                        print("Could not get valid distance reading")
            
            # Calculate and display FPS (but not on every frame to save CPU)
            if current_time - last_fps_display_time >= 1.0:  # Update FPS display once per second
                fps = frame_count / (current_time - last_fps_display_time)
                frame_count = 0
                last_fps_display_time = current_time
                
                # Display information on frame
                cv2.putText(current_frame, f"FPS: {fps:.1f}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # Add diagnostic info
                if args.debug:
                    # Default diagnostic info
                    cv2.putText(current_frame, f"Det. interval: {DETECTION_INTERVAL}s", (10, 60), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    cv2.putText(current_frame, f"Conf. threshold: {CONFIDENCE_THRESHOLD}", (10, 80), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    
                    # Add cloud API info if enabled
                    if cloud_api_url:
                        api_status = "Connected" if cloud_api_success_count > cloud_api_failure_count else "Issues"
                        cv2.putText(current_frame, f"Cloud API: {api_status} ({cloud_api_success_count}/{cloud_api_success_count+cloud_api_failure_count})", 
                                   (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
            # Add status text showing mode
            mode_text = "AUTO" if auto_mode else "MANUAL"
            cv2.putText(current_frame, mode_text, (10, 120), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                       
            # Add IP address and port if web server is running
            if args.web:
                ip_text = f"Control: http://{get_local_ip()}:{args.port}"
                cv2.putText(current_frame, ip_text, (10, 150), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            # Update the frame for web streaming again (with overlays)
            with lock:
                outputFrame = current_frame.copy()
            
            # Display the frame with detections (unless in headless mode)
            if not args.headless:
                try:
                    cv2.imshow('PiDog Target Tracker', current_frame)
                    
                    # Break the loop if 'q' is pressed
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                except Exception as e:
                    print(f"Warning: Could not display frame: {e}")
    else:
        # If no camera, just wait for commands via web interface
        print("Running without camera. Use web interface for control.")
        try:
            while True:
                # Update distance for web interface
                distance = get_reliable_distance()
                if distance is not None:
                    latest_distance = distance
                    print(f"Current distance: {latest_distance} cm")
                else:
                    print("Could not get valid distance reading")
                
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nProgram interrupted by user.")
    
    # Cleanup
    if has_camera and cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    
    # Cleanup PiDog
    try:
        if has_imu:
            my_dog.do_action('sit', speed=300)
            my_dog.wait_all_done()
        if has_rgb:
            my_dog.rgb_strip.set_mode('off', 'black')
        my_dog.close()
    except Exception as e:
        print(f"Error during cleanup: {e}")
    
    print("Program ended.")

# Route pour les fichiers statiques (permet d'inclure des images/CSS/JS)
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# Flask routes
@app.route('/')
def index():
    """Home page route"""
    global auto_mode, has_camera, has_rgb, has_imu
    return render_template_string(HTML_TEMPLATE, auto_mode=auto_mode, 
                                 has_camera=has_camera, has_rgb=has_rgb, has_imu=has_imu)

def generate():
    """Video streaming generator function using simplified approach from test_cam.py"""
    global outputFrame, lock
    
    while True:
        # Wait until a frame is available
        with lock:
            if outputFrame is None:
                time.sleep(0.1)
                continue
            
            # Simple frame encoding
            try:
                ret, buffer = cv2.imencode('.jpg', outputFrame)
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except Exception as e:
                print(f"Frame encoding error: {e}")
                continue
        
        # Control streaming rate
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    """Route for video streaming - simplified version"""
    global has_camera
    if has_camera:
        return Response(generate(),
                      mimetype="multipart/x-mixed-replace; boundary=frame")
    else:
        print("Camera not available")
        return "No video feed available", 200

@app.route('/distance')
def get_distance():
    """API route to get the current distance reading"""
    global latest_distance
    # Check if target is within explosion range
    explosion_warning = latest_distance < EXPLOSION_DISTANCE if latest_distance is not None else False
    return jsonify({"distance": latest_distance, "explosion_warning": explosion_warning})

@app.route('/toggle_mode')
def toggle_mode():
    """API route to toggle between auto and manual modes"""
    global auto_mode
    auto_mode = not auto_mode
    print(f"Mode toggled to: {'auto' if auto_mode else 'manual'}")
    return jsonify({"auto_mode": auto_mode})

@app.route('/command', methods=['POST', 'OPTIONS'])
def execute_command():
    """API route to execute commands on the PiDog"""
    global my_dog, has_rgb, has_imu, latest_distance
    
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return jsonify({"status": "success"}), 200
    
    if request.method == 'POST':
        try:
            # Vérifier si la requête contient du JSON
            if not request.is_json:
                print("Invalid request: No JSON data")
                return jsonify({"status": "error", "message": "No JSON data provided"}), 400
            
            data = request.get_json()
            command = data.get('command')
            
            print(f"Received command: {command}")
            
            # Check for explosion condition
            explosion_warning = latest_distance < EXPLOSION_DISTANCE if latest_distance is not None else False
            
            if command:
                # Handle special commands
                if command == 'aggressive_mode':
                    # Extra aggressive display
                    try:
                        if hasattr(my_dog, 'speak'):
                            my_dog.speak('growl', 100)
                            time.sleep(0.2)
                            my_dog.speak('bark', 100)
                        else:
                            print("Warning: speak method not found")
                        if has_rgb:
                            my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                        print("Aggressive mode activated")
                    except Exception as e:
                        print(f"Error in aggressive mode: {e}")
                        traceback.print_exc()
                    return jsonify({"status": "success", "message": "Attack mode activated!", "explosion_warning": explosion_warning})
                
                elif command == 'bark':
                    try:
                        if hasattr(my_dog, 'speak'):
                            my_dog.speak('bark', 100)  # Son d'aboiement avec volume maximum
                        else:
                            print("Warning: speak method not found")
                        if has_rgb:
                            my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                        print("Bark command executed")
                    except Exception as e:
                        print(f"Error in bark command: {e}")
                        traceback.print_exc()
                    return jsonify({"status": "success", "message": "Bark command executed", "explosion_warning": explosion_warning})
                
                # Handle movement commands - check if IMU is required
                elif command in ['forward', 'backward', 'turn_left', 'turn_right', 'stand', 'sit']:
                    # Ces commandes requièrent l'IMU pour fonctionner correctement
                    if has_imu:
                        try:
                            print(f"Executing action: {command}")
                            result = my_dog.do_action(command, speed=300)
                            my_dog.wait_all_done()
                            print(f"Action completed with result: {result}")
                            return jsonify({"status": "success", "message": f"Command '{command}' executed successfully"})
                        except Exception as e:
                            print(f"Error executing command {command}: {e}")
                            traceback.print_exc()
                            return jsonify({"status": "error", "message": f"Error executing {command}: {str(e)}"})
                    else:
                        print(f"Cannot execute {command} - IMU not available")
                        return jsonify({"status": "error", "message": "IMU not available, movement commands are limited"})
                
                else:
                    print(f"Unknown command: {command}")
                    return jsonify({"status": "error", "message": f"Unknown command: {command}"})
            else:
                print("No command provided in request")
                return jsonify({"status": "error", "message": "No command provided"})
        except Exception as e:
            print(f"Error processing command request: {e}")
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
    finally:
        # Ensure proper cleanup
        cv2.destroyAllWindows()
        try:
            if my_dog is not None:
                my_dog.close()
        except:
            pass 