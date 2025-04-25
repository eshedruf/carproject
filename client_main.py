import socket
import struct
import json
import threading
import time
import numpy as np, cv2
from image_utils import ImgUtils
from pid_controller import PID
from gui import GUI
from auth_window import AuthWindow
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto import Random

class Client(threading.Thread):
    def __init__(self, gui, server_ip, server_port):
        super().__init__(daemon=True)
        self.gui = gui
        self.pid = PID()
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.aes_key = None

    def connect(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.server_ip, self.server_port))
                print(f"Connected to remote processor at {self.server_ip}:{self.server_port}")
                pubkey_len = struct.unpack('!I', self._recvall(4))[0]
                pubkey = self._recvall(pubkey_len)
                rsa_pub = RSA.import_key(pubkey)
                rsa_cipher = PKCS1_OAEP.new(rsa_pub)
                self.aes_key = Random.get_random_bytes(16)
                enc_key = rsa_cipher.encrypt(self.aes_key)
                self.sock.sendall(struct.pack('!I', len(enc_key)))
                self.sock.sendall(enc_key)
                print("Encryption handshake with server complete.")
                break
            except (ConnectionRefusedError, socket.timeout) as e:
                print(f"Connection failed, retrying... Error: {e}")
                time.sleep(2)

    def _recvall(self, count):
        buf = b""
        while count:
            new = self.sock.recv(count)
            if not new:
                return None
            buf += new
            count -= len(new)
        return buf

    def _send_encrypted(self, data: bytes):
        cipher = AES.new(self.aes_key, AES.MODE_EAX)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        self.sock.sendall(struct.pack('!I', len(cipher.nonce)))
        self.sock.sendall(cipher.nonce)
        self.sock.sendall(struct.pack('!I', len(tag)))
        self.sock.sendall(tag)
        self.sock.sendall(struct.pack('!I', len(ciphertext)))
        self.sock.sendall(ciphertext)

    def _recv_encrypted(self) -> bytes:
        nonce_len = struct.unpack('!I', self._recvall(4))[0]
        nonce = self._recvall(nonce_len)
        tag_len = struct.unpack('!I', self._recvall(4))[0]
        tag = self._recvall(tag_len)
        ct_len = struct.unpack('!I', self._recvall(4))[0]
        ciphertext = self._recvall(ct_len)
        cipher = AES.new(self.aes_key, AES.MODE_EAX, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def send_message(self, message: dict):
        msg_bytes = json.dumps(message).encode()
        self._send_encrypted(msg_bytes)

    def recv_message(self) -> dict:
        resp_bytes = self._recv_encrypted()
        return json.loads(resp_bytes.decode())

    def run(self):
        try:
            while True:
                payload = self._recv_encrypted()
                h_len = struct.unpack('!I', payload[:4])[0]
                header = json.loads(payload[4:4+h_len].decode())
                frame_data = payload[4+h_len:]
                frame = np.frombuffer(frame_data, dtype=np.dtype(header["dtype"]))
                frame = frame.reshape(header["shape"])

                mask = ImgUtils.threshold(frame)
                warped = ImgUtils.warp(mask)
                result = self.pid.process(warped)
                error, pid_out, left, right, lf, rf, derivative, integral, prev_error = result

                if self.gui.control_flags.get("stopped", False):
                    left = right = 0.0
                    lf = rf = 0

                resp_dict = {
                    "left_duty": left,
                    "right_duty": right,
                    "left_freq": lf,
                    "right_freq": rf
                }
                resp_bytes = (json.dumps(resp_dict) + "\n").encode()
                self._send_encrypted(resp_bytes)

                mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
                pid_img = self.gui.pid_graph.update(error, pid_out)
                info = (
                    f"Centroid Err: {error:.2f} | PID: {pid_out:.4f}\n"
                    f"Integral: {integral:.4f} | Deriv: {derivative:.4f} | Prev Err: {prev_error:.4f}\n"
                    f"Left Duty: {left:.3f}, Right Duty: {right:.3f} | "
                    f"Left Freq: {lf}, Right Freq: {rf}"
                )
                self.gui.update_gui(frame, mask_bgr, warped_bgr, pid_img, info)
        except (ConnectionResetError, BrokenPipeError, socket.timeout) as e:
            print(f"[Connection Error] {e}")
        finally:
            if self.sock:
                self.sock.close()

def main():
    server_ip = "raspitwo.local"
    server_port = 8000
    client = Client(None, server_ip, server_port)
    client.connect()

    auth_window = AuthWindow(client)
    auth_window.mainloop()

    if auth_window.authenticated:
        gui = GUI()
        client.gui = gui
        gui.server = client
        client.start()
        gui.mainloop()
    else:
        print("Authentication failed.")

if __name__ == "__main__":
    main()