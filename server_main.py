import cv2
import numpy as np
import time
from picamera2 import Picamera2
from car import MotorController
from sqldb import UserDB
from protocol import Protocol, ConnectionClosedError
import socket

class CarController:
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
        if pwm.get("type") == Protocol.CMDS['STOP']:
            print("Received STOP command")
            return
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

    def stop_car(self):
        self.motor.stop()
        print("Car stopped due to client disconnection")

    def cleanup(self):
        self.motor.stop()
        self.motor.cleanup()
        self.picam2.stop()
        self.picam2.close()

class CarRemoteServerApp:
    def __init__(self, host, port, frame_rate=20.0):
        self.protocol = Protocol('server', host, port)
        self.car = CarController()
        self.frame_period = 1.0 / frame_rate
        self.running = False

    def run(self):
        while True:
            print("Waiting for a client connection...")
            try:
                self.protocol.accept()
                print("Client connected. Starting authentication...")

                # Authentication loop
                db = UserDB()
                authenticated = False
                while not authenticated:
                    try:
                        request = self.protocol.recv_json()
                        if request["type"] == Protocol.CMDS['SIGNUP']:
                            username = request["username"]
                            password = request["password"]
                            age = request["age"]
                            if db.add_user(username, password, age):
                                self.protocol.send_json({"status": "success"})
                                authenticated = True
                            else:
                                self.protocol.send_json({"status": "error", "message": "Username already exists"})
                        elif request["type"] == Protocol.CMDS['LOGIN']:
                            username = request["username"]
                            password = request["password"]
                            if db.verify_user(username, password):
                                self.protocol.send_json({"status": "success"})
                                authenticated = True
                            else:
                                self.protocol.send_json({"status": "error", "message": "Invalid credentials"})
                        else:
                            self.protocol.send_json({"status": "error", "message": "Invalid request type"})
                    except (ConnectionResetError, BrokenPipeError, socket.timeout, ConnectionClosedError) as e:
                        print(f"Authentication failed due to connection error: {e}")
                        break
                db.close()

                if authenticated:
                    print("Authentication successful. Starting main loop.")
                    self.running = True
                    try:
                        while self.running:
                            t0 = time.time()
                            frame = self.car.capture_frame()
                            self.protocol.send_frame(frame)
                            pwm = self.protocol.recv_json()
                            if pwm.get("type") == Protocol.CMDS['STOP']:
                                print("Received STOP command. Stopping.")
                                break
                            self.car.process_pwm_response(pwm)
                            elapsed = time.time() - t0
                            if elapsed < self.frame_period:
                                time.sleep(self.frame_period - elapsed)
                    except (ConnectionResetError, BrokenPipeError, socket.timeout, ConnectionClosedError) as e:
                        print(f"Client disconnected during main loop: {e}")
                        self.car.stop_car()
                        self.protocol.close()
                        self.running = False
                    except KeyboardInterrupt:
                        print("Stopping by user interrupt.")
                        self.running = False
                    finally:
                        self.car.stop_car()
                        self.protocol.close()
                else:
                    print("Authentication failed. Waiting for a new client...")
                    self.protocol.close()
            except Exception as e:
                print(f"Error accepting new connection: {e}")
                self.protocol.close()
                continue

if __name__ == '__main__':
    HOST = '0.0.0.0'
    PORT = 8000
    app = CarRemoteServerApp(HOST, PORT, frame_rate=20.0)
    app.run()