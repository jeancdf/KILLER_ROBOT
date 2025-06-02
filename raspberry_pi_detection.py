#!/usr/bin/env python3
# Human Silhouette Detection for Raspberry Pi
# This is a template for future development

import cv2
import numpy as np
from ultralytics import YOLO
import time
import os

def main():
    # Set environment variable to improve performance on Raspberry Pi
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"
    
    # Load the YOLOv8n model
    print("Loading YOLOv8n model...")
    # Note: For Raspberry Pi, consider using a smaller model like YOLOv8n-640
    model = YOLO("yolov8n.pt")
    
    # Optionally configure model for better performance on Raspberry Pi
    # model.conf = 0.5  # Higher confidence threshold
    # model.iou = 0.7   # Higher NMS IOU threshold
    
    # Class ID for 'person' in COCO dataset
    person_class_id = 0
    
    # Initialize camera
    # For Raspberry Pi Camera v2 (adjust as needed)
    print("Initializing Raspberry Pi camera...")
    
    # For CSI camera on Raspberry Pi
    # Try this first:
    cap = cv2.VideoCapture(0)
    
    # Alternative options for Pi Camera:
    # cap = cv2.VideoCapture("libcamerasrc ! video/x-raw, width=640, height=480 ! appsink", cv2.CAP_GSTREAMER)
    # Or:
    # from picamera2 import Picamera2
    # picam2 = Picamera2()
    # picam2.start()
    
    # Check if camera is opened correctly
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return
    
    # Set camera properties for better performance
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS for Raspberry Pi
    
    print("Starting detection. Press 'q' to quit.")
    
    # Main loop
    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()
        
        if not ret:
            print("Error: Failed to capture image")
            break
            
        # Optional: Resize frame for faster processing
        frame = cv2.resize(frame, (320, 240))
        
        # Measure processing time
        start_time = time.time()
        
        # Run YOLOv8 inference on the frame
        results = model(frame)
        
        # Process results
        for result in results:
            boxes = result.boxes.cpu().numpy()
            
            # Draw bounding boxes for persons only
            for box in boxes:
                # Get class ID
                class_id = int(box.cls[0])
                
                # If the detected object is a person
                if class_id == person_class_id:
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Get confidence score
                    confidence = float(box.conf[0])
                    
                    # Draw bounding box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # Add label with confidence score
                    label = f"Person: {confidence:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    
                    # Here you would add code for:
                    # 1. Tracking the closest person
                    # 2. Estimating distance
                    # 3. Controlling motors (future implementation)
        
        # Calculate and display FPS
        processing_time = time.time() - start_time
        fps = 1.0 / processing_time if processing_time > 0 else 0
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Display the frame with detections
        cv2.imshow('Human Detection (Raspberry Pi)', frame)
        
        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Release the camera and close all windows
    cap.release()
    cv2.destroyAllWindows()
    print("Detection stopped.")

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