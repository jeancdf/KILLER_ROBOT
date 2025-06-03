#!/usr/bin/env python3
# PiDog Person Tracker - Aggressive Mode
# Detects, pursues humans and barks when close to intimidate them
# For use on Raspberry Pi with PiDog robot

import cv2
import numpy as np
import time
import os
import threading
import socket
import argparse
from ultralytics import YOLO
from pidog import Pidog
from flask import Flask, Response, render_template_string, request, jsonify

# Constants
PERSON_CLASS_ID = 0  # Class ID for 'person' in COCO dataset
BARK_DISTANCE = 70  # Distance in cm to start barking (increased range)
PURSUE_DISTANCE = 200  # Distance in cm to start pursuing
MAX_PURSUIT_DISTANCE = 400  # Maximum pursuit distance
FPS_TARGET = 5  # Lower target FPS to save CPU resources
DETECTION_INTERVAL = 0.5  # Seconds between detections
MOVEMENT_INTERVAL = 1.5  # Shorter interval for more aggressive movement
BARK_INTERVAL = 1.0  # Interval between barks

# Global variables for web streaming
app = Flask(__name__)
outputFrame = None
lock = threading.Lock()
latest_distance = 0
auto_mode = True  # By default, the dog operates autonomously
my_dog = None  # Global variable for PiDog instance

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

# HTML template for the web interface (updated with aggressive theme)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PiDog Attack Mode</title>
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
        }
        .video-container img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
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
    </style>
</head>
<body>
    <div class="container">
        <h1>PiDog ATTACK MODE</h1>
        
        <div class="video-container">
            <img src="/video_feed" alt="PiDog Attack Camera">
        </div>
        
        <div class="info">
            <p>Target Distance: <span id="distance">Scanning...</span> cm</p>
            <p>Mode: <span id="mode">{{ 'Autonomous Hunting' if auto_mode else 'Manual Control' }}</span></p>
        </div>
        
        <div class="mode-switch">
            <button onclick="toggleMode()" id="modeBtn">
                {{ 'Switch to Manual Mode' if auto_mode else 'Switch to Hunting Mode' }}
            </button>
        </div>
        
        <div class="controls">
            <button onclick="sendCommand('forward')" id="forwardBtn" {{ 'disabled' if auto_mode else '' }}>Advance</button>
            <button onclick="sendCommand('backward')" id="backwardBtn" {{ 'disabled' if auto_mode else '' }}>Retreat</button>
            <button onclick="sendCommand('turn_left')" id="leftBtn" {{ 'disabled' if auto_mode else '' }}>Turn Left</button>
            <button onclick="sendCommand('turn_right')" id="rightBtn" {{ 'disabled' if auto_mode else '' }}>Turn Right</button>
            <button onclick="sendCommand('stand')" id="standBtn" {{ 'disabled' if auto_mode else '' }}>Stand</button>
            <button onclick="sendCommand('sit')" id="sitBtn" {{ 'disabled' if auto_mode else '' }}>Sit</button>
            <button onclick="sendCommand('bark')" id="barkBtn">Bark</button>
            <button onclick="sendCommand('aggressive_mode')" id="aggressiveBtn">ATTACK!</button>
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
                        modeBtn.textContent = 'Switch to Manual Mode';
                        modeText.textContent = 'Autonomous Hunting';
                        controlButtons.forEach(id => {
                            document.getElementById(id).disabled = true;
                        });
                    } else {
                        modeBtn.textContent = 'Switch to Hunting Mode';
                        modeText.textContent = 'Manual Control';
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
    args = parser.parse_args()
    
    # For global access
    global latest_distance, auto_mode, outputFrame, my_dog
    
    # Initialize PiDog
    print("Initializing PiDog in AGGRESSIVE mode...")
    my_dog = Pidog()
    my_dog.do_action('stand', speed=90)  # Start with standing position, more energetic
    my_dog.wait_all_done()
    
    # Display aggressive startup behavior
    my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)  # Aggressive red flash
    my_dog.speaker.sound_effect('bark')  # Initial bark to show readiness
    time.sleep(0.5)
    my_dog.rgb_strip.set_mode('breath', 'red', delay=0.05)  # Pulsing red "breathing"
    
    # Load the YOLOv8n model
    print("Loading YOLOv8n model for target acquisition...")
    model = YOLO("yolov8n.pt")  # Will download if not available
    
    # Initialize camera
    print("Initializing camera for target tracking...")
    cap = cv2.VideoCapture(0)  # Use default camera
    
    # Check if camera is opened correctly
    if not cap.isOpened():
        print("Error: Could not open camera.")
        my_dog.close()
        return
    
    # Set camera properties for better performance
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)
    
    # Start the Flask server in a separate thread if web interface is enabled
    if args.web:
        local_ip = get_local_ip()
        print(f"Starting attack control station on http://{local_ip}:{args.port}")
        webThread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=args.port, debug=False, use_reloader=False))
        webThread.daemon = True
        webThread.start()
    
    print("Starting aggressive tracking. Press 'q' to quit.")
    
    # Variables for tracking
    last_detection_time = 0
    last_movement_time = 0
    last_bark_time = 0
    last_center_x = None
    last_bbox_height = None
    is_moving = False
    bark_intensity = 1  # Start with low intensity, increases as we get closer
    
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
        
        # Only run detection periodically to save CPU
        current_time = time.time()
        if current_time - last_detection_time > DETECTION_INTERVAL:
            # Run YOLOv8 inference on the frame
            results = model(frame, conf=0.35)  # Lower confidence threshold for more aggressive targeting
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
                    if class_id == PERSON_CLASS_ID:
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
            if largest_person_bbox is not None:
                x1, y1, x2, y2 = largest_person_bbox
                
                # Calculate center of bbox
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                bbox_height = y2 - y1
                
                # Draw bounding box with target-like appearance
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)  # Red for aggressive mode
                
                # Add label with confidence score
                label = f"TARGET: {confidence:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                # Add crosshair on target
                cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y), (0, 0, 255), 1)
                cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20), (0, 0, 255), 1)
                cv2.circle(frame, (center_x, center_y), 10, (0, 0, 255), 1)
                
                # Calculate head position for tracking
                # Map image x-coordinate (0-640) to head yaw angle (-60 to 60 degrees)
                frame_width = frame.shape[1]
                head_yaw = ((center_x / frame_width) * 120) - 60
                
                # Move head to track person more aggressively (faster speed)
                my_dog.head_move([[head_yaw, 0, 0]], speed=90)
                
                # Check distance using ultrasonic sensor
                distance = round(my_dog.ultrasonic.read_distance(), 2)
                latest_distance = distance  # Update global variable for web interface
                print(f"Target distance: {distance} cm")
                
                # Display distance on frame
                cv2.putText(frame, f"Distance: {distance:.1f} cm", (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # Adjust bark intensity based on distance
                if distance < BARK_DISTANCE:
                    bark_intensity = max(1, min(3, int((BARK_DISTANCE - distance) / (BARK_DISTANCE / 3)) + 1))
                else:
                    bark_intensity = 1
                
                # Bark with intensity increasing as we get closer to the target
                if (current_time - last_bark_time > BARK_INTERVAL / bark_intensity) and distance < BARK_DISTANCE:
                    print(f"Barking at target! Intensity: {bark_intensity}")
                    
                    # Different barks based on intensity
                    if bark_intensity == 1:
                        my_dog.speaker.sound_effect('bark')
                    elif bark_intensity == 2:
                        my_dog.speaker.sound_effect('bark')  # Bark twice in succession for intensity 2
                        time.sleep(0.1)
                        my_dog.speaker.sound_effect('bark')
                    else:
                        my_dog.speaker.sound_effect('growl')  # Most intense - growl instead of bark
                    
                    # Set LED color based on intensity
                    if bark_intensity == 1:
                        my_dog.rgb_strip.set_mode('breath', 'red', delay=0.05)
                    else:
                        my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                    
                    last_bark_time = current_time
                
                # Move aggressively toward the person in auto mode
                if auto_mode and current_time - last_movement_time > MOVEMENT_INTERVAL and not is_moving:
                    last_movement_time = current_time
                    
                    # Person is within pursuit distance - always move toward them
                    if distance < PURSUE_DISTANCE and distance > 15:  # 15cm minimum to avoid collision
                        print("Pursuing target...")
                        is_moving = True
                        
                        # First align body with head angle
                        if abs(head_yaw) > 20:
                            # Turn left or right based on head angle
                            if head_yaw > 0:
                                my_dog.do_action('turn_left', step_count=1, speed=90)
                            else:
                                my_dog.do_action('turn_right', step_count=1, speed=90)
                        else:
                            # Move forward aggressively with more steps if person is farther
                            steps = 2 if distance < 50 else 3
                            my_dog.do_action('forward', step_count=steps, speed=90)
                        
                        my_dog.wait_all_done()
                        is_moving = False
                    
                    # Person is farther away - move faster to catch up
                    elif distance >= PURSUE_DISTANCE and distance < MAX_PURSUIT_DISTANCE:
                        print("Target is escaping! Pursuing...")
                        is_moving = True
                        
                        # First align body with head angle
                        if abs(head_yaw) > 15:  # More aggressive turning
                            # Turn left or right based on head angle
                            if head_yaw > 0:
                                my_dog.do_action('turn_left', step_count=2, speed=95)
                            else:
                                my_dog.do_action('turn_right', step_count=2, speed=95)
                        else:
                            # Move forward with more steps and speed
                            my_dog.do_action('forward', step_count=3, speed=95)
                        
                        my_dog.wait_all_done()
                        is_moving = False
                
                # Store last position
                last_center_x = center_x
                last_bbox_height = bbox_height
            
            # No person detected - search mode
            else:
                # Look around actively for targets
                if auto_mode and current_time - last_movement_time > 3.0 and not is_moving:
                    print("Searching for targets...")
                    last_movement_time = current_time
                    is_moving = True
                    
                    # Randomly choose to turn or look around
                    action = np.random.choice(['turn_left', 'turn_right', 'shake_head'], p=[0.4, 0.4, 0.2])
                    
                    if action == 'shake_head':
                        my_dog.do_action('shake_head', speed=80)
                    else:
                        # Turn to look for targets
                        my_dog.do_action(action, step_count=1, speed=80)
                    
                    my_dog.wait_all_done()
                    is_moving = False
        
        # Calculate and display FPS
        fps = 1.0 / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Add status text showing mode
        mode_text = "HUNT MODE" if auto_mode else "MANUAL MODE"
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
    
    # Release the camera and close all windows
    cap.release()
    cv2.destroyAllWindows()
    
    # Cleanup PiDog
    my_dog.do_action('sit', speed=80)
    my_dog.wait_all_done()
    my_dog.close()
    print("Tracking stopped.")

# Flask routes
@app.route('/')
def index():
    """Home page route"""
    global auto_mode
    return render_template_string(HTML_TEMPLATE, auto_mode=auto_mode)

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
    return Response(generate(),
                   mimetype="multipart/x-mixed-replace; boundary=frame")

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
    global is_moving, my_dog
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            command = data.get('command')
            
            if command:
                # Handle special commands
                if command == 'aggressive_mode':
                    # Extra aggressive display
                    my_dog.speaker.sound_effect('growl')
                    my_dog.rgb_strip.set_mode('boom', 'red', delay=0.005)
                    time.sleep(0.2)
                    my_dog.speaker.sound_effect('bark')
                    time.sleep(0.1)
                    my_dog.speaker.sound_effect('bark')
                    return jsonify({"status": "success", "message": "Attack mode activated!"})
                
                # Only execute movement commands in manual mode
                if not auto_mode or command in ['bark', 'wag_tail']:
                    is_moving = True
                    
                    if command == 'bark':
                        my_dog.speaker.sound_effect('bark')
                        my_dog.rgb_strip.set_mode('boom', 'red', delay=0.01)
                    else:
                        my_dog.do_action(command, speed=90)  # Higher speed for aggressive movements
                        my_dog.wait_all_done()
                    
                    is_moving = False
                    return jsonify({"status": "success", "message": f"Command '{command}' executed"})
                else:
                    return jsonify({"status": "error", "message": "Can only execute movement commands in manual mode"})
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