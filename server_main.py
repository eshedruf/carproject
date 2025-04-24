import cv2
import numpy as np
import time
import socket
import struct
import json
from picamera2 import Picamera2
from car import MotorController

# --- ADDED FOR ENCRYPTION ---
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto import Random
# ----------------------------

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

        # Encryption placeholders
        self.rsa_cipher = None
        self.aes_key = None

    def start(self):
        """Bind, listen, accept client, and perform RSA/AES handshake."""
        # --- ORIGINAL BIND/LISTEN ---
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(1)
        print(f"Listening for remote processor on {self.host}:{self.port}...")
        self.conn, addr = self.sock.accept()
        print(f"Accepted connection from {addr}")

        # --- ENCRYPTION HANDSHAKE ---
        # Generate RSA key pair
        rsa_key = RSA.generate(2048)
        priv_key = rsa_key
        pub_key = rsa_key.publickey().export_key()
        # Send server's public key
        self.conn.sendall(struct.pack('!I', len(pub_key)))
        self.conn.sendall(pub_key)
        # Prepare to decrypt AES key
        self.rsa_cipher = PKCS1_OAEP.new(priv_key)
        # Receive encrypted AES key
        enc_key_len = struct.unpack('!I', self.conn.recv(4))[0]
        enc_key = self._recvall(enc_key_len)
        self.aes_key = self.rsa_cipher.decrypt(enc_key)
        print("Encryption handshake complete.")

    def _recvall(self, count):
        buf = b""
        while count:
            new = self.conn.recv(count)
            if not new:
                return None
            buf += new
            count -= len(new)
        return buf

    def _send_encrypted(self, data: bytes):
        cipher = AES.new(self.aes_key, AES.MODE_EAX)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        # send nonce, tag, ciphertext lengths and data
        self.conn.sendall(struct.pack('!I', len(cipher.nonce)))
        self.conn.sendall(cipher.nonce)
        self.conn.sendall(struct.pack('!I', len(tag)))
        self.conn.sendall(tag)
        self.conn.sendall(struct.pack('!I', len(ciphertext)))
        self.conn.sendall(ciphertext)

    def _recv_encrypted(self) -> bytes:
        nonce_len = struct.unpack('!I', self._recvall(4))[0]
        nonce = self._recvall(nonce_len)
        tag_len = struct.unpack('!I', self._recvall(4))[0]
        tag = self._recvall(tag_len)
        ct_len = struct.unpack('!I', self._recvall(4))[0]
        ciphertext = self._recvall(ct_len)
        cipher = AES.new(self.aes_key, AES.MODE_EAX, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def send_frame(self, frame):
        """
        Sends the frame encrypted with AES, then receives the encrypted JSON response.
        """
        # Header with shape and dtype
        header = {"shape": frame.shape, "dtype": str(frame.dtype)}
        header_bytes = json.dumps(header).encode('utf-8')

        # Raw frame data
        raw = frame.tobytes()

        # Prepare payload: header length + header + raw data
        payload = struct.pack('!I', len(header_bytes)) + header_bytes + raw

        # Send encrypted payload
        self._send_encrypted(payload)

        # Receive encrypted response and decrypt
        resp_data = self._recv_encrypted()
        resp_str = resp_data.decode('utf-8').strip()
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