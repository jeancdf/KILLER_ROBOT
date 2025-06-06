#!/usr/bin/env python3
# PiDog Client - Simplified client for cloud-based control
# Handles hardware interaction and sends data to cloud server
#
# Pour utiliser ce client avec l'instance cloud déployée :
# python pidog_client.py
#
# Le client se connectera automatiquement à https://killerrobot-production.up.railway.app:8080/ws
# Vous pouvez spécifier une autre URL avec l'option --server :
# python pidog_client.py --server ws://autre-adresse:port/ws
#
# Pour désactiver la caméra, utilisez l'option --no-camera :
# python pidog_client.py --no-camera

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
import json
import requests
import websocket
import queue
from io import BytesIO

# Constants
CAMERA_FPS = 10
DISTANCE_SENSOR_INTERVAL = 0.2  # Seconds between distance readings
WEBSOCKET_RECONNECT_INTERVAL = 5  # Seconds between reconnection attempts
MAX_RECONNECT_ATTEMPTS = -1  # Infinite reconnection attempts
COMMAND_TIMEOUT = 10  # Seconds to wait for command completion

# Global variables
ws = None  # WebSocket connection
ws_connected = False
command_queue = queue.Queue()  # Queue for commands from server
response_queue = queue.Queue()  # Queue for responses to server
shutdown_event = threading.Event()  # Signal for graceful shutdown
frame_queue = queue.Queue(maxsize=2)  # Queue for latest camera frame (small to avoid memory issues)

# Hardware status flags
has_rgb = True
has_imu = True
has_camera = True
has_distance_sensor = True

# Hardware references
my_dog = None
cap = None

# Distance sensor variables
ultrasonic_attribute = None
read_distance_method = None

# Get the local IP address
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's DNS server
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"  # Fallback to localhost

# Initialize hardware components with failsafe handling
def initialize_hardware():
    global my_dog, has_rgb, has_imu, has_camera, has_distance_sensor
    global ultrasonic_attribute, read_distance_method
    
    print("Initializing PiDog hardware with failsafe handling...")
    
    try:
        from pidog import Pidog
        my_dog = Pidog()
        print("PiDog base hardware initialized successfully")
        
        # Setup distance sensor
        try:
            # Try to identify the ultrasonic distance sensor
            if hasattr(my_dog, 'ultrasonic'):
                ultrasonic_attribute = 'ultrasonic'
                if hasattr(my_dog.ultrasonic, 'read'):
                    read_distance_method = my_dog.ultrasonic.read
                    print("Ultrasonic sensor found (using ultrasonic.read)")
                elif hasattr(my_dog.ultrasonic, 'distance'):
                    read_distance_method = my_dog.ultrasonic.distance
                    print("Ultrasonic sensor found (using ultrasonic.distance)")
                else:
                    print("Warning: Ultrasonic sensor found but no read method available")
                    has_distance_sensor = False
            elif hasattr(my_dog, 'sonar'):
                ultrasonic_attribute = 'sonar'
                if hasattr(my_dog.sonar, 'read'):
                    read_distance_method = my_dog.sonar.read
                    print("Sonar sensor found (using sonar.read)")
                elif hasattr(my_dog.sonar, 'distance'):
                    read_distance_method = my_dog.sonar.distance
                    print("Sonar sensor found (using sonar.distance)")
                else:
                    print("Warning: Sonar sensor found but no read method available")
                    has_distance_sensor = False
            else:
                print("Warning: No distance sensor found")
                has_distance_sensor = False
                
            # Test the sensor
            if has_distance_sensor and read_distance_method is not None:
                test_distance = read_distance_method()
                print(f"Distance sensor test reading: {test_distance} cm")
                if test_distance is None or not isinstance(test_distance, (int, float)):
                    print("Warning: Invalid distance reading, disabling sensor")
                    has_distance_sensor = False
        except Exception as e:
            print(f"Error configuring distance sensor: {e}")
            traceback.print_exc()
            has_distance_sensor = False
        
        # Check IMU by trying to stand
        try:
            my_dog.do_action('stand', speed=300)
            my_dog.wait_all_done()
            print("IMU working - Stand action successful")
        except Exception as e:
            print(f"Warning: IMU not working: {e}")
            traceback.print_exc()
            has_imu = False
        
        # Check RGB LED strip
        try:
            if hasattr(my_dog, 'rgb_strip'):
                my_dog.rgb_strip.set_mode('breath', 'blue', delay=0.1)
                time.sleep(0.5)
                print("RGB strip working")
            else:
                print("Warning: RGB strip not available")
                has_rgb = False
        except Exception as e:
            print(f"Warning: RGB strip not working: {e}")
            traceback.print_exc()
            has_rgb = False
        
        # Check speaker
        try:
            if hasattr(my_dog, 'speak'):
                my_dog.speak('boot', 80)  # Lower volume for testing
                print("Speaker working")
            else:
                print("Warning: Speaker not available")
        except Exception as e:
            print(f"Warning: Speaker not working: {e}")
            traceback.print_exc()
            
        # Return to sitting position
        if has_imu:
            try:
                my_dog.do_action('sit', speed=300)
                my_dog.wait_all_done()
            except Exception as e:
                print(f"Warning: Couldn't return to sitting position: {e}")
                
    except Exception as e:
        print(f"Critical error initializing PiDog: {e}")
        traceback.print_exc()
        return False
        
    return True

# Initialize camera
def initialize_camera():
    global cap, has_camera
    
    if has_camera:
        try:
            print("Initializing camera...")
            cap = cv2.VideoCapture(0)
            
            # Wait for camera to initialize
            time.sleep(1)
            
            # Test camera
            ret, test_frame = cap.read()
            if not ret or test_frame is None:
                print("Error: Could not capture frame, disabling camera")
                has_camera = False
                if cap is not None:
                    cap.release()
                    cap = None
            else:
                print(f"Camera initialized successfully. Frame size: {test_frame.shape[1]}x{test_frame.shape[0]}")
                # Set lower resolution for better performance
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                return True
        except Exception as e:
            print(f"Error initializing camera: {e}")
            traceback.print_exc()
            has_camera = False
    
    return False

# Read distance sensor with reliability check
def get_reliable_distance(max_attempts=3, valid_range=(0, 1000)):
    if not has_distance_sensor or read_distance_method is None:
        return None
        
    readings = []
    
    for _ in range(max_attempts):
        try:
            value = read_distance_method()
            if value is not None and isinstance(value, (int, float)) and value > valid_range[0] and value < valid_range[1]:
                readings.append(value)
        except Exception as e:
            pass
        time.sleep(0.01)
    
    if readings:
        return round(sum(readings) / len(readings), 2)
    else:
        return None

# Camera capture thread function
def camera_capture_thread():
    global cap, frame_queue, shutdown_event
    
    print("Starting camera capture thread")
    
    last_frame_time = 0
    frame_interval = 1.0 / CAMERA_FPS
    
    while not shutdown_event.is_set():
        try:
            current_time = time.time()
            
            # Control frame rate
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.01)
                continue
                
            # Check if camera is connected
            if cap is None or not cap.isOpened():
                print("Camera disconnected, attempting to reconnect...")
                initialize_camera()
                time.sleep(1)
                continue
            
            # Capture frame
            ret, frame = cap.read()
            if not ret or frame is None:
                print("Failed to capture frame")
                time.sleep(0.5)
                continue
                
            # Update frame queue (replace old frame)
            if frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass
            
            # Compress frame to reduce size
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            compressed_frame = buffer.tobytes()
            
            frame_queue.put(compressed_frame)
            last_frame_time = current_time
            
        except Exception as e:
            print(f"Error in camera thread: {e}")
            time.sleep(1)

# Distance sensor thread function
def distance_sensor_thread():
    global shutdown_event, response_queue
    
    print("Starting distance sensor thread")
    
    while not shutdown_event.is_set():
        try:
            # Read distance
            distance = get_reliable_distance()
            
            # Send to server if available
            if distance is not None:
                response = {
                    "type": "sensor_data",
                    "sensor": "distance",
                    "value": distance,
                    "timestamp": time.time()
                }
                response_queue.put(response)
                
            # Wait before next reading
            time.sleep(DISTANCE_SENSOR_INTERVAL)
        except Exception as e:
            print(f"Error in distance sensor thread: {e}")
            time.sleep(1)

# WebSocket thread for sending data to server
def websocket_sender_thread():
    global ws, ws_connected, response_queue, frame_queue, shutdown_event
    
    print("Starting WebSocket sender thread")
    
    while not shutdown_event.is_set():
        try:
            if not ws_connected:
                time.sleep(0.5)
                continue
                
            # Priority 1: Send responses to commands
            try:
                response = response_queue.get_nowait()
                ws.send(json.dumps(response))
                continue  # Continue to process more responses
            except queue.Empty:
                pass  # No responses to send
                
            # Priority 2: Send camera frames if available
            if has_camera:
                try:
                    frame_data = frame_queue.get_nowait()
                    # Create a message with the frame
                    message = {
                        "type": "camera_frame",
                        "timestamp": time.time(),
                        "frame_data": frame_data.hex()  # Convert binary to hex string
                    }
                    ws.send(json.dumps(message))
                except queue.Empty:
                    pass  # No frames to send
                    
            # Slow down if nothing to send
            time.sleep(0.05)
                
        except Exception as e:
            print(f"Error in WebSocket sender thread: {e}")
            time.sleep(0.5)

# WebSocket thread for receiving commands from server
def websocket_receiver_thread():
    global ws, ws_connected, command_queue, shutdown_event
    
    print("Starting WebSocket receiver thread")
    
    while not shutdown_event.is_set():
        try:
            if not ws_connected:
                time.sleep(0.5)
                continue
                
            # Get next command from queue
            try:
                command = command_queue.get(timeout=0.5)
                print(f"Processing command: {command['type']}")
                
                # Process the command
                if command["type"] == "robot_action":
                    action = command.get("action")
                    if action and has_imu:
                        try:
                            # Execute the action
                            result = my_dog.do_action(action, speed=command.get("speed", 300))
                            my_dog.wait_all_done()
                            
                            # Send response
                            response = {
                                "type": "action_response",
                                "action": action,
                                "success": True,
                                "message": f"Action {action} completed successfully"
                            }
                            response_queue.put(response)
                        except Exception as e:
                            error_msg = str(e)
                            print(f"Error executing action {action}: {error_msg}")
                            
                            # Send error response
                            response = {
                                "type": "action_response",
                                "action": action,
                                "success": False,
                                "message": f"Error: {error_msg}"
                            }
                            response_queue.put(response)
                
                elif command["type"] == "rgb_control":
                    if has_rgb:
                        try:
                            mode = command.get("mode", "breath")
                            color = command.get("color", "blue")
                            delay = command.get("delay", 0.1)
                            
                            my_dog.rgb_strip.set_mode(mode, color, delay=delay)
                            
                            # Send response
                            response = {
                                "type": "rgb_response",
                                "success": True,
                                "message": f"RGB set to {mode} {color}"
                            }
                            response_queue.put(response)
                        except Exception as e:
                            error_msg = str(e)
                            print(f"Error controlling RGB: {error_msg}")
                            
                            # Send error response
                            response = {
                                "type": "rgb_response",
                                "success": False,
                                "message": f"Error: {error_msg}"
                            }
                            response_queue.put(response)
                
                elif command["type"] == "speak":
                    if hasattr(my_dog, 'speak'):
                        try:
                            sound = command.get("sound", "bark")
                            volume = command.get("volume", 80)
                            
                            my_dog.speak(sound, volume)
                            
                            # Send response
                            response = {
                                "type": "speak_response",
                                "success": True,
                                "message": f"Played sound {sound}"
                            }
                            response_queue.put(response)
                        except Exception as e:
                            error_msg = str(e)
                            print(f"Error playing sound: {error_msg}")
                            
                            # Send error response
                            response = {
                                "type": "speak_response",
                                "success": False,
                                "message": f"Error: {error_msg}"
                            }
                            response_queue.put(response)
                
                elif command["type"] == "status_request":
                    # Send hardware status
                    status = {
                        "type": "status_response",
                        "has_camera": has_camera,
                        "has_imu": has_imu,
                        "has_rgb": has_rgb,
                        "has_distance_sensor": has_distance_sensor,
                        "ip_address": get_local_ip(),
                        "timestamp": time.time()
                    }
                    response_queue.put(status)
                
            except queue.Empty:
                pass  # No commands to process
                
            time.sleep(0.05)
                
        except Exception as e:
            print(f"Error in WebSocket receiver thread: {e}")
            time.sleep(0.5)

# WebSocket connection handlers
def on_message(ws, message):
    try:
        data = json.loads(message)
        command_type = data.get("type")
        
        if command_type:
            # Add the command to the queue
            command_queue.put(data)
        else:
            print(f"Received message with unknown format: {message}")
    except json.JSONDecodeError:
        print(f"Received invalid JSON: {message}")
    except Exception as e:
        print(f"Error processing message: {e}")

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    global ws_connected
    ws_connected = False
    print(f"WebSocket connection closed: {close_status_code} - {close_msg}")

def on_open(ws):
    global ws_connected
    ws_connected = True
    print("WebSocket connection established")
    
    # Send initial hardware status
    status = {
        "type": "status_response",
        "has_camera": has_camera,
        "has_imu": has_imu,
        "has_rgb": has_rgb,
        "has_distance_sensor": has_distance_sensor,
        "ip_address": get_local_ip(),
        "timestamp": time.time()
    }
    response_queue.put(status)

# WebSocket connection manager thread
def websocket_connection_manager(server_url):
    global ws, ws_connected, shutdown_event
    
    reconnect_count = 0
    
    print(f"Starting WebSocket connection manager for server: {server_url}")
    
    while not shutdown_event.is_set():
        try:
            if not ws_connected:
                print(f"Connecting to WebSocket server: {server_url} (attempt {reconnect_count + 1})")
                
                # Ajouter plus de logs pour le débogage
                print(f"Création de l'objet WebSocketApp...")
                
                # Create new WebSocket connection
                ws = websocket.WebSocketApp(server_url,
                                            on_open=on_open,
                                            on_message=on_message,
                                            on_error=on_error,
                                            on_close=on_close)
                
                print(f"WebSocketApp créé avec succès, démarrage de la connexion...")
                
                # Activer le mode debug si demandé
                websocket.enableTrace(false)
                
                # Start WebSocket connection in a separate thread
                ws_thread = threading.Thread(target=ws.run_forever, 
                                            kwargs={'sslopt': {"cert_reqs": 0}})  # Ignorer la vérification SSL
                ws_thread.daemon = True
                ws_thread.start()
                
                print(f"Thread WebSocket démarré, attente de connexion...")
                
                # Wait for connection or timeout
                for i in range(30):  # 3 seconds timeout
                    if ws_connected:
                        reconnect_count = 0
                        break
                    time.sleep(0.1)
                    if i % 10 == 0:  # Log every second
                        print(f"Attente de connexion... {(i+1)/10}s")
                
                if not ws_connected:
                    print("Failed to connect to WebSocket server")
                    reconnect_count += 1
            
            # Wait before checking connection again
            time.sleep(1)
            
        except Exception as e:
            print(f"Error in WebSocket connection manager: {e}")
            ws_connected = False
            reconnect_count += 1
            time.sleep(WEBSOCKET_RECONNECT_INTERVAL)
            
        # Check if max reconnect attempts reached
        if MAX_RECONNECT_ATTEMPTS > 0 and reconnect_count >= MAX_RECONNECT_ATTEMPTS:
            print(f"Maximum reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) reached. Giving up.")
            shutdown_event.set()
            break

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='PiDog Client for Cloud Control')
    parser.add_argument('--server', type=str, default='wss://killerrobot-production.up.railway.app/ws/pidog-client',
                       help='WebSocket server URL (default: wss://killerrobot-production.up.railway.app/ws/pidog-client)')
    parser.add_argument('--client-id', type=str, default=f"pidog-{socket.gethostname()}-{int(time.time())}",
                       help='Client ID for WebSocket connection (default: auto-generated)')
    parser.add_argument('--no-camera', action='store_true',
                       help='Disable camera even if available')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    args = parser.parse_args()
    
    global has_camera
    
    # If --no-camera flag is set, disable camera
    if args.no_camera:
        has_camera = False
        print("Camera disabled by command line argument")
    
    # Ensure URL includes client ID
    server_url = args.server
    if server_url.endswith('/ws'):
        server_url = f"{server_url}/{args.client_id}"
    elif '/ws/' in server_url and server_url.split('/ws/')[1] == '':
        server_url = f"{server_url}{args.client_id}"
    
    print(f"Using server URL: {server_url}")
    print(f"Client ID: {args.client_id}")
    
    # Print diagnostic information
    try:
        import psutil
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        memory = psutil.virtual_memory()
        print(f"DIAGNOSTIC - CPU: {cpu_count} cores, Freq: {cpu_freq.current if cpu_freq else 'Unknown'} MHz")
        print(f"DIAGNOSTIC - Memory: Total={memory.total/1024/1024:.1f}MB, Available={memory.available/1024/1024:.1f}MB ({memory.percent}% used)")
    except:
        print("DIAGNOSTIC - Couldn't get system info")
    
    # Initialize hardware
    if not initialize_hardware():
        print("Failed to initialize hardware, exiting")
        return
    
    # Initialize camera if enabled
    if has_camera:
        if not initialize_camera():
            print("Failed to initialize camera")
    
    # Create and start threads
    threads = []
    
    # Start distance sensor thread if available
    if has_distance_sensor:
        distance_thread = threading.Thread(target=distance_sensor_thread)
        distance_thread.daemon = True
        distance_thread.start()
        threads.append(distance_thread)
    
    # Start camera thread if available
    if has_camera and cap is not None:
        camera_thread = threading.Thread(target=camera_capture_thread)
        camera_thread.daemon = True
        camera_thread.start()
        threads.append(camera_thread)
    
    # Start WebSocket threads
    sender_thread = threading.Thread(target=websocket_sender_thread)
    sender_thread.daemon = True
    sender_thread.start()
    threads.append(sender_thread)
    
    receiver_thread = threading.Thread(target=websocket_receiver_thread)
    receiver_thread.daemon = True
    receiver_thread.start()
    threads.append(receiver_thread)
    
    # Start WebSocket connection manager
    connection_thread = threading.Thread(target=websocket_connection_manager, args=(server_url,))
    connection_thread.daemon = True
    connection_thread.start()
    threads.append(connection_thread)
    
    # Flash RGB to indicate ready if available
    if has_rgb:
        try:
            my_dog.rgb_strip.set_mode('boom', 'green', delay=0.05)
            time.sleep(1)
            my_dog.rgb_strip.set_mode('breath', 'blue', delay=0.1)
        except:
            pass
    
    print(f"PiDog client initialized and connected to {server_url}")
    print("Press Ctrl+C to exit")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        shutdown_event.set()
        
        # Clean up hardware
        if has_rgb:
            try:
                my_dog.rgb_strip.set_mode('off', 'black')
            except:
                pass
        
        if has_camera and cap is not None:
            cap.release()
        
        if my_dog is not None:
            try:
                if has_imu:
                    my_dog.do_action('sit', speed=300)
                    my_dog.wait_all_done()
                my_dog.close()
            except:
                pass
        
        print("Shutdown complete")

if __name__ == "__main__":
    main() 