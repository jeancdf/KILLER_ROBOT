#!/usr/bin/env python3
# Utility functions for human detection and tracking

import numpy as np
import cv2

def estimate_distance(bbox_height, real_height=1.7, focal_length=None, sensor_height=None):
    """
    Estimate distance to a person based on their bounding box height.
    
    This uses a simple pinhole camera model. For accurate results,
    camera calibration should be performed.
    
    Args:
        bbox_height (float): Height of the bounding box in pixels
        real_height (float): Average human height in meters (default: 1.7m)
        focal_length (float, optional): Camera focal length in pixels
        sensor_height (float, optional): Camera sensor height in pixels
        
    Returns:
        float: Estimated distance in meters
    """
    # If focal length is not provided, use a reasonable default
    if focal_length is None or sensor_height is None:
        # This is a very rough approximation
        # For better results, perform camera calibration
        return (real_height * 1000) / bbox_height
    
    # More accurate calculation using camera parameters
    distance = (real_height * focal_length) / (bbox_height * sensor_height)
    return distance

def find_closest_person(boxes, confidences):
    """
    Find the person with the largest bounding box (likely closest).
    
    Args:
        boxes (list): List of bounding boxes [x1, y1, x2, y2]
        confidences (list): Corresponding confidence scores
        
    Returns:
        tuple: (box_index, box, confidence) of closest person, or None if no person found
    """
    if not boxes:
        return None
    
    # Calculate areas of all boxes
    areas = [(box[2] - box[0]) * (box[3] - box[1]) for box in boxes]
    
    # Find the box with maximum area
    max_area_idx = np.argmax(areas)
    
    return max_area_idx, boxes[max_area_idx], confidences[max_area_idx]

def track_person(frame, previous_box, max_search_expansion=20):
    """
    Simple tracking based on overlap with previous detection.
    
    Note: This is a placeholder for a more sophisticated tracking algorithm.
    For better results, consider using dedicated trackers like CSRT, KCF, etc.
    
    Args:
        frame (numpy.ndarray): Current video frame
        previous_box (list): Previous [x1, y1, x2, y2] coordinates
        max_search_expansion (int): Expansion factor for search area
        
    Returns:
        list: Updated [x1, y1, x2, y2] coordinates
    """
    if previous_box is None:
        return None
    
    x1, y1, x2, y2 = previous_box
    
    # Expand search area
    x1_expanded = max(0, x1 - max_search_expansion)
    y1_expanded = max(0, y1 - max_search_expansion)
    x2_expanded = min(frame.shape[1], x2 + max_search_expansion)
    y2_expanded = min(frame.shape[0], y2 + max_search_expansion)
    
    # For a real implementation, use OpenCV's trackers:
    # Example:
    # tracker = cv2.TrackerCSRT_create()
    # tracker.init(frame, (x1, y1, x2-x1, y2-y1))
    # success, box = tracker.update(next_frame)
    
    # This is a placeholder - in a real implementation, 
    # you would perform actual tracking here
    return [x1, y1, x2, y2]  # Return previous box as fallback

def draw_distance_indicator(frame, bbox, distance):
    """
    Draw distance indicator on the frame.
    
    Args:
        frame (numpy.ndarray): Video frame to draw on
        bbox (list): Bounding box [x1, y1, x2, y2]
        distance (float): Estimated distance in meters
        
    Returns:
        numpy.ndarray: Frame with distance indicator
    """
    x1, y1, x2, y2 = bbox
    
    # Draw distance text at the bottom of the bounding box
    cv2.putText(
        frame, 
        f"Distance: {distance:.2f}m", 
        (x1, y2 + 20), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        0.5, 
        (255, 0, 0), 
        2
    )
    
    # Optional: Draw a circle whose size is inversely proportional to distance
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    
    # Radius inversely proportional to distance (adjust as needed)
    radius = int(50 / distance) if distance > 0 else 50
    radius = min(radius, 50)  # Cap the maximum radius
    
    cv2.circle(frame, (center_x, center_y), radius, (0, 0, 255), 2)
    
    return frame 