import cv2
import numpy as np
import time
import socket
import struct
import json
from picamera2 import Picamera2
from car import MotorController

# --- Configuration ---
SERVER_IP = "192.168.0.134"  # Replace with your remote processor's IP address
SERVER_PORT = 8000           # Must match the remote processor port

# Initialize Motor Controller and Picamera2
motor = MotorController()
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 380)})
picam2.configure(config)
picam2.start()
time.sleep(2)  # Warm up the camera

# Connect to the remote processor
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((SERVER_IP, SERVER_PORT))
print(f"Connected to remote processor at {SERVER_IP}:{SERVER_PORT}")

# Set desired frame rate
frame_rate = 20.0
frame_period = 1.0 / frame_rate

try:
    while True:
        start_time = time.time()
        
        # Capture frame from the camera
        frame = picam2.capture_array()
        # Convert from RGB (picamera2 default) to BGR for OpenCV
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # Rotate frame 180° if necessary
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        
        # Create header with the image shape and dtype for reconstruction
        header = {
            "shape": frame.shape,  # e.g. (380, 640, 3)
            "dtype": str(frame.dtype)  # e.g. "uint8"
        }
        header_bytes = json.dumps(header).encode("utf-8")
        # Send header length first (4 bytes, network byte order)
        sock.sendall(struct.pack("!I", len(header_bytes)))
        # Send header bytes
        sock.sendall(header_bytes)
        
        # Send the raw image data
        raw_data = frame.tobytes()
        # Send raw data length (4 bytes) followed by raw image data.
        sock.sendall(struct.pack("!I", len(raw_data)))
        sock.sendall(raw_data)
        
        # Wait for JSON response from the remote processor (terminated by newline)
        response_data = b""
        while not response_data.endswith(b"\n"):
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("Socket connection broken")
            response_data += chunk
        
        # Decode JSON response to extract PWM values
        response_str = response_data.decode("utf-8").strip()
        pwm_info = json.loads(response_str)
        left_duty = pwm_info.get("left_duty", 0.07)
        right_duty = pwm_info.get("right_duty", 0.07)
        left_freq = pwm_info.get("left_freq", 50)
        right_freq = pwm_info.get("right_freq", 50)
        
        # If both duty cycles are 0, call motor.stop(), otherwise apply move_forward
        if left_duty == 0.0 and right_duty == 0.0:
            motor.stop()
            print("Motor stopped (received duty cycle 0).")
        else:
            motor.move_forward(left_duty=left_duty, right_duty=right_duty,
                               left_freq=left_freq, right_freq=right_freq)
            print(f"Received PWM -> Left Duty: {left_duty:.3f}, Right Duty: {right_duty:.3f}, "
                  f"Left Freq: {left_freq}, Right Freq: {right_freq}")
        
        # Maintain constant frame rate
        elapsed = time.time() - start_time
        if elapsed < frame_period:
            time.sleep(frame_period - elapsed)

except KeyboardInterrupt:
    print("Interrupted by user.")

finally:
    motor.stop()
    motor.cleanup()
    picam2.stop()
    picam2.close()
    sock.close()
