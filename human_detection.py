#!/usr/bin/env python3
# Human Silhouette Detection using YOLOv8 and OpenCV

import cv2
import numpy as np
from ultralytics import YOLO
import time

def main():
    # Load the YOLOv8n model
    print("Loading YOLOv8n model...")
    model = YOLO("yolov8n.pt")  # This will download the model if not available
    
    # Class ID for 'person' in COCO dataset (used by YOLOv8)
    person_class_id = 0
    
    # Initialize webcam
    print("Initializing webcam...")
    cap = cv2.VideoCapture(0)
    
    # Check if webcam is opened correctly
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return
    
    # Set webcam properties (optional)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print("Starting detection. Press 'q' to quit.")
    
    # Main loop
    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()
        
        if not ret:
            print("Error: Failed to capture image")
            break
            
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
        
        # Calculate and display FPS
        fps = 1.0 / (time.time() - start_time)
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Display the frame with detections
        cv2.imshow('Human Detection', frame)
        
        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Release the webcam and close all windows
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