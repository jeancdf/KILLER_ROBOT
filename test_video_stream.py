#!/usr/bin/env python3
# Test script to check if the video streaming from the cloud server is working

import requests
import cv2
import numpy as np
import time
import sys
import os
import argparse

def test_video_stream(client_id, server_url="https://killerrobot-production.up.railway.app"):
    """Test if video streaming is working for a specific client"""
    
    print(f"Testing video stream for client: {client_id}")
    print(f"Server URL: {server_url}")
    
    # First check if the client exists
    try:
        client_status_url = f"{server_url}/client/{client_id}/status"
        response = requests.get(client_status_url)
        
        if response.status_code != 200:
            print(f"Error: Client {client_id} not found or not connected")
            return False
            
        status = response.json()
        print(f"Client status: {status}")
        
        if not status.get('has_camera', False):
            print("Warning: Client reports no camera available")
    except Exception as e:
        print(f"Error checking client status: {e}")
        return False
    
    # Try to get a frame
    try:
        frame_url = f"{server_url}/client/{client_id}/latest_frame?t={int(time.time())}"
        print(f"Getting frame from: {frame_url}")
        
        response = requests.get(frame_url, stream=True)
        
        if response.status_code != 200:
            print(f"Error: Failed to get frame, status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
        # Check content type
        content_type = response.headers.get('content-type', '')
        print(f"Content type: {content_type}")
        
        if 'image' not in content_type:
            print(f"Warning: Response is not an image ({content_type})")
        
        # Save the frame to a file for inspection
        output_file = f"{client_id}_frame.jpg"
        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        
        print(f"Frame saved to: {output_file}")
        
        # Try to decode the image with OpenCV
        try:
            frame_data = np.frombuffer(response.content, dtype=np.uint8)
            frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
            
            if frame is None:
                print("Error: Could not decode image data")
                return False
                
            print(f"Successfully decoded frame with shape: {frame.shape}")
            
            # Display the image if possible
            if os.name != 'nt' or 'DISPLAY' in os.environ:
                cv2.imshow("Frame", frame)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                
            return True
        except Exception as e:
            print(f"Error decoding image: {e}")
            return False
            
    except Exception as e:
        print(f"Error getting frame: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test video streaming from the cloud server")
    parser.add_argument("client_id", help="Client ID to test")
    parser.add_argument("--server", default="https://killerrobot-production.up.railway.app", 
                        help="Server URL (default: https://killerrobot-production.up.railway.app)")
    
    args = parser.parse_args()
    
    if test_video_stream(args.client_id, args.server):
        print("Video streaming test PASSED!")
        sys.exit(0)
    else:
        print("Video streaming test FAILED!")
        sys.exit(1) 