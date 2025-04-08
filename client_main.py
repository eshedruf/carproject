import cv2
import numpy as np
import time
import socket
import struct
import json
from picamera2 import Picamera2
from car import MotorController


class PiClient:
    """
    This class handles the connection to the remote processor.
    It is responsible for sending the camera frame (along with a header)
    and receiving the JSON response with PWM values.
    """
    def __init__(self, server_ip, server_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None

    def connect(self):
        """Establishes the TCP connection."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.server_ip, self.server_port))
        print(f"Connected to remote processor at {self.server_ip}:{self.server_port}")

    def send_frame(self, frame):
        """
        Sends the frame with its header and raw data.
        Returns the JSON response received from the processor.
        """
        # Build header information
        header = {
            "shape": frame.shape,  # e.g. (380, 640, 3)
            "dtype": str(frame.dtype)  # e.g. "uint8"
        }
        header_bytes = json.dumps(header).encode("utf-8")
        
        # Send header length first (4 bytes, network byte order)
        self.sock.sendall(struct.pack("!I", len(header_bytes)))
        # Send header bytes
        self.sock.sendall(header_bytes)
        
        # Convert frame to raw bytes and send its length then data
        raw_data = frame.tobytes()
        self.sock.sendall(struct.pack("!I", len(raw_data)))
        self.sock.sendall(raw_data)
        
        # Receive the response terminated by a newline character
        response_data = b""
        while not response_data.endswith(b"\n"):
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("Socket connection broken")
            response_data += chunk

        # Decode and return the response as a dictionary
        response_str = response_data.decode("utf-8").strip()
        return json.loads(response_str)

    def close(self):
        """Closes the socket connection."""
        if self.sock:
            self.sock.close()


class CarController:
    """
    This class encapsulates the car's functionalities:
    it initializes the motor controller and camera,
    captures images, and applies commands based on remote processor instructions.
    """
    def __init__(self):
        # Initialize motor controller
        self.motor = MotorController()

        # Initialize camera
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 380)})
        self.picam2.configure(config)
        self.picam2.start()
        time.sleep(2)  # Allow camera to warm-up

    def capture_frame(self):
        """
        Captures an image from the camera, converts it from RGB to BGR,
        and rotates it 180° if necessary.
        """
        frame = self.picam2.capture_array()
        # Convert from RGB to BGR for OpenCV processing
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # Rotate the frame if required
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        return frame

    def process_pwm_response(self, pwm_info):
        """
        Processes PWM values received from the remote processor.
        If both duty cycles are zero, stops the motor; otherwise, moves forward.
        """
        left_duty = pwm_info.get("left_duty", 0.07)
        right_duty = pwm_info.get("right_duty", 0.07)
        left_freq = pwm_info.get("left_freq", 50)
        right_freq = pwm_info.get("right_freq", 50)

        if left_duty == 0.0 and right_duty == 0.0:
            self.motor.stop()
            print("Motor stopped (received duty cycle 0).")
        else:
            self.motor.move_forward(left_duty=left_duty, right_duty=right_duty,
                                    left_freq=left_freq, right_freq=right_freq)
            print(f"Received PWM -> Left Duty: {left_duty:.3f}, Right Duty: {right_duty:.3f}, "
                  f"Left Freq: {left_freq}, Right Freq: {right_freq}")

    def cleanup(self):
        """Stops the motor and releases camera resources."""
        self.motor.stop()
        self.motor.cleanup()
        self.picam2.stop()
        self.picam2.close()


class CarRemoteControllerApp:
    """
    This is the main application class which ties together the remote processor client and the car controller.
    It runs a loop to capture frames, send them to the remote processor, process the commands, and maintain the frame rate.
    """
    def __init__(self, server_ip, server_port, frame_rate=20.0):
        self.frame_rate = frame_rate
        self.frame_period = 1.0 / frame_rate
        self.client = PiClient(server_ip, server_port)
        self.car = CarController()
        self.running = False

    def run(self):
        """Starts the main loop, capturing frames, processing responses, and controlling the car."""
        self.client.connect()
        self.running = True

        try:
            while self.running:
                start_time = time.time()
                
                # Capture and process frame
                frame = self.car.capture_frame()
                # Send frame to remote processor and get response
                pwm_info = self.client.send_frame(frame)
                # Process the received PWM information
                self.car.process_pwm_response(pwm_info)
                
                # Maintain constant frame rate
                elapsed = time.time() - start_time
                if elapsed < self.frame_period:
                    time.sleep(self.frame_period - elapsed)
        except KeyboardInterrupt:
            print("Interrupted by user.")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources before exiting."""
        self.car.cleanup()
        self.client.close()


if __name__ == '__main__':
    # --- Configuration ---
    SERVER_IP = "192.168.0.134"  # Replace with your remote processor's IP address
    SERVER_PORT = 8000           # Must match the remote processor port

    app = CarRemoteControllerApp(SERVER_IP, SERVER_PORT, frame_rate=20.0)
    app.run()
