#!/bin/bash
# PiDog Client Startup Script with auto-restart
# Usage: ./start_pidog_client.sh [--no-camera] [--debug]

# Directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Log file for output
LOG_FILE="pidog_client.log"
ERROR_LOG="pidog_client_error.log"

# Maximum number of restart attempts
MAX_RESTARTS=5
RESTART_DELAY=5 # seconds

# Count restart attempts
restart_count=0

# Function to check if required packages are installed
check_requirements() {
    echo "Checking required packages..."
    python3 -c "import websocket" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "websocket-client not found. Installing..."
        pip3 install websocket-client
    fi
    
    python3 -c "import cv2" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "OpenCV not found. Installing..."
        pip3 install opencv-python
    fi
    
    python3 -c "import requests" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "Requests library not found. Installing..."
        pip3 install requests
    fi
}

# Check for arguments
CAMERA_FLAG=""
DEBUG_FLAG=""
SERVER_URL=""

for arg in "$@"
do
    if [ "$arg" == "--no-camera" ]; then
        CAMERA_FLAG="--no-camera"
        echo "Running without camera"
    fi
    
    if [ "$arg" == "--debug" ]; then
        DEBUG_FLAG="--debug"
        echo "Debug mode enabled"
    fi
    
    if [[ "$arg" == "--server="* ]]; then
        SERVER_URL="${arg}"
        echo "Using custom server URL: ${SERVER_URL}"
    fi
done

# Check requirements
check_requirements

# Test connection before starting
echo "Testing connection to server..."
python3 pidog_client.py --test-connection $SERVER_URL

# Start the client with auto-restart
while [ $restart_count -lt $MAX_RESTARTS ]; do
    echo "Starting PiDog client (attempt $((restart_count+1))/$MAX_RESTARTS)..."
    echo "Start time: $(date)" | tee -a "$LOG_FILE"
    
    # Run with arguments
    python3 pidog_client.py $CAMERA_FLAG $DEBUG_FLAG $SERVER_URL 2>&1 | tee -a "$LOG_FILE"
    exit_code=$?
    
    # Check if exit was clean or due to error
    if [ $exit_code -eq 0 ]; then
        echo "Client exited cleanly." | tee -a "$LOG_FILE"
        break
    else
        restart_count=$((restart_count+1))
        echo "Client crashed with exit code $exit_code. Restarting in $RESTART_DELAY seconds... ($restart_count/$MAX_RESTARTS)" | tee -a "$ERROR_LOG"
        sleep $RESTART_DELAY
    fi
done

if [ $restart_count -eq $MAX_RESTARTS ]; then
    echo "Maximum restart attempts reached. Please check the logs." | tee -a "$ERROR_LOG"
    exit 1
fi

exit 0 