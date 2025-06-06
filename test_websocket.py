#!/usr/bin/env python3
# WebSocket Test Client for PiDog Cloud Server
# Use this to test connection to the cloud server without hardware

import websocket
import threading
import time
import json
import argparse
import socket
import base64
import cv2
import numpy as np
import os
import sys
import traceback

# Constants
PING_INTERVAL = 5  # Seconds between pings
TEST_DURATION = 30  # Test duration in seconds
DEFAULT_SERVER = "wss://killerrobot-production.up.railway.app/ws/pidog-client"

# Test camera with local webcam if available
USE_TEST_CAMERA = True
TEST_CAMERA_FPS = 5
TEST_IMAGE_SIZE = (640, 480)

# Global variables
ws = None
ws_connected = False
shutdown_event = threading.Event()
test_distance = 100  # Simulated distance

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def on_message(ws, message):
    """Handler for incoming WebSocket messages"""
    try:
        data = json.loads(message)
        print(f"Received message: {data['type']}")
        
        # If we got a command, simulate response
        if data.get('type') == 'command':
            print(f"Command received: {data.get('command_type')} - {data.get('data', {})}")
            
            # Send fake response
            response = {
                "type": "command_response",
                "command_id": data.get('command_id', 'unknown'),
                "status": "success",
                "message": "Command simulated (no hardware)"
            }
            ws.send(json.dumps(response))
            
    except Exception as e:
        print(f"Error handling message: {e}")
        print(f"Raw message: {message}")

def on_error(ws, error):
    """Handler for WebSocket errors"""
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    """Handler for WebSocket close events"""
    global ws_connected
    ws_connected = False
    print(f"WebSocket connection closed: {close_status_code} - {close_msg}")

def on_open(ws):
    """Handler for WebSocket connection open"""
    global ws_connected
    ws_connected = True
    print("WebSocket connection established")
    
    # Send initial status
    status = {
        "type": "status_response",
        "data": {
            "has_camera": USE_TEST_CAMERA,
            "has_imu": False,
            "has_rgb": False,
            "has_distance_sensor": True,
            "ip_address": get_local_ip(),
            "hostname": socket.gethostname(),
            "timestamp": time.time(),
            "client_version": "test-client-1.0",
            "is_test_client": True
        }
    }
    ws.send(json.dumps(status))
    print("Initial status sent")

def status_thread_func():
    """Thread for sending periodic status updates"""
    print("Status thread started")
    global test_distance
    
    while not shutdown_event.is_set() and ws_connected:
        try:
            # Vary the test distance to simulate movement
            test_distance += np.random.randint(-5, 6)  # -5 to +5 cm change
            if test_distance < 10:  # Minimum 10cm
                test_distance = 10
            if test_distance > 200:  # Maximum 200cm
                test_distance = 200
                
            # Create status update
            status = {
                "type": "status_update",
                "data": {
                    "has_camera": USE_TEST_CAMERA,
                    "has_imu": False,
                    "has_rgb": False,
                    "has_distance_sensor": True,
                    "distance": test_distance,
                    "auto_mode": False,
                    "timestamp": time.time()
                }
            }
            
            # Add explosion warning if distance is small
            if test_distance < 20:
                status["data"]["explosion_warning"] = True
                print(f"⚠️ SIMULATED EXPLOSION WARNING! Distance: {test_distance}cm")
            
            # Send status update
            if ws_connected:
                ws.send(json.dumps(status))
                print(f"Status update sent. Distance: {test_distance}cm")
            
            # Sleep before next update
            time.sleep(2)
        except Exception as e:
            print(f"Error in status thread: {e}")
            time.sleep(5)

def camera_thread_func():
    """Thread for sending simulated camera frames"""
    if not USE_TEST_CAMERA:
        return
        
    print("Camera simulation thread started")
    frame_count = 0
    
    # Try to open local webcam if available
    local_webcam = False
    cap = None
    
    try:
        cap = cv2.VideoCapture(0)
        ret, test_frame = cap.read()
        if ret and test_frame is not None:
            local_webcam = True
            print("Using local webcam for test frames")
        else:
            print("Local webcam not available, using test pattern")
            cap.release()
            cap = None
    except Exception as e:
        print(f"Error accessing webcam: {e}")
        if cap is not None:
            cap.release()
            cap = None
    
    while not shutdown_event.is_set() and ws_connected:
        try:
            # Create frame (either from webcam or test pattern)
            if local_webcam and cap is not None:
                ret, frame = cap.read()
                if not ret or frame is None:
                    raise Exception("Failed to capture frame from webcam")
            else:
                # Create a test pattern
                frame = np.zeros((*TEST_IMAGE_SIZE, 3), dtype=np.uint8)
                
                # Add some visual elements
                cv2.putText(frame, "TEST PATTERN", (50, 50), 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Frame: {frame_count}", (50, 100), 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Distance: {test_distance}cm", (50, 150), 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, f"Time: {time.strftime('%H:%M:%S')}", (50, 200), 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # Draw a moving element
                x = int(100 + 100 * np.sin(frame_count / 10))
                y = int(300 + 50 * np.cos(frame_count / 15))
                cv2.circle(frame, (x, y), 30, (0, 0, 255), -1)
            
            # Resize frame
            frame = cv2.resize(frame, TEST_IMAGE_SIZE)
            
            # Compress frame
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
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
                        "timestamp": time.time(),
                        "test_client": True
                    }
                }
                
                # Send to server
                if ws_connected:
                    ws.send(json.dumps(message))
                    print(f"Frame {frame_count} sent, size: {len(jpg_as_text) // 1024}KB")
                
                frame_count += 1
            
            # Control frame rate
            time.sleep(1.0 / TEST_CAMERA_FPS)
        except Exception as e:
            print(f"Error in camera thread: {e}")
            time.sleep(1)
    
    # Clean up webcam if used
    if cap is not None:
        cap.release()

def ping_thread_func():
    """Thread for sending ping messages to keep connection alive"""
    print("Ping thread started")
    
    while not shutdown_event.is_set() and ws_connected:
        try:
            # Send ping message
            if ws_connected:
                ping_msg = {
                    "type": "ping",
                    "timestamp": time.time()
                }
                ws.send(json.dumps(ping_msg))
                print("Ping sent")
            
            # Sleep before next ping
            time.sleep(PING_INTERVAL)
        except Exception as e:
            print(f"Error in ping thread: {e}")
            time.sleep(1)

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='WebSocket Test Client for PiDog Cloud Server')
    parser.add_argument('--url', type=str, default=DEFAULT_SERVER,
                       help=f'WebSocket server URL (default: {DEFAULT_SERVER})')
    parser.add_argument('--client-id', type=str, default=f"test-{socket.gethostname()}-{int(time.time())}",
                       help='Client ID for WebSocket connection (default: auto-generated)')
    parser.add_argument('--no-camera', action='store_true',
                       help='Disable camera test')
    parser.add_argument('--debug', action='store_true',
                       help='Enable WebSocket debug output')
    args = parser.parse_args()
    
    global USE_TEST_CAMERA
    
    # Set debug mode if requested
    if args.debug:
        websocket.enableTrace(True)
    
    # Update camera flag if requested
    if args.no_camera:
        USE_TEST_CAMERA = False
    
    # Ensure URL includes client ID
    server_url = args.url
    if server_url.endswith('/ws'):
        server_url = f"{server_url}/{args.client_id}"
    elif '/ws/' in server_url and server_url.split('/ws/')[1] == '':
        server_url = f"{server_url}{args.client_id}"
    elif not 'client-id' in server_url.lower() and not args.client_id in server_url:
        if '?' in server_url:
            server_url = f"{server_url}&client-id={args.client_id}"
        else:
            server_url = f"{server_url}?client-id={args.client_id}"
    
    print(f"Connecting to: {server_url}")
    print(f"Client ID: {args.client_id}")
    print(f"Test duration: {TEST_DURATION} seconds")
    print(f"Camera simulation: {'Enabled' if USE_TEST_CAMERA else 'Disabled'}")
    
    # Create WebSocket connection
    global ws
    ws = websocket.WebSocketApp(server_url,
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    
    # Start WebSocket in a thread
    ws_thread = threading.Thread(target=ws.run_forever, kwargs={
        'sslopt': {"cert_reqs": 0},  # Ignore SSL verification
        'ping_interval': 30,
        'ping_timeout': 10
    })
    ws_thread.daemon = True
    ws_thread.start()
    
    # Wait for connection
    connection_timeout = 10
    print("Waiting for connection...")
    for i in range(connection_timeout * 10):
        if ws_connected:
            print("Connected!")
            break
        time.sleep(0.1)
        if i % 10 == 0:
            print(f"Waiting... {i//10}/{connection_timeout}s")
    
    if not ws_connected:
        print("Connection failed! Exiting.")
        return
    
    # Start threads
    threads = []
    
    status_thread = threading.Thread(target=status_thread_func)
    status_thread.daemon = True
    status_thread.start()
    threads.append(status_thread)
    
    ping_thread = threading.Thread(target=ping_thread_func)
    ping_thread.daemon = True
    ping_thread.start()
    threads.append(ping_thread)
    
    if USE_TEST_CAMERA:
        camera_thread = threading.Thread(target=camera_thread_func)
        camera_thread.daemon = True
        camera_thread.start()
        threads.append(camera_thread)
    
    # Run for specified duration
    try:
        print(f"Test running for {TEST_DURATION} seconds...")
        start_time = time.time()
        while time.time() - start_time < TEST_DURATION and ws_connected:
            time.sleep(1)
            
        print("Test completed")
    except KeyboardInterrupt:
        print("Test interrupted by user")
    finally:
        # Clean shutdown
        shutdown_event.set()
        print("Closing WebSocket connection...")
        if ws is not None:
            ws.close()
        
        # Wait for threads to finish
        for thread in threads:
            thread.join(timeout=1)
            
        print("Test finished")

if __name__ == "__main__":
    main() 