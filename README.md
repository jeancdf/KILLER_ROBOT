# KILLER_ROBOT - Human Silhouette Detection System

A system for detecting human silhouettes using a camera and a lightweight AI model.

## Overview

This project uses:
- OpenCV for camera capture
- YOLOv8n for human detection
- Python 3.7+ as the programming language

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Run the detection script:
```
python human_detection.py
```

## Features

- Real-time human detection from webcam feed
- Bounding box display around detected persons
- Filtering to show only human detections

## Future Development

- Transfer to Raspberry Pi
- Performance optimization for ARM CPU
- Person tracking
- Distance estimation
- Motor control for tracking 