import socket
import threading
import time
import cv2
import numpy as np
from picamera2 import Picamera2
from car import MotorController
from sqldb import UserDB
from protocol import Protocol, ConnectionClosedError

MAX_CLIENTS = 3
FRAME_RATE = 20.0

ADMIN_USER = 'admin'
ADMIN_PASS = 'admin'

class CarController:
    def __init__(self):
        self.motor = MotorController()
        self.picam2 = Picamera2()
        cfg = self.picam2.create_preview_configuration(main={"size": (640, 380)})
        self.picam2.configure(cfg)
        self.picam2.start()
        time.sleep(2)

    def capture_frame(self):
        frame = self.picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return cv2.rotate(frame, cv2.ROTATE_180)

    def process_pwm(self, pwm):
        if pwm.get("type") == Protocol.CMDS['STOP']:
            self.motor.stop()
            print("[ADMIN] STOP command processed")
            return
        left = pwm.get('left_duty', 0.0)
        right = pwm.get('right_duty', 0.0)
        lf = pwm.get('left_freq', 50)
        rf = pwm.get('right_freq', 50)
        if left == 0.0 and right == 0.0:
            self.motor.stop()
            print("[ADMIN] Motors stopped")
        else:
            self.motor.move_forward(left_duty=left, right_duty=right, left_freq=lf, right_freq=rf)
            print(f"[ADMIN] Motors -> Ld:{left:.3f}, Rd:{right:.3f}")

    def cleanup(self):
        self.motor.stop()
        self.motor.cleanup()
        self.picam2.stop()
        self.picam2.close()

class CarRemoteServerApp:
    def __init__(self, host, port):
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_sock.bind((host, port))
        self.listen_sock.listen(MAX_CLIENTS)
        print(f"Listening on {host}:{port} (admin + {MAX_CLIENTS-1} spectators)")

        self.car = CarController()
        self.frame_period = 1.0 / FRAME_RATE
        self.lock = threading.Lock()
        self.active = 0
        self.admin_present = False

    def run(self):
        try:
            while True:
                conn, addr = self.listen_sock.accept()
                print(f"Incoming connection from {addr}")
                with self.lock:
                    if self.active >= MAX_CLIENTS:
                        print("Server full, closing connection silently")
                        conn.close()
                        continue
                    self.active += 1
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("Shutting down server")
        finally:
            self.car.cleanup()
            self.listen_sock.close()

    def _handle_client(self, sock, addr):
        protocol = Protocol('server', None, None, listen_sock=self.listen_sock)
        protocol.conn = sock
        try:
            protocol._perform_encryption_handshake()
        except ConnectionClosedError:
            self._cleanup(is_admin=False)
            return

        db = UserDB()
        auth = False
        is_admin = False
        try:
            while not auth:
                req = protocol.recv_json()
                username = req.get('username')
                password = req.get('password')
                req_type = req.get('type')

                if req_type == Protocol.CMDS['SIGNUP']:
                    if username == ADMIN_USER:
                        protocol.send_json({"status": "error", "message": "Cannot signup as admin"})
                        raise ConnectionClosedError("Admin signup blocked")
                    ok = db.add_user(username, password, req['age'])
                    protocol.send_json({"status": "success"} if ok else {"status": "error", "message": "Username exists"})
                    auth = ok

                elif req_type == Protocol.CMDS['LOGIN']:
                    if username == ADMIN_USER:
                        if password == ADMIN_PASS:
                            with self.lock:
                                if not self.admin_present:
                                    self.admin_present = True
                                    is_admin = True
                                    protocol.send_json({"status": "success"})
                                    auth = True
                                else:
                                    protocol.send_json({"status": "error", "message": "Admin already connected"})
                                    raise ConnectionClosedError("Admin already present")
                        else:
                            protocol.send_json({"status": "error", "message": "Invalid admin credentials"})
                            raise ConnectionClosedError("Bad admin login")
                    else:
                        ok = db.verify_user(username, password)
                        protocol.send_json({"status": "success"} if ok else {"status": "error", "message": "Invalid credentials"})
                        auth = ok
                else:
                    protocol.send_json({"status": "error", "message": "Invalid request"})
        except Exception as e:
            print(f"Auth failed ({addr}): {e}")
            protocol.close()
            db.close()
            self._cleanup(is_admin)
            return
        finally:
            db.close()

        role = "ADMIN" if is_admin else "SPECTATOR"
        print(f"{role} {addr} authenticated")

        try:
            if is_admin:
                self._admin_loop(protocol)
            else:
                self._spectator_loop(protocol)
        finally:
            protocol.close()
            print(f"{role} {addr} disconnected")
            self._cleanup(is_admin)

    def _admin_loop(self, protocol):
        while True:
            t0 = time.time()
            frame = self.car.capture_frame()
            protocol.send_frame(frame)
            try:
                pwm = protocol.recv_json()
            except ConnectionClosedError:
                break
            self.car.process_pwm(pwm)
            dt = time.time() - t0
            if dt < self.frame_period:
                time.sleep(self.frame_period - dt)

    def _spectator_loop(self, protocol):
        """
        Spectator clients: ignore any incoming commands,
        then capture & send frames continuously until they disconnect.
        """
        sock = protocol.conn
        sock.settimeout(0.1)

        while True:
            # Drain and ignore any spectator commands
            try:
                while True:
                    cmd = protocol.recv_json()
                    print(f"[SPECTATOR] Ignored command: {cmd.get('type')}")
            except (socket.timeout, ConnectionClosedError):
                pass

            # Capture a camera frame and send it
            try:
                frame = self.car.capture_frame()
                protocol.send_frame(frame)
            except (ConnectionClosedError, TimeoutError):
                # Client has disconnected or timed out—exit cleanly
                break

            # Pace the loop to FRAME_RATE
            time.sleep(self.frame_period)


    def _cleanup(self, is_admin):
        with self.lock:
            self.active -= 1
            if is_admin:
                self.admin_present = False
                self.car.motor.stop()
                print("[SERVER] Admin disconnected—car stopped")

if __name__ == "__main__":
    app = CarRemoteServerApp('0.0.0.0', 8000)
    app.run()
