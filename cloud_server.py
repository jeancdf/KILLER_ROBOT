#!/usr/bin/env python3
# PiDog Cloud Server - Central server for PiDog control
# Handles web interface, AI detection, and communication with Raspberry Pi

import os
import cv2
import numpy as np
import time
import json
import threading
import logging
import base64
import asyncio
import uvicorn
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, File, UploadFile, Form, Body
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("pidog_cloud")

# Log startup information
logger.info("Starting PiDog Cloud Server")
logger.info(f"Python version: {sys.version}")
logger.info(f"Current directory: {os.getcwd()}")
logger.info(f"Files in current directory: {os.listdir('.')}")

# Constants
DETECTION_CONFIDENCE_THRESHOLD = 0.25
CAMERA_FRAME_BUFFER_SIZE = 10
DETECTION_INTERVAL = 0.5  # Seconds between detections

# Global variables
app = FastAPI(title="PiDog Cloud Control")
model = None
model_loaded = False
model_loading = False
clients = {}  # Connected clients
latest_frames = {}  # Latest frames from each client
latest_detections = {}  # Latest detections for each client
client_status = {}  # Status of each client

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates for web interface
try:
    templates_dir = "templates"
    if not os.path.exists(templates_dir):
        logger.warning(f"Templates directory '{templates_dir}' does not exist, creating it")
        os.makedirs(templates_dir, exist_ok=True)
    templates = Jinja2Templates(directory=templates_dir)
    logger.info(f"Templates directory initialized: {templates_dir}")
except Exception as e:
    logger.error(f"Error initializing templates directory: {e}")
    # Fallback to empty directory
    templates = Jinja2Templates(directory=".")

# Serve static files
try:
    static_dir = "static"
    if not os.path.exists(static_dir):
        logger.warning(f"Static directory '{static_dir}' does not exist, creating it")
        os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"Static directory mounted: {static_dir}")
except Exception as e:
    logger.error(f"Error mounting static directory: {e}")

# Data models
class ClientCommand(BaseModel):
    client_id: str
    command_type: str
    data: Dict[str, Any]

class DetectionResult(BaseModel):
    success: bool
    detections: List[Dict[str, Any]]
    inference_time: float = 0.0
    image_size: Dict[str, int]

# Function to load the YOLOv8 model
def load_model():
    global model, model_loaded, model_loading
    
    if model_loaded:
        return True
    
    if model_loading:
        logger.info("Model is already loading, waiting...")
        return False
    
    model_loading = True
    
    try:
        logger.info("Loading YOLOv8 model...")
        from ultralytics import YOLO
        
        # Check if model file exists
        model_path = "yolov8n.pt"
        if not os.path.exists(model_path):
            logger.error(f"Model file not found: {model_path}")
            logger.info(f"Files in current directory: {os.listdir('.')}")
            model_loading = False
            return False
        
        # Load the model
        start_time = time.time()
        model = YOLO(model_path)
        
        # Optimize model placement
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("Using CUDA for model inference")
                model.to('cuda')
            else:
                logger.info("Using CPU for model inference")
                model.to('cpu')
        except Exception as e:
            logger.warning(f"Error optimizing model placement: {e}")
        
        # Warm up the model
        logger.info("Warming up model with dummy image")
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        model(dummy_img, conf=DETECTION_CONFIDENCE_THRESHOLD, classes=0, verbose=False)
        
        model_loaded = True
        load_time = time.time() - start_time
        logger.info(f"YOLOv8 model loaded in {load_time:.2f} seconds")
        model_loading = False
        return True
        
    except Exception as e:
        logger.error(f"Error loading YOLOv8 model: {e}")
        model_loading = False
        return False

# Function to perform person detection on an image
def detect_persons(image):
    global model, model_loaded
    
    if not model_loaded:
        logger.warning("Cannot perform detection, model not loaded")
        return {
            "success": False,
            "detections": [],
            "inference_time": 0,
            "image_size": {
                "width": image.shape[1],
                "height": image.shape[0]
            }
        }
    
    try:
        # Start timing
        start_time = time.time()
        
        # Run inference
        results = model(image, conf=DETECTION_CONFIDENCE_THRESHOLD, classes=0, verbose=False)  # class 0 = person
        
        # Calculate inference time
        inference_time = time.time() - start_time
        
        # Extract detections
        detections = []
        
        for result in results:
            boxes = result.boxes.cpu().numpy()
            
            for box in boxes:
                # Get class ID
                class_id = int(box.cls[0])
                
                # If it's a person (class 0)
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
            "inference_time": inference_time,
            "image_size": {
                "width": image.shape[1],
                "height": image.shape[0]
            }
        }
        
    except Exception as e:
        logger.error(f"Error in person detection: {e}")
        return {
            "success": False,
            "detections": [],
            "inference_time": 0,
            "image_size": {
                "width": image.shape[1],
                "height": image.shape[0]
            },
            "error": str(e)
        }

# Background detection task
async def run_detection_on_client_frames():
    logger.info("Starting background detection task")
    while True:
        try:
            # Process each client's latest frame
            for client_id, frame_data in latest_frames.items():
                # Skip if no frame data
                if frame_data is None:
                    continue
                
                # Convert hex string to binary
                try:
                    # Check if we need to process a new detection
                    last_detection_time = latest_detections.get(client_id, {}).get("timestamp", 0)
                    current_time = time.time()
                    
                    # Only run detection if enough time has passed
                    if current_time - last_detection_time >= DETECTION_INTERVAL:
                        frame_bytes = bytes.fromhex(frame_data["frame_data"])
                        # Decode image
                        frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
                        
                        if frame is not None:
                            # Run detection
                            detection_result = detect_persons(frame)
                            
                            if detection_result:
                                # Add timestamp and save result
                                detection_result["timestamp"] = current_time
                                latest_detections[client_id] = detection_result
                                
                                # Log detection information
                                num_detections = len(detection_result["detections"])
                                logger.info(f"Client {client_id}: Detected {num_detections} persons in {detection_result.get('inference_time', 0):.3f}s")
                
                except Exception as e:
                    logger.error(f"Error processing frame from client {client_id}: {e}")
            
            # Sleep to control detection frequency
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error in detection task: {e}")
            await asyncio.sleep(1)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.lock = threading.Lock()

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        with self.lock:
            self.active_connections[client_id] = websocket
            clients[client_id] = {"connected_at": time.time()}
        logger.info(f"Client {client_id} connected")

    def disconnect(self, client_id: str):
        with self.lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
            if client_id in clients:
                del clients[client_id]
            if client_id in latest_frames:
                del latest_frames[client_id]
            if client_id in latest_detections:
                del latest_detections[client_id]
            if client_id in client_status:
                del client_status[client_id]
        logger.info(f"Client {client_id} disconnected")

    async def send_message(self, client_id: str, message: Dict[str, Any]):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
                return True
            except Exception as e:
                logger.error(f"Error sending message to client {client_id}: {e}")
                return False
        return False

    async def broadcast(self, message: Dict[str, Any]):
        for client_id in list(self.active_connections.keys()):
            await self.send_message(client_id, message)

# Initialize connection manager
manager = ConnectionManager()

# Routes
@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Error rendering home page: {e}")
        # Return a simple HTML response as fallback
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>PiDog Cloud Control</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                h1 {{ color: #c62828; }}
            </style>
        </head>
        <body>
            <h1>PiDog Cloud Control</h1>
            <p>Server is running. Template error: {str(e)}</p>
            <p>Please connect your PiDog client to start controlling your robot.</p>
        </body>
        </html>
        """)

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint for Railway's healthcheck system.
    Returns status of the server and model loading.
    """
    try:
        return {
            "status": "ok",
            "model_loaded": model_loaded,
            "model_loading": model_loading,
            "server_time": time.time(),
            "clients_connected": len(clients),
            "environment": os.environ.get("DEPLOYMENT_ENV", "development")
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/clients")
async def get_clients():
    return JSONResponse({
        "clients": list(clients.keys()),
        "status": client_status
    })

@app.get("/client/{client_id}/status")
async def get_client_status(client_id: str):
    if client_id in client_status:
        return JSONResponse(client_status[client_id])
    return JSONResponse({"error": "Client not found"}, status_code=404)

@app.post("/client/{client_id}/command")
async def send_command(client_id: str, command: ClientCommand):
    if client_id not in clients:
        return JSONResponse({"error": "Client not found"}, status_code=404)
    
    # Prepare command for client
    message = {
        "type": command.command_type,
        **command.data
    }
    
    # Send command to client
    success = await manager.send_message(client_id, message)
    
    if success:
        return JSONResponse({"status": "success", "message": "Command sent"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to send command"}, status_code=500)

@app.get("/client/{client_id}/latest_frame")
async def get_latest_frame(client_id: str):
    if client_id not in latest_frames:
        return JSONResponse({"error": "No frames available for this client"}, status_code=404)
    
    try:
        frame_data = latest_frames[client_id]
        frame_bytes = bytes.fromhex(frame_data["frame_data"])
        
        # Return the JPEG frame directly
        return StreamingResponse(
            io.BytesIO(frame_bytes),
            media_type="image/jpeg"
        )
    except Exception as e:
        logger.error(f"Error retrieving frame for client {client_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/client/{client_id}/latest_detection")
async def get_latest_detection(client_id: str):
    if client_id not in latest_detections:
        return JSONResponse({"error": "No detections available for this client"}, status_code=404)
    
    return JSONResponse(latest_detections[client_id])

# WebSocket endpoint for client connections
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    
    try:
        while True:
            # Receive message from client
            message = await websocket.receive_json()
            message_type = message.get("type")
            
            if message_type == "camera_frame":
                # Store the latest frame
                latest_frames[client_id] = {
                    "frame_data": message.get("frame_data"),
                    "timestamp": message.get("timestamp", time.time())
                }
            
            elif message_type == "sensor_data":
                # Store sensor data in client status
                if client_id not in client_status:
                    client_status[client_id] = {}
                
                sensor_name = message.get("sensor")
                if sensor_name:
                    if "sensors" not in client_status[client_id]:
                        client_status[client_id]["sensors"] = {}
                    
                    client_status[client_id]["sensors"][sensor_name] = {
                        "value": message.get("value"),
                        "timestamp": message.get("timestamp", time.time())
                    }
            
            elif message_type == "status_response":
                # Update client status
                client_status[client_id] = {
                    "has_camera": message.get("has_camera", False),
                    "has_imu": message.get("has_imu", False),
                    "has_rgb": message.get("has_rgb", False),
                    "has_distance_sensor": message.get("has_distance_sensor", False),
                    "ip_address": message.get("ip_address"),
                    "last_update": time.time()
                }
                
                # Log client status
                logger.info(f"Updated status for client {client_id}: {client_status[client_id]}")
            
            elif message_type in ["action_response", "rgb_response", "speak_response"]:
                # Just log these responses
                success = message.get("success", False)
                msg = message.get("message", "No message")
                if success:
                    logger.info(f"Client {client_id} response: {msg}")
                else:
                    logger.warning(f"Client {client_id} error response: {msg}")
            
            else:
                logger.warning(f"Unknown message type from client {client_id}: {message_type}")
    
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket connection with client {client_id}: {e}")
    finally:
        manager.disconnect(client_id)

# Add a default fallback route that returns a 200 OK for any other path
@app.get("/{path:path}")
async def catch_all(path: str):
    logger.info(f"Received request to unmapped path: /{path}")
    return {"status": "ok", "message": f"Path /{path} does not exist, but server is running"}

# Startup event to initialize background tasks
@app.on_event("startup")
async def startup_event():
    logger.info("Server startup event triggered")
    
    # Create directories if they don't exist
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # Load model in background
    threading.Thread(target=load_model, daemon=True).start()
    
    # Start background detection task
    try:
        asyncio.create_task(run_detection_on_client_frames())
        logger.info("Background detection task started")
    except Exception as e:
        logger.error(f"Failed to start background detection task: {e}")
    
    logger.info("PiDog Cloud Server started successfully")

# Après les autres endpoints, ajoutons les nouveaux endpoints pour la webcam

@app.get("/webcam-test", response_class=HTMLResponse)
async def webcam_test(request: Request):
    """
    Page de test pour la détection via webcam locale
    """
    try:
        return templates.TemplateResponse("webcam_test.html", {"request": request})
    except Exception as e:
        logger.error(f"Error rendering webcam test page: {e}")
        return HTMLResponse(content=f"<html><body><h1>Error</h1><p>{str(e)}</p></body></html>")

@app.post("/detect-webcam")
async def detect_webcam(image: UploadFile = File(...)):
    """
    Endpoint pour recevoir une image de webcam et renvoyer les détections
    """
    try:
        # Lire le contenu de l'image
        contents = await image.read()
        
        # Convertir en tableau numpy
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return JSONResponse({"success": False, "error": "Image invalide"})
        
        # Effectuer la détection
        start_time = time.time()
        results = detect_persons(img)
        
        # Renvoyer les résultats
        return JSONResponse(results)
        
    except Exception as e:
        logger.error(f"Error in webcam detection: {e}")
        return JSONResponse({"success": False, "error": str(e)})

# Main entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PiDog Cloud Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port to bind the server to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    
    args = parser.parse_args()
    
    logger.info(f"Starting server on {args.host}:{args.port}")
    
    uvicorn.run(
        "cloud_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    ) 