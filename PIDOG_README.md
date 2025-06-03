# PiDog Person Tracker

A script that makes your PiDog robot detect, track, and follow people, making sounds when they get too close. Now with remote camera monitoring and control!

## Overview

This project combines:
- Human detection using YOLOv8n
- PiDog's movement capabilities 
- Ultrasonic distance sensing
- Camera tracking
- Sound effects
- Web-based remote monitoring and control

## Features

- Detects humans using computer vision
- Tracks people with the PiDog's camera/head
- Follows people when they're in range
- Backs away if someone gets too close
- Barks and changes LED colors when people are detected
- Looks around when no one is detected
- **NEW**: Remote camera monitoring through web interface
- **NEW**: Remote control of PiDog from any device with a web browser

## Setup Instructions

### Prerequisites

- SunFounder PiDog robot fully assembled
- Raspberry Pi (3B+, 4, or similar) with Raspberry Pi OS installed
- Camera and ultrasonic sensor properly connected
- Internet connection for downloading YOLO model
- For remote monitoring: Both devices on the same network

### Installation

1. Install required Python libraries:

```bash
# Install OpenCV and other dependencies
sudo apt update
sudo apt install -y python3-opencv python3-pip python3-setuptools python3-smbus

# Install Robot HAT library (if not already installed)
cd ~/
git clone -b v2.0 https://github.com/sunfounder/robot-hat.git
cd robot-hat
sudo python3 setup.py install

# Install vilib for camera (if not already installed)
cd ~/
git clone -b picamera2 https://github.com/sunfounder/vilib.git
cd vilib
sudo python3 install.py

# Install PiDog library
cd ~/
git clone https://github.com/sunfounder/pidog.git
cd pidog
sudo python3 setup.py install

# Install Flask for web interface
pip3 install flask

# Install PyTorch and ultralytics
pip3 install torch torchvision torchaudio
pip3 install ultralytics
```

2. Transfer the `pidog_person_tracker.py` script to your Raspberry Pi.

3. Make the script executable:

```bash
chmod +x pidog_person_tracker.py
```

## Running the Script

### Basic Usage (No Remote Access)

1. Place your PiDog on the ground in a safe, open area.

2. Run the script:

```bash
python3 pidog_person_tracker.py
```

### With Remote Access Enabled

1. Place your PiDog on the ground in a safe, open area.

2. Run the script with the web interface enabled:

```bash
python3 pidog_person_tracker.py --web
```

3. You can also specify a custom port (default is 8000):

```bash
python3 pidog_person_tracker.py --web --port 8080
```

4. For headless operation (no local display window):

```bash
python3 pidog_person_tracker.py --web --headless
```

5. The script will output a URL you can access from any device on the same network, for example:
   ```
   Starting web server on http://192.168.1.100:8000
   ```

6. Open that URL in a web browser on any device (computer, tablet, smartphone) to:
   - View the live camera feed
   - See the current distance reading
   - Toggle between auto and manual modes
   - Control the PiDog manually

## Web Interface Features

The web interface provides:

1. **Live Camera Feed**: See what PiDog sees, including person detection boxes
2. **Distance Reading**: Current ultrasonic sensor reading
3. **Mode Control**: Switch between automatic (follows people) and manual (you control) modes
4. **Manual Controls**:
   - Movement: Forward, Backward, Turn Left, Turn Right
   - Posture: Stand, Sit
   - Actions: Bark, Wag Tail

## Customization

You can adjust the following parameters at the top of the script:

- `CLOSE_DISTANCE`: How close (in cm) before the dog barks (default: 30cm)
- `FOLLOW_DISTANCE`: Distance at which the dog will follow a person (default: 200cm)
- `SAFE_DISTANCE`: Maximum tracking distance (default: 400cm)
- `FPS_TARGET`: Target frame rate (lower for better CPU performance)
- `DETECTION_INTERVAL`: Time between running detection
- `MOVEMENT_INTERVAL`: Time between movement commands

## Troubleshooting

- **Robot falls over**: Reduce movement speed or step count in the script
- **Camera not working**: Check camera connection and permissions
- **Detection not working**: Ensure good lighting conditions
- **Movement problems**: Check servo connections and calibration
- **Web interface not accessible**: Make sure both devices are on the same network
- **Video stream slow**: Reduce resolution or FPS in the code

## Advanced Modifications

Consider enhancing the script with:

- Person recognition to only follow specific people
- Additional sounds and behaviors
- Gesture recognition to respond to hand signals
- Obstacle avoidance during movement
- Custom web interface with additional controls

## Safety Note

Always supervise the PiDog when running this script. The robot may move unexpectedly and should be used in a safe environment. 