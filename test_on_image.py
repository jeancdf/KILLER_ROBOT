#!/usr/bin/env python3
# Test human detection on a single image

import cv2
import argparse
from ultralytics import YOLO
import time
import os

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test human detection on a static image')
    parser.add_argument('--image', type=str, default=None, help='Path to the image file')
    parser.add_argument('--conf', type=float, default=0.25, help='Confidence threshold')
    args = parser.parse_args()
    
    # Check if image path is provided
    if args.image is None or not os.path.exists(args.image):
        print("Please provide a valid image path using --image argument")
        print("Example: python test_on_image.py --image test.jpg")
        return
    
    # Load the YOLOv8n model
    print(f"Loading YOLOv8n model...")
    model = YOLO("yolov8n.pt")
    
    # Class ID for 'person' in COCO dataset
    person_class_id = 0
    
    # Load the image
    print(f"Loading image: {args.image}")
    image = cv2.imread(args.image)
    
    if image is None:
        print(f"Error: Unable to load image {args.image}")
        return
    
    # Get image dimensions
    height, width = image.shape[:2]
    print(f"Image dimensions: {width}x{height}")
    
    # Run YOLOv8 inference on the image
    start_time = time.time()
    results = model(image, conf=args.conf)
    processing_time = time.time() - start_time
    
    print(f"Detection completed in {processing_time:.2f} seconds")
    
    # Process results
    person_count = 0
    for result in results:
        boxes = result.boxes.cpu().numpy()
        
        # Draw bounding boxes for persons only
        for box in boxes:
            # Get class ID
            class_id = int(box.cls[0])
            
            # If the detected object is a person
            if class_id == person_class_id:
                person_count += 1
                
                # Get bounding box coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # Get confidence score
                confidence = float(box.conf[0])
                
                # Draw bounding box
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Add label with confidence score
                label = f"Person: {confidence:.2f}"
                cv2.putText(image, label, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    print(f"Detected {person_count} persons in the image")
    
    # Add processing info to the image
    cv2.putText(image, f"Processing time: {processing_time:.2f}s", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.putText(image, f"Persons detected: {person_count}", (10, 60), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    # Display the image with detections
    cv2.imshow('Human Detection Test', image)
    print("Press any key to close the window...")
    cv2.waitKey(0)
    
    # Save the output image
    output_path = f"output_{os.path.basename(args.image)}"
    cv2.imwrite(output_path, image)
    print(f"Result saved as {output_path}")
    
    # Close all windows
    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}") 