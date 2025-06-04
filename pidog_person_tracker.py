#!/usr/bin/env python3
# PiDog Person Tracker - Simplified Version
# Controls PiDog robot with failsafe for component initialization failures

import cv2
import numpy as np
import time
import os
import threading
import socket
import argparse
import sys
from flask import Flask, Response, render_template_string, request, jsonify

# Constants
BARK_DISTANCE = 70  # Distance in cm to start barking
PURSUE_DISTANCE = 200  # Distance in cm to start pursuing
MAX_PURSUIT_DISTANCE = 400  # Maximum pursuit distance
FPS_TARGET = 5  # Lower target FPS to save CPU resources

# Global variables for web streaming
app = Flask(__name__)
outputFrame = None
lock = threading.Lock()
latest_distance = 0
auto_mode = True  # By default, the dog operates autonomously
my_dog = None  # Global variable for PiDog instance
camera_available = True  # Flag to track camera availability
model = None  # Will hold YOLO model if available

# Available components flags
has_rgb = True
has_imu = True
has_camera = True

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
    </style>
</head>
<body>
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
    </div>

    <script>
        // Update distance reading
        function updateDistance() {
            fetch('/distance')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('distance').textContent = data.distance;
                    setTimeout(updateDistance, 1000);
                })
                .catch(error => {
                    console.error('Error fetching distance:', error);
                    setTimeout(updateDistance, 5000);  // Retry after 5 seconds on error
                });
        }
        
        // Send command to the PiDog
        function sendCommand(command) {
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
            })
            .catch(error => {
                console.error('Error sending command:', error);
            });
        }
        
        // Toggle between auto and manual mode
        function toggleMode() {
            fetch('/toggle_mode')
                .then(response => response.json())
                .then(data => {
                    const modeBtn = document.getElementById('modeBtn');
                    const modeText = document.getElementById('mode');
                    const controlButtons = ['forwardBtn', 'backwardBtn', 'leftBtn', 'rightBtn', 'standBtn', 'sitBtn'];
                    
                    if (data.auto_mode) {
                        modeBtn.textContent = 'Passer en mode manuel';
                        modeText.textContent = 'Autonome';
                        controlButtons.forEach(id => {
                            document.getElementById(id).disabled = true;
                        });
                    } else {
                        modeBtn.textContent = 'Passer en mode autonome';
                        modeText.textContent = 'Manuel';
                        controlButtons.forEach(id => {
                            document.getElementById(id).disabled = false;
                        });
                    }
                })
                .catch(error => {
                    console.error('Error toggling mode:', error);
                });
        }
        
        // Start updating distance when page loads
        document.addEventListener('DOMContentLoaded', function() {
            updateDistance();
        });
    </script>
</body>
</html>
"""

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='PiDog Person Tracker with Remote Control')
    parser.add_argument('--web', action='store_true', help='Enable web interface')
    parser.add_argument('--port', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--headless', action='store_true', help='Run without displaying local video window')
    parser.add_argument('--no-camera', action='store_true', help='Run without camera (manual control only)')
    args = parser.parse_args()
    
    # For global access
    global latest_distance, auto_mode, outputFrame, my_dog, has_rgb, has_imu, has_camera, model
    
    # Check if camera should be disabled
    if args.no_camera:
        has_camera = False
    
    # Try to initialize PiDog with component failure handling
    print("Initializing PiDog with failsafe for component errors...")
    try:
        from pidog import Pidog
        my_dog = Pidog()
        
        # Try to stand - this will fail if IMU is not working
        try:
            my_dog.do_action('stand', speed=80)
            my_dog.wait_all_done()
        except Exception as e:
            print(f"Warning: Could not perform stand action: {e}")
            has_imu = False
        
        # Check if RGB strip is available
        try:
            # Try to access the rgb_strip attribute
            if hasattr(my_dog, 'rgb_strip'):
                # Try to use it
                try:
                    my_dog.rgb_strip.set_mode('breath', 'red', delay=0.1)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Warning: RGB strip exists but failed to use: {e}")
                    has_rgb = False
            else:
                print("Warning: RGB strip not available on this PiDog")
                has_rgb = False
        except:
            has_rgb = False
        
        # Check if speaker is available and make a test sound
        try:
            if hasattr(my_dog, 'speaker'):
                my_dog.speaker.sound_effect('boot')  # Less aggressive startup sound
                time.sleep(0.5)
            else:
                print("Warning: Speaker not available on this PiDog")
        except Exception as e:
            print(f"Warning: Could not play sound: {e}")
    except Exception as e:
        print(f"Critical error initializing PiDog: {e}")
        print("Exiting...")
        return
    
    # Initialize camera if available
    if has_camera and not args.no_camera:
        try:
            # Try to initialize the camera
            print("Initializing camera...")
            
            # Try to initialize YOLO model
            try:
                from ultralytics import YOLO
                model = YOLO("yolov8n.pt")
                print("YOLOv8 model loaded successfully")
            except Exception as e:
                print(f"Warning: Could not load YOLO model: {e}")
                print("Running without person detection")
            
            # Initialize the camera
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("Error: Could not open camera.")
                has_camera = False
            else:
                # Set camera properties
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 15)
        except Exception as e:
            print(f"Error initializing camera: {e}")
            has_camera = False
    else:
        has_camera = False
        cap = None
    
    # Start the Flask server in a separate thread if web interface is enabled
    if args.web:
        local_ip = get_local_ip()
        print(f"Starting web control interface on http://{local_ip}:{args.port}")
        webThread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=args.port, debug=False, use_reloader=False))
        webThread.daemon = True
        webThread.start()
    
    # Main loop - only run if camera is available
    if has_camera and cap is not None:
        print("Starting camera-based tracking. Press 'q' to quit.")
        
        # Variables for tracking
        last_detection_time = 0
        last_movement_time = 0
        
        # Main loop
        while True:
            # Control the frame rate
            time.sleep(1.0/FPS_TARGET)
            
            # Capture frame-by-frame
            ret, frame = cap.read()
            
            if not ret:
                print("Error: Failed to capture image")
                break
            
            # Measure processing time
            start_time = time.time()
            
            # Only run detection if model is available
            if model is not None:
                current_time = time.time()
                if current_time - last_detection_time > 0.5:  # Run detection every 0.5 seconds
                    # Run YOLOv8 inference on the frame
                    results = model(frame, conf=0.35, classes=0)  # Class 0 = person
                    last_detection_time = current_time
                    
                    # Process results
                    largest_person_bbox = None
                    largest_area = 0
                    
                    for result in results:
                        boxes = result.boxes.cpu().numpy()
                        
                        # Find the largest person in the frame (likely closest)
                        for box in boxes:
                            # Get class ID
                            class_id = int(box.cls[0])
                            
                            # If the detected object is a person
                            if class_id == 0:
                                # Get bounding box coordinates
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                
                                # Calculate area
                                area = (x2 - x1) * (y2 - y1)
                                
                                # Keep track of the largest person
                                if area > largest_area:
                                    largest_area = area
                                    largest_person_bbox = [x1, y1, x2, y2]
                                    confidence = float(box.conf[0])
                    
                    # If we found a person
                    if largest_person_bbox is not None and auto_mode:
                        x1, y1, x2, y2 = largest_person_bbox
                        
                        # Calculate center of bbox
                        center_x = (x1 + x2) // 2
                        
                        # Draw bounding box
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        
                        # Add label with confidence score
                        label = f"TARGET: {confidence:.2f}"
                        cv2.putText(frame, label, (x1, y1 - 10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                        
                        # Calculate head position for tracking
                        # Map image x-coordinate (0-640) to head yaw angle (-60 to 60 degrees)
                        frame_width = frame.shape[1]
                        head_yaw = ((center_x / frame_width) * 120) - 60
                        
                        # Move head to track person if IMU is available
                        if has_imu:
                            try:
                                my_dog.head_move([[head_yaw, 0, 0]], speed=80)
                            except Exception as e:
                                print(f"Warning: Could not move head: {e}")
                        
                        # Check distance using ultrasonic sensor
                        try:
                            distance = round(my_dog.ultrasonic.read_distance(), 2)
                            latest_distance = distance  # Update global variable for web interface
                            print(f"Target distance: {distance} cm")
                            
                            # Display distance on frame
                            cv2.putText(frame, f"Distance: {distance:.1f} cm", (10, 60), 
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
                                                my_dog.do_action('turn_left', step_count=1, speed=80)
                                            except Exception as e:
                                                print(f"Warning: Could not turn left: {e}")
                                        else:
                                            try:
                                                my_dog.do_action('turn_right', step_count=1, speed=80)
                                            except Exception as e:
                                                print(f"Warning: Could not turn right: {e}")
                                    else:
                                        # Move forward
                                        try:
                                            my_dog.do_action('forward', step_count=1, speed=80)
                                        except Exception as e:
                                            print(f"Warning: Could not move forward: {e}")
                                    
                                    # Bark if close enough
                                    if distance < BARK_DISTANCE:
                                        try:
                                            if hasattr(my_dog, 'speaker'):
                                                my_dog.speaker.sound_effect('bark')
                                        except Exception as e:
                                            print(f"Warning: Could not bark: {e}")
                        except Exception as e:
                            print(f"Error reading distance: {e}")
                            latest_distance = 0  # Set to 0 when unavailable
            
            # Calculate and display FPS
            fps = 1.0 / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Add status text showing mode
            mode_text = "AUTO" if auto_mode else "MANUAL"
            cv2.putText(frame, mode_text, (10, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                       
            # Add IP address and port if web server is running
            if args.web:
                ip_text = f"Control: http://{get_local_ip()}:{args.port}"
                cv2.putText(frame, ip_text, (10, 120), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            # Update the frame for web streaming
            with lock:
                outputFrame = frame.copy()
            
            # Display the frame with detections (unless in headless mode)
            if not args.headless:
                cv2.imshow('PiDog Target Tracker', frame)
                
                # Break the loop if 'q' is pressed
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    else:
        # If no camera, just wait for commands via web interface
        print("Running without camera. Use web interface for control.")
        try:
            while True:
                # Update distance for web interface
                try:
                    if hasattr(my_dog, 'ultrasonic'):
                        latest_distance = round(my_dog.ultrasonic.read_distance(), 2)
                except:
                    latest_distance = 0
                
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
            my_dog.do_action('sit', speed=80)
            my_dog.wait_all_done()
        if has_rgb:
            my_dog.rgb_strip.set_mode('off', 'black')
        my_dog.close()
    except Exception as e:
        print(f"Error during cleanup: {e}")
    
    print("Program ended.")

# Flask routes
@app.route('/')
def index():
    """Home page route"""
    global auto_mode, has_camera, has_rgb, has_imu
    return render_template_string(HTML_TEMPLATE, auto_mode=auto_mode, 
                                 has_camera=has_camera, has_rgb=has_rgb, has_imu=has_imu)

def generate():
    """Video streaming generator function"""
    global outputFrame, lock
    
    while True:
        with lock:
            if outputFrame is None:
                continue
            
            # Encode the frame in JPEG format
            (flag, encodedImage) = cv2.imencode(".jpg", outputFrame)
            
            if not flag:
                continue
        
        # Yield the output frame in the byte format
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
              bytearray(encodedImage) + b'\r\n')
        
        # Sleep to control streaming rate
        time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    """Route for video streaming"""
    global has_camera
    if has_camera:
        return Response(generate(),
                      mimetype="multipart/x-mixed-replace; boundary=frame")
    else:
        return "Camera not available", 404

@app.route('/distance')
def get_distance():
    """API route to get the current distance reading"""
    global latest_distance
    return jsonify({"distance": latest_distance})

@app.route('/toggle_mode')
def toggle_mode():
    """API route to toggle between auto and manual modes"""
    global auto_mode
    auto_mode = not auto_mode
    return jsonify({"auto_mode": auto_mode})

@app.route('/command', methods=['POST'])
def execute_command():
    """API route to execute commands on the PiDog"""
    global my_dog, has_rgb, has_imu
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            command = data.get('command')
            
            if command:
                # Handle special commands
                if command == 'aggressive_mode':
                    # Extra aggressive display
                    try:
                        if hasattr(my_dog, 'speaker'):
                            my_dog.speaker.sound_effect('growl')
                            time.sleep(0.2)
                            my_dog.speaker.sound_effect('bark')
                        if has_rgb:
                            my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                    except Exception as e:
                        print(f"Error in aggressive mode: {e}")
                    return jsonify({"status": "success", "message": "Attack mode activated!"})
                
                elif command == 'bark':
                    try:
                        if hasattr(my_dog, 'speaker'):
                            my_dog.speaker.sound_effect('bark')
                        if has_rgb:
                            my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                    except Exception as e:
                        print(f"Error in bark command: {e}")
                    return jsonify({"status": "success", "message": "Bark command executed"})
                
                # Handle movement commands - check if IMU is required
                elif command in ['forward', 'backward', 'turn_left', 'turn_right', 'stand', 'sit']:
                    # These commands require the IMU to work properly
                    if has_imu:
                        try:
                            my_dog.do_action(command, speed=80)
                            my_dog.wait_all_done()
                            return jsonify({"status": "success", "message": f"Command '{command}' executed"})
                        except Exception as e:
                            print(f"Error executing command {command}: {e}")
                            return jsonify({"status": "error", "message": f"Error executing {command}: {str(e)}"})
                    else:
                        return jsonify({"status": "error", "message": "IMU not available, movement commands are limited"})
                
                else:
                    return jsonify({"status": "error", "message": f"Unknown command: {command}"})
            else:
                return jsonify({"status": "error", "message": "No command provided"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Ensure proper cleanup
        cv2.destroyAllWindows()
        try:
            if my_dog is not None:
                my_dog.close()
        except:
            pass 