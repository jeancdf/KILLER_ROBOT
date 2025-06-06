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
import base64
import random

# Constants
CAMERA_FPS = 10
DISTANCE_SENSOR_INTERVAL = 0.2  # Seconds between distance readings
WEBSOCKET_RECONNECT_INTERVAL = 5  # Seconds between reconnection attempts
MAX_RECONNECT_ATTEMPTS = -1  # Infinite reconnection attempts
COMMAND_TIMEOUT = 10  # Seconds to wait for command completion
EXPLOSION_DISTANCE = 20  # cm

# Global variables
ws = None  # WebSocket connection
ws_connected = False
shutdown_event = threading.Event()  # Signal for graceful shutdown
send_queue = queue.Queue()  # Queue for sending messages to server
auto_mode = False  # Default to manual mode
latest_distance = None  # Latest distance reading
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
    """Get a reliable distance reading by averaging multiple readings"""
    if not has_distance_sensor or read_distance_method is None:
        return None
        
    readings = []
    errors = 0
    
    for i in range(max_attempts):
        try:
            value = read_distance_method()
            
            # Check if the value is a valid number within range
            if value is not None and isinstance(value, (int, float)) and value >= valid_range[0] and value < valid_range[1]:
                readings.append(value)
            else:
                errors += 1
                print(f"Invalid distance reading: {value}")
        except Exception as e:
            errors += 1
            if i == 0:  # Only print error on first attempt to avoid spam
                print(f"Error reading distance: {e}")
        
        # Small delay between readings
        time.sleep(0.01)
    
    if readings:
        # Calculate average and round to 2 decimal places
        avg_distance = round(sum(readings) / len(readings), 2)
        
        # Update the latest_distance global variable
        global latest_distance
        latest_distance = avg_distance
        
        return avg_distance
    else:
        if errors == max_attempts:
            print("All distance readings failed!")
        return None

# Camera capture thread function
def camera_capture_thread():
    """Thread for capturing camera frames and sending to server"""
    global cap
    
    print("Camera capture thread started")
    
    frame_count = 0
    last_status_time = 0
    frame_interval = 1.0 / CAMERA_FPS  # Time between frames based on desired FPS
    
    while not shutdown_event.is_set():
        try:
            if cap is not None and has_camera:
                # Capture frame
                ret, frame = cap.read()
                
                if ret and frame is not None:
                    # Resize for network efficiency
                    frame = cv2.resize(frame, (640, 480))
                    
                    # Convert to JPEG with lower quality for better network performance
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]  # 70% quality
                    ret, buffer = cv2.imencode('.jpg', frame, encode_param)
                    
                    if ret:
                        # Convert to base64
                        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                        
                        # Create message
                        message = {
                            "type": "camera_frame",
                            "data": {
                                "frame": jpg_as_text,
                                "frame_id": frame_count,
                                "timestamp": time.time()
                            }
                        }
                        
                        # Send to server
                        try:
                            send_queue.put(json.dumps(message))
                            print(f"Frame {frame_count} sent, size: {len(jpg_as_text) // 1024}KB")
                        except Exception as e:
                            print(f"Error queuing frame: {e}")
                        
                        frame_count += 1
                        
                        # Send status update periodically
                        current_time = time.time()
                        if current_time - last_status_time > 5:  # Every 5 seconds
                            send_status_update()
                            last_status_time = current_time
                else:
                    print("Failed to capture frame, will retry")
                    time.sleep(0.5)
                    
                # Control frame rate to reduce network usage
                time.sleep(frame_interval)
            else:
                # Camera not available, sleep to avoid high CPU usage
                time.sleep(1)
                
        except Exception as e:
            print(f"Error in camera capture thread: {e}")
            traceback.print_exc()
            time.sleep(1)

# Distance sensor thread function
def distance_sensor_thread():
    """Thread for reading distance sensor and updating global distance"""
    global latest_distance
    
    print("Distance sensor thread started")
    
    while not shutdown_event.is_set():
        try:
            if has_distance_sensor:
                # Get distance reading
                distance = get_reliable_distance()
                
                if distance is not None:
                    # Update global distance
                    latest_distance = distance
                    
                    # In auto mode, react based on distance
                    if auto_mode and has_imu:
                        if distance < 20:  # Explosion distance
                            # Flash red and sound alarm
                            if has_rgb:
                                try:
                                    my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                                except:
                                    pass
                            if hasattr(my_dog, 'speak'):
                                try:
                                    my_dog.speak('bark', 100)
                                except:
                                    pass
                                    
                        elif distance < 70:  # Bark distance
                            # Bark at the target
                            if hasattr(my_dog, 'speak') and random.random() < 0.2:  # 20% chance to bark
                                try:
                                    my_dog.speak('bark', 100)
                                except:
                                    pass
        except Exception as e:
            print(f"Error in distance sensor thread: {e}")
            
        # Sleep to avoid high CPU usage
        time.sleep(0.5)

# WebSocket thread for sending data to server
def websocket_sender_thread():
    """Thread for sending messages to the server"""
    global ws, ws_connected
    
    print("WebSocket sender thread started")
    last_status_update = 0
    
    while not shutdown_event.is_set():
        try:
            if ws_connected:
                try:
                    # Get message from queue with timeout
                    message = send_queue.get(timeout=0.5)
                    
                    # Send message
                    ws.send(message)
                    
                    # Mark task as done
                    send_queue.task_done()
                    
                    # Send periodic status updates with distance data
                    current_time = time.time()
                    if current_time - last_status_update > 2:  # Send status every 2 seconds
                        send_status_update()
                        last_status_update = current_time
                        
                except queue.Empty:
                    # No message in queue, send status update periodically
                    current_time = time.time()
                    if current_time - last_status_update > 2:  # Send status every 2 seconds
                        send_status_update()
                        last_status_update = current_time
                except Exception as e:
                    print(f"Error sending message: {e}")
                    # Try to reconnect if there's an error
                    ws_connected = False
            else:
                # Not connected, sleep to avoid high CPU usage
                time.sleep(0.5)
        except Exception as e:
            print(f"Error in sender thread: {e}")
            time.sleep(0.5)

# WebSocket thread for receiving commands from server
def websocket_receiver_thread():
    """Thread for processing commands from server"""
    global ws, ws_connected, shutdown_event
    
    print("WebSocket receiver thread started")
    
    while not shutdown_event.is_set():
        try:
            # Only process commands if connected
            if not ws_connected:
                time.sleep(0.5)
                continue
                
            # Nothing to do here - commands are handled directly in on_message callback
            time.sleep(0.5)
                
        except Exception as e:
            print(f"Error in WebSocket receiver thread: {e}")
            time.sleep(0.5)

# WebSocket connection handlers
def on_message(ws, message):
    global auto_mode, my_dog
    try:
        print(f"Received message: {message}")
        data = json.loads(message)
        message_type = data.get('type')
        
        if message_type == 'command':
            command_type = data.get('command_type')
            command_data = data.get('data', {})
            
            print(f"Received command: {command_type} - {command_data}")
            debug_command(command_type, command_data, "Received from server")
            
            # Handle different command types
            if command_type == 'control':
                action = command_data.get('action')
                if action:
                    print(f"Executing control action: {action}")
                    success = handle_control_action(action)
                    
                    # Send a response confirming whether the action was executed
                    response = {
                        "type": "command_response",
                        "command_type": "control",
                        "action": action,
                        "status": "success" if success else "error",
                        "message": f"Action {action} executed successfully" if success else f"Failed to execute {action}",
                        "timestamp": time.time()
                    }
                    send_queue.put(json.dumps(response))
                    
                    # Send updated status after command execution
                    send_status_update()
                    
            elif command_type == 'rgb_control':
                mode = command_data.get('mode')
                color = command_data.get('color')
                if mode and color and has_rgb:
                    try:
                        my_dog.rgb_strip.set_mode(mode, color)
                        print(f"RGB set to {mode} {color}")
                        
                        # Send response
                        response = {
                            "type": "command_response",
                            "command_type": "rgb_control",
                            "status": "success",
                            "timestamp": time.time()
                        }
                        send_queue.put(json.dumps(response))
                    except Exception as e:
                        print(f"Error setting RGB: {e}")
                        traceback.print_exc()
                        
                        # Send error response
                        response = {
                            "type": "command_response",
                            "command_type": "rgb_control",
                            "status": "error",
                            "error": str(e),
                            "timestamp": time.time()
                        }
                        send_queue.put(json.dumps(response))
                        
            elif command_type == 'speak':
                sound = command_data.get('sound')
                if sound and hasattr(my_dog, 'speak'):
                    try:
                        my_dog.speak(sound, 100)
                        print(f"Playing sound: {sound}")
                        
                        # Send response
                        response = {
                            "type": "command_response",
                            "command_type": "speak",
                            "status": "success",
                            "timestamp": time.time()
                        }
                        send_queue.put(json.dumps(response))
                    except Exception as e:
                        print(f"Error playing sound: {e}")
                        traceback.print_exc()
                        
                        # Send error response
                        response = {
                            "type": "command_response",
                            "command_type": "speak",
                            "status": "error",
                            "error": str(e),
                            "timestamp": time.time()
                        }
                        send_queue.put(json.dumps(response))
                        
            elif command_type == 'set_mode':
                mode = command_data.get('mode')
                if mode in ['auto', 'manual']:
                    auto_mode = (mode == 'auto')
                    print(f"Mode changed to: {mode}")
                    
                    # Reset head position when switching to manual mode
                    if not auto_mode and has_imu:
                        try:
                            my_dog.head_move([[0, 0, 0]], speed=300)
                        except Exception as e:
                            print(f"Error resetting head position: {e}")
                            
                    # Send response
                    response = {
                        "type": "command_response",
                        "command_type": "set_mode",
                        "mode": mode,
                        "status": "success",
                        "timestamp": time.time()
                    }
                    send_queue.put(json.dumps(response))
                    
        elif message_type == 'connection_established':
            print(f"Connection confirmed with server. Client ID: {data.get('client_id')}")
            
            # Send initial status update
            send_status_update()
            
    except json.JSONDecodeError:
        print(f"Error: Received invalid JSON message: {message}")
    except Exception as e:
        print(f"Error handling message: {e}")
        traceback.print_exc()

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
        "data": {
            "has_camera": has_camera,
            "has_imu": has_imu,
            "has_rgb": has_rgb,
            "has_distance_sensor": has_distance_sensor,
            "ip_address": get_local_ip(),
            "hostname": socket.gethostname(),
            "timestamp": time.time(),
            "client_version": "1.0.1"  # Add version for tracking
        }
    }
    
    try:
        # Get initial distance reading for first status
        if has_distance_sensor and read_distance_method is not None:
            try:
                distance = get_reliable_distance()
                if distance is not None:
                    status["data"]["distance"] = distance
                    print(f"Initial distance reading: {distance} cm")
            except Exception as e:
                print(f"Error getting initial distance reading: {e}")
                
        # Send initial status
        send_queue.put(json.dumps(status))
        print("Initial status sent to server")
        
        # If camera is available, send a test frame to verify camera connection
        if has_camera and cap is not None:
            try:
                ret, frame = cap.read()
                if ret and frame is not None:
                    # Resize and compress
                    frame = cv2.resize(frame, (320, 240))  # Smaller test frame
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]  # Lower quality for test
                    ret, buffer = cv2.imencode('.jpg', frame, encode_param)
                    
                    if ret:
                        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                        test_frame_msg = {
                            "type": "camera_frame",
                            "data": {
                                "frame": jpg_as_text,
                                "frame_id": 0,
                                "timestamp": time.time(),
                                "test_frame": True
                            }
                        }
                        send_queue.put(json.dumps(test_frame_msg))
                        print("Test camera frame sent to server")
            except Exception as e:
                print(f"Error sending test camera frame: {e}")
                traceback.print_exc()
    except Exception as e:
        print(f"Error in on_open handler: {e}")
        traceback.print_exc()

# WebSocket connection manager thread
def websocket_connection_manager(server_url):
    global ws, ws_connected, shutdown_event
    
    reconnect_count = 0
    
    print(f"Starting WebSocket connection manager for server: {server_url}")
    
    while not shutdown_event.is_set():
        try:
            if not ws_connected:
                print(f"Connecting to WebSocket server: {server_url} (attempt {reconnect_count + 1})")
                
                # Add more logs for debugging
                print(f"Creating WebSocketApp object...")
                
                # Create new WebSocket connection with increased timeouts
                ws = websocket.WebSocketApp(server_url,
                                          on_open=on_open,
                                          on_message=on_message,
                                          on_error=on_error,
                                          on_close=on_close,
                                          header=["User-Agent: PiDog-Client/1.0"])
                
                print(f"WebSocketApp created successfully, starting connection...")
                
                # Start WebSocket connection in a separate thread with SSL verification disabled
                ws_thread = threading.Thread(target=ws.run_forever, 
                                           kwargs={
                                               'sslopt': {"cert_reqs": 0},  # Ignore SSL verification
                                               'ping_interval': 30,  # Send ping every 30 seconds
                                               'ping_timeout': 10,   # Wait 10 seconds for pong
                                               'skip_utf8_validation': True  # Skip UTF-8 validation for speed
                                           })
                ws_thread.daemon = True
                ws_thread.start()
                
                print(f"WebSocket thread started, waiting for connection...")
                
                # Wait for connection or timeout
                connection_timeout = 30  # 30 seconds timeout
                for i in range(connection_timeout * 10):  # Check every 0.1 seconds
                    if ws_connected:
                        reconnect_count = 0
                        print("Successfully connected to WebSocket server!")
                        break
                    time.sleep(0.1)
                    if i % 10 == 0:  # Log every second
                        print(f"Waiting for connection... {(i+1)/10}s")
                
                # If still not connected after timeout
                if not ws_connected:
                    print("Connection timed out, will retry...")
            
            # If connected, periodically send status updates and check connection
            if ws_connected:
                # Send ping every 30 seconds to keep connection alive
                send_ping()
                
                # Send status update every 5 seconds
                time.sleep(5)
                send_status_update()
            else:
                # If not connected, wait before retry with exponential backoff
                reconnect_count += 1
                wait_time = min(30, reconnect_count * 2)  # Exponential backoff up to 30 seconds
                print(f"Connection failed, retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                
        except Exception as e:
            print(f"Error in WebSocket connection manager: {e}")
            traceback.print_exc()
            time.sleep(5)  # Wait before retry on error

def handle_control_action(action):
    """Handle control actions received from the server"""
    global my_dog, has_imu, has_rgb
    
    if my_dog is None:
        print(f"Cannot execute {action} - PiDog not initialized")
        return False
        
    if not has_imu and action in ['forward', 'backward', 'turn_left', 'turn_right', 'stand', 'sit']:
        print(f"Cannot execute {action} - IMU not available")
        return False
        
    # Don't allow movement commands in auto mode unless it's bark or aggressive_mode
    if auto_mode and action not in ['bark', 'aggressive_mode']:
        print(f"Ignoring movement command {action} in auto mode")
        return False
        
    try:
        if action == 'forward':
            my_dog.do_action('forward', step_count=2, speed=300)
            print("Moving forward")
            return True
            
        elif action == 'backward':
            my_dog.do_action('backward', step_count=2, speed=300)
            print("Moving backward")
            return True
            
        elif action == 'turn_left':
            my_dog.do_action('turn_left', step_count=2, speed=300)
            print("Turning left")
            return True
            
        elif action == 'turn_right':
            my_dog.do_action('turn_right', step_count=2, speed=300)
            print("Turning right")
            return True
            
        elif action == 'stand':
            my_dog.do_action('stand', speed=300)
            print("Standing up")
            return True
            
        elif action == 'sit':
            my_dog.do_action('sit', speed=300)
            print("Sitting down")
            return True
            
        elif action == 'bark':
            if hasattr(my_dog, 'speak'):
                my_dog.speak('bark', 100)
                print("Barking")
                return True
            else:
                print("Bark not available")
                return False
                
        elif action == 'aggressive_mode':
            # Extra aggressive display
            success = False
            
            if hasattr(my_dog, 'speak'):
                try:
                    my_dog.speak('growl', 100)
                    time.sleep(0.2)
                    my_dog.speak('bark', 100)
                    print("Aggressive mode activated - sound played")
                    success = True
                except Exception as e:
                    print(f"Error playing aggressive sounds: {e}")
                    
            if has_rgb:
                try:
                    my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                    print("Aggressive mode activated - LED effect")
                    success = True
                except Exception as e:
                    print(f"Error setting aggressive LED mode: {e}")
                    
            return success
        else:
            print(f"Unknown action: {action}")
            return False
                
    except Exception as e:
        print(f"Error executing action {action}: {e}")
        traceback.print_exc()
        return False

def send_status_update():
    """Send robot status update to the server"""
    global latest_distance
    
    if not ws_connected:
        return
        
    # Get current distance reading
    distance = None
    if has_distance_sensor and read_distance_method is not None:
        try:
            distance = get_reliable_distance()
            # Print distance for debugging
            if distance is not None:
                print(f"Current distance: {distance} cm")
            else:
                print("Warning: Could not get valid distance reading")
        except Exception as e:
            print(f"Error reading distance sensor: {e}")
        
    status_data = {
        "type": "status_update",
        "data": {
            "has_camera": has_camera,
            "has_imu": has_imu,
            "has_rgb": has_rgb,
            "has_distance_sensor": has_distance_sensor,
            "distance": distance,
            "auto_mode": auto_mode,
            "timestamp": time.time(),
            "client_id": socket.gethostname(),
            "ip_address": get_local_ip()
        }
    }
    
    # Check for explosion condition
    if distance is not None and distance < EXPLOSION_DISTANCE:
        status_data["data"]["explosion_warning"] = True
        print("⚠️ EXPLOSION DISTANCE DETECTED! ⚠️")
    
    try:
        send_queue.put(json.dumps(status_data))
        print("Status update sent to server")
    except Exception as e:
        print(f"Error sending status update: {e}")

def handle_sensor_trigger(sensor_data):
    """Handle sensor triggers like explosion distance"""
    try:
        sensor_type = sensor_data.get("type")
        value = sensor_data.get("value")
        
        if sensor_type == "distance":
            # Check if distance is below threshold for alarm
            if value and value < 20:  # cm
                # Trigger explosion warning
                send_status_update()
                
                # Flash the LED strip red
                if has_rgb:
                    my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                
                # Make alarming sound
                if hasattr(my_dog, 'speak'):
                    my_dog.speak('growl', 100)
                    time.sleep(0.2)
                    my_dog.speak('bark', 100)
                
                # Add response to confirm action
                response = {
                    "type": "sensor_response",
                    "sensor": "distance",
                    "action": "explosion_warning",
                    "status": "triggered",
                    "timestamp": time.time()
                }
                send_queue.put(json.dumps(response))
                
            # Check if distance is within barking range
            elif value and value < 70:  # cm
                # Randomly bark at target (20% chance)
                if random.random() < 0.2 and hasattr(my_dog, 'speak'):
                    my_dog.speak('bark', 100)
                    
                    # Add response to confirm action
                    response = {
                        "type": "sensor_response",
                        "sensor": "distance",
                        "action": "bark_warning",
                        "status": "triggered",
                        "timestamp": time.time()
                    }
                    send_queue.put(json.dumps(response))
                    
    except Exception as e:
        print(f"Error handling sensor trigger: {e}")
        traceback.print_exc()

def handle_robot_action(action, params=None):
    """Execute robot action and send response to server"""
    if not my_dog:
        response = {
            "type": "action_response",
            "action": action,
            "success": False,
            "message": "PiDog not initialized"
        }
        send_queue.put(json.dumps(response))
        return
        
    try:
        params = params or {}
        success = False
        message = ""
        
        # Adjust speed if not specified
        if 'speed' not in params:
            params['speed'] = 300
            
        # Execute action based on type
        if action == 'forward':
            if has_imu:
                step_count = params.get('step_count', 2)
                my_dog.do_action('forward', step_count=step_count, speed=params['speed'])
                success = True
                message = f"Moved forward {step_count} steps"
            else:
                message = "Cannot move - IMU not available"
                
        elif action == 'backward':
            if has_imu:
                step_count = params.get('step_count', 2)
                my_dog.do_action('backward', step_count=step_count, speed=params['speed'])
                success = True
                message = f"Moved backward {step_count} steps"
            else:
                message = "Cannot move - IMU not available"
                
        elif action == 'turn_left':
            if has_imu:
                step_count = params.get('step_count', 2)
                my_dog.do_action('turn_left', step_count=step_count, speed=params['speed'])
                success = True
                message = f"Turned left {step_count} steps"
            else:
                message = "Cannot move - IMU not available"
                
        elif action == 'turn_right':
            if has_imu:
                step_count = params.get('step_count', 2)
                my_dog.do_action('turn_right', step_count=step_count, speed=params['speed'])
                success = True
                message = f"Turned right {step_count} steps"
            else:
                message = "Cannot move - IMU not available"
                
        elif action == 'stand':
            if has_imu:
                my_dog.do_action('stand', speed=params['speed'])
                success = True
                message = "Standing up"
            else:
                message = "Cannot stand - IMU not available"
                
        elif action == 'sit':
            if has_imu:
                my_dog.do_action('sit', speed=params['speed'])
                success = True
                message = "Sitting down"
            else:
                message = "Cannot sit - IMU not available"
                
        # Send response
        response = {
            "type": "action_response",
            "action": action,
            "success": success,
            "message": message
        }
        send_queue.put(json.dumps(response))
        
    except Exception as e:
        print(f"Error executing action {action}: {e}")
        traceback.print_exc()
        
        # Send error response
        response = {
            "type": "action_response",
            "action": action,
            "success": False,
            "message": str(e)
        }
        send_queue.put(json.dumps(response))

def send_ping():
    """Send ping message to server"""
    if ws_connected:
        status = {
            "type": "ping",
            "timestamp": time.time()
        }
        send_queue.put(json.dumps(status))

# Debug helper for troubleshooting commands
def debug_command(command_type, data, message=""):
    """Print detailed debug information about a command"""
    try:
        debug_enabled = os.environ.get("PIDOG_DEBUG", "0") == "1"
        if not debug_enabled:
            return
            
        print("\n" + "="*60)
        print(f"COMMAND DEBUG: {command_type}")
        print("-"*60)
        print(f"DATA: {json.dumps(data, indent=2)}")
        if message:
            print(f"MESSAGE: {message}")
        print("="*60 + "\n")
    except:
        pass  # Never let debug code crash the application

def main():
    # Parse command line arguments
    global has_camera, CAMERA_FPS
    
    parser = argparse.ArgumentParser(description='PiDog Client for Cloud Control')
    parser.add_argument('--server', type=str, default='wss://killerrobot-production.up.railway.app/ws/pidog-client',
                       help='WebSocket server URL (default: wss://killerrobot-production.up.railway.app/ws/pidog-client)')
    parser.add_argument('--client-id', type=str, default=f"pidog-{socket.gethostname()}-{int(time.time())}",
                       help='Client ID for WebSocket connection (default: auto-generated)')
    parser.add_argument('--no-camera', action='store_true',
                       help='Disable camera even if available')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode with verbose logging')
    parser.add_argument('--verbose-debug', action='store_true',
                       help='Enable extremely verbose debug output for command troubleshooting')
    parser.add_argument('--camera-fps', type=int, default=CAMERA_FPS,
                       help=f'Camera frames per second (default: {CAMERA_FPS})')
    parser.add_argument('--test-connection', action='store_true',
                       help='Test connection with server and exit')
    args = parser.parse_args()
    
    global has_camera, CAMERA_FPS
    
    # Set debug mode based on command line flag
    debug_mode = args.debug
    if debug_mode:
        print("Debug mode enabled - verbose logging will be shown")
        websocket.enableTrace(True)  # Enable WebSocket debug output
    
    # Set extremely verbose debug mode for command troubleshooting
    if args.verbose_debug:
        print("VERBOSE DEBUG MODE ENABLED - All commands will be logged in detail")
        os.environ["PIDOG_DEBUG"] = "1"
    
    # Update camera FPS if specified
    if args.camera_fps != CAMERA_FPS:
        CAMERA_FPS = args.camera_fps
        print(f"Camera FPS set to {CAMERA_FPS}")
    
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
    
    # Test mode - just try to connect to server and exit
    if args.test_connection:
        print("Running in test connection mode")
        try:
            print(f"Testing connection to {server_url}...")
            # Create a simple WebSocket connection
            ws = websocket.create_connection(server_url, sslopt={"cert_reqs": 0})
            print("Connection successful!")
            
            # Send a simple test message
            test_msg = {
                "type": "test_connection",
                "client_id": args.client_id,
                "timestamp": time.time()
            }
            ws.send(json.dumps(test_msg))
            print("Test message sent")
            
            # Try to receive a response
            print("Waiting for response...")
            try:
                response = ws.recv()
                print(f"Response received: {response}")
            except Exception as e:
                print(f"No response received: {e}")
                
            # Close connection
            ws.close()
            print("Test completed, exiting")
            return
        except Exception as e:
            print(f"Connection test failed: {e}")
            traceback.print_exc()
            return
    
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