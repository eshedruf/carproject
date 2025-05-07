import socket
import threading
import time
import cv2
import numpy as np
from picamera2 import Picamera2
from car import MotorController
from sqldb import UserDB
from protocol import Protocol, ConnectionClosedError

MAX_CLIENTS   = 3
FRAME_RATE    = 20.0
ADMIN_USER    = 'admin'
ADMIN_PASS    = 'admin'

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
        t = pwm.get("type")
        if t == Protocol.CMDS['STOP']:
            self.motor.stop()
            print("[ADMIN] STOP")
            return

        left  = pwm.get('left_duty',  0.0)
        right = pwm.get('right_duty', 0.0)
        lf    = pwm.get('left_freq', 50)
        rf    = pwm.get('right_freq',50)

        if left == 0.0 and right == 0.0:
            self.motor.stop()
            print("[ADMIN] Motors stopped")
        else:
            self.motor.move_forward(
                left_duty=left, right_duty=right,
                left_freq=lf, right_freq=rf
            )
            print(f"[ADMIN] Ld:{left:.3f} Rd:{right:.3f}")

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
        print(f"Listening on {host}:{port} (1 admin + {MAX_CLIENTS-1} spectators)")

        self.car            = CarController()
        self.frame_period   = 1.0 / FRAME_RATE
        self.lock           = threading.Lock()
        self.clients        = []         # list of Protocol objects
        self.admin_protocol = None       # the one admin socket
        self.running        = True

    def run(self):
        # Start broadcasting frames to all clients
        threading.Thread(target=self._broadcast_frames, daemon=True).start()

        try:
            while self.running:
                conn, addr = self.listen_sock.accept()
                print(f"Incoming connection from {addr}")
                threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                ).start()
        except KeyboardInterrupt:
            print("Shutting down server")
        finally:
            self.running = False
            self.car.cleanup()
            self.listen_sock.close()

    def _handle_client(self, sock, addr):
        protocol = Protocol('server', None, None, listen_sock=self.listen_sock)
        protocol.conn = sock

        # Encryption handshake
        try:
            protocol._perform_encryption_handshake()
        except ConnectionClosedError:
            return

        db = UserDB()
        try:
            # --- AUTH ---
            auth = False
            is_admin = False
            while not auth:
                req = protocol.recv_json()
                u, p, t = req.get('username'), req.get('password'), req.get('type')

                if t == Protocol.CMDS['SIGNUP']:
                    if u == ADMIN_USER:
                        protocol.send_json({"status":"error","message":"Cannot signup as admin"})
                        raise ConnectionClosedError()
                    ok = db.add_user(u, p, req.get('age'))
                    protocol.send_json({"status":"success"} if ok else {"status":"error","message":"Username exists"})
                    auth = ok

                elif t == Protocol.CMDS['LOGIN']:
                    if u == ADMIN_USER:
                        # Admin login
                        if p == ADMIN_PASS:
                            with self.lock:
                                if self.admin_protocol is None:
                                    self.admin_protocol = protocol
                                    is_admin = True
                                    auth = True
                                    protocol.send_json({"status":"success"})
                                else:
                                    protocol.send_json({"status":"error","message":"Admin already connected"})
                                    raise ConnectionClosedError()
                        else:
                            protocol.send_json({"status":"error","message":"Invalid admin credentials"})
                            raise ConnectionClosedError()
                    else:
                        # Spectator login
                        ok = db.verify_user(u, p)
                        protocol.send_json({"status":"success"} if ok else {"status":"error","message":"Invalid credentials"})
                        auth = ok
                else:
                    protocol.send_json({"status":"error","message":"Invalid request"})
        except ConnectionClosedError:
            print(f"Auth failed for {addr}")
            protocol.close()
            return
        finally:
            db.close()

        role = "ADMIN" if is_admin else "SPECTATOR"
        print(f"{role} {addr} authenticated")

        # Add to broadcast list
        with self.lock:
            self.clients.append(protocol)

        if is_admin:
            # Only admin socket reads commands
            try:
                while self.running:
                    cmd = protocol.recv_json()    # blocks until admin sends
                    self.car.process_pwm(cmd)
            except ConnectionClosedError:
                pass
            finally:
                print("Admin disconnected, stopping car")
                self.car.motor.stop()
        else:
            # Spectator: just stay alive until disconnect
            try:
                while self.running:
                    time.sleep(1)
            except:
                pass

        # Cleanup on disconnect
        protocol.close()
        with self.lock:
            if protocol in self.clients:
                self.clients.remove(protocol)
            if protocol is self.admin_protocol:
                self.admin_protocol = None
        print(f"{role} {addr} disconnected")

    def _broadcast_frames(self):
        """Continuously capture & send frames to every client."""
        while self.running:
            t0 = time.time()
            frame = self.car.capture_frame()

            with self.lock:
                targets = list(self.clients)

            for prot in targets:
                try:
                    prot.send_frame(frame)
                except Exception:
                    with self.lock:
                        if prot in self.clients:
                            self.clients.remove(prot)

            dt = time.time() - t0
            if dt < self.frame_period:
                time.sleep(self.frame_period - dt)

if __name__ == "__main__":
    app = CarRemoteServerApp('0.0.0.0', 8000)
    app.run()
