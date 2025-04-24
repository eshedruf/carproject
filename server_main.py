import cv2
import numpy as np
import time
import socket
import struct
import json
from picamera2 import Picamera2
from car import MotorController


class PiServer:
    """
    This class handles the server side of the connection.
    It listens for a client (remote processor), sends camera frames,
    and receives JSON responses with PWM values.
    """
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.conn = None

    def start(self):
        """Bind, listen, and accept a single client connection."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(1)
        print(f"Listening for remote processor on {self.host}:{self.port}...")
        self.conn, addr = self.sock.accept()
        print(f"Accepted connection from {addr}")

    def send_frame(self, frame):
        """
        Sends the frame with header and raw data over the accepted connection,
        then waits for and returns the JSON response.
        """
        # Header with shape and dtype
        header = {"shape": frame.shape, "dtype": str(frame.dtype)}
        header_bytes = json.dumps(header).encode('utf-8')

        # Send header length + header
        self.conn.sendall(struct.pack('!I', len(header_bytes)))
        self.conn.sendall(header_bytes)

        # Send raw image data length + data
        raw = frame.tobytes()
        self.conn.sendall(struct.pack('!I', len(raw)))
        self.conn.sendall(raw)

        # Receive JSON response (terminated by newline)
        data = b''
        while not data.endswith(b"\n"):
            chunk = self.conn.recv(1024)
            if not chunk:
                raise ConnectionError("Connection lost while waiting for response")
            data += chunk

        resp_str = data.decode('utf-8').strip()
        return json.loads(resp_str)

    def close(self):
        if self.conn:
            self.conn.close()
        if self.sock:
            self.sock.close()


class CarController:
    """
    Initializes the motor controller and camera,
    captures frames, and applies commands.
    """
    def __init__(self):
        self.motor = MotorController()
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 380)})
        self.picam2.configure(config)
        self.picam2.start()
        time.sleep(2)

    def capture_frame(self):
        frame = self.picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        return frame

    def process_pwm_response(self, pwm):
        left_duty = pwm.get('left_duty', 0.07)
        right_duty = pwm.get('right_duty', 0.07)
        left_freq = pwm.get('left_freq', 50)
        right_freq = pwm.get('right_freq', 50)

        if left_duty == 0.0 and right_duty == 0.0:
            self.motor.stop()
            print("Motor stopped (duty=0)")
        else:
            self.motor.move_forward(
                left_duty=left_duty, right_duty=right_duty,
                left_freq=left_freq, right_freq=right_freq
            )
            print(f"PWM -> Ld: {left_duty:.3f}, Rd: {right_duty:.3f}, "
                  f"Lf: {left_freq}, Rf: {right_freq}")

    def cleanup(self):
        self.motor.stop()
        self.motor.cleanup()
        self.picam2.stop()
        self.picam2.close()


class CarRemoteServerApp:
    """
    Main app: starts the PiServer, then captures frames,
    sends them to the remote processor, and drives the car.
    """
    def __init__(self, host, port, frame_rate=20.0):
        self.frame_period = 1.0 / frame_rate
        self.server = PiServer(host, port)
        self.car = CarController()
        self.running = False

    def run(self):
        self.server.start()
        self.running = True
        try:
            while self.running:
                t0 = time.time()
                frame = self.car.capture_frame()
                pwm = self.server.send_frame(frame)
                self.car.process_pwm_response(pwm)
                elapsed = time.time() - t0
                if elapsed < self.frame_period:
                    time.sleep(self.frame_period - elapsed)
        except KeyboardInterrupt:
            print("Stopping by user interrupt.")
        finally:
            self.cleanup()

    def cleanup(self):
        self.car.cleanup()
        self.server.close()


if __name__ == '__main__':
    HOST = '0.0.0.0'
    PORT = 8000
    app = CarRemoteServerApp(HOST, PORT, frame_rate=20.0)
    app.run()
