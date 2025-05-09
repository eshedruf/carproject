import socket
import struct
import json
import numpy as np
from typing import Optional
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto import Random
import cv2
import base64

MAX_CLIENTS = 1  # Adjustable as needed

class ConnectionClosedError(Exception):
    pass

class Protocol:
    CMDS = {
        'RSAKEY': 'rsakey',
        'AESKEY': 'aeskey',
        'SIGNUP': 'signup',
        'LOGIN': 'login',
        'PWM': 'pwm',
        'UDP_PORT': 'udp_port'
    }

    # JSON Message Structures:
    # - 'RSAKEY': {"type": "rsakey", "public_key": str (base64)}
    # - 'AESKEY': {"type": "aeskey", "encrypted_aes_key": str (base64)}
    # - 'SIGNUP': {"type": "signup", "username": str, "password": str, "age": int}
    # - 'LOGIN': {"type": "login", "username": str, "password": str}
    # - 'PWM': {"type": "pwm", "left_duty": float, "right_duty": float, "left_freq": int, "right_freq": int}
    # - 'UDP_PORT': {"type": "udp_port", "port": int}

    def __init__(self, role: str, host: Optional[str] = None, port: Optional[int] = None,
                 listen_sock: Optional[socket.socket] = None):
        self.role = role
        if role == 'server' and listen_sock is not None:
            self.sock = listen_sock
        else:
            self.host = host
            self.port = port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if role == 'server':
                self.sock.bind((host, port))
                self.sock.listen(MAX_CLIENTS)
        self.conn = None
        self.aes_key = None

    def connect(self):
        if self.role == 'client':
            self.sock.connect((self.host, self.port))

    def accept(self):
        if self.role == 'server':
            self.conn, addr = self.sock.accept()
            return self.conn, addr
        return None, None

    def send_unencrypted_json(self, msg: dict):
        data = json.dumps(msg).encode()
        length = struct.pack('I', len(data))
        if self.role == 'server':
            self.conn.sendall(length + data)
        else:
            self.sock.sendall(length + data)

    def recv_unencrypted_json(self) -> dict:
        sock = self.conn if self.role == 'server' else self.sock
        length = struct.unpack('I', self._recv_exact(sock, 4))[0]
        data = self._recv_exact(sock, length)
        return json.loads(data.decode())

    def key_exchange(self):
        if self.role == 'server':
            rsa_key = RSA.generate(2048)
            pub_key = rsa_key.publickey().exportKey()
            pub_key_b64 = base64.b64encode(pub_key).decode()
            self.send_unencrypted_json({"type": self.CMDS['RSAKEY'], "public_key": pub_key_b64})
            response = self.recv_unencrypted_json()
            if response.get("type") != self.CMDS['AESKEY']:
                raise ValueError("Invalid AESKEY response")
            encrypted_aes_key = base64.b64decode(response.get("encrypted_aes_key"))
            cipher = PKCS1_OAEP.new(rsa_key)
            self.aes_key = cipher.decrypt(encrypted_aes_key)
        else:
            init_msg = self.recv_unencrypted_json()
            if init_msg.get("type") != self.CMDS['RSAKEY']:
                raise ValueError("Invalid RSAKEY message")
            pub_key = base64.b64decode(init_msg.get("public_key"))
            cipher = PKCS1_OAEP.new(RSA.importKey(pub_key))
            self.aes_key = Random.new().read(32)
            encrypted_aes_key = cipher.encrypt(self.aes_key)
            encrypted_aes_key_b64 = base64.b64encode(encrypted_aes_key).decode()
            self.send_unencrypted_json({"type": self.CMDS['AESKEY'], "encrypted_aes_key": encrypted_aes_key_b64})

    def send_json(self, msg: dict):
        data = json.dumps(msg).encode()
        cipher = AES.new(self.aes_key, AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(data)
        to_send = cipher.nonce + tag + ct
        length = struct.pack('I', len(to_send))
        if self.role == 'server':
            self.conn.sendall(length + to_send)
        else:
            self.sock.sendall(length + to_send)

    def recv_json(self) -> dict:
        sock = self.conn if self.role == 'server' else self.sock
        length = struct.unpack('I', self._recv_exact(sock, 4))[0]
        data = self._recv_exact(sock, length)
        nonce, tag, ct = data[:16], data[16:32], data[32:]
        cipher = AES.new(self.aes_key, AES.MODE_GCM, nonce=nonce)
        pt = cipher.decrypt_and_verify(ct, tag)
        return json.loads(pt.decode())

    def send_frame(self, frame: np.ndarray):
        data = frame.tobytes()
        cipher = AES.new(self.aes_key, AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(data)
        to_send = cipher.nonce + tag + ct
        length = struct.pack('I', len(to_send))
        if self.role == 'server':
            self.conn.sendall(length + to_send)
        else:
            self.sock.sendall(length + to_send)

    def recv_frame(self) -> np.ndarray:
        sock = self.conn if self.role == 'server' else self.sock
        length = struct.unpack('I', self._recv_exact(sock, 4))[0]
        data = self._recv_exact(sock, length)
        nonce, tag, ct = data[:16], data[16:32], data[32:]
        cipher = AES.new(self.aes_key, AES.MODE_GCM, nonce=nonce)
        pt = cipher.decrypt_and_verify(ct, tag)
        return np.frombuffer(pt, dtype=np.uint8).reshape((380, 640, 3))

    def send_frame_udp(self, frame: np.ndarray, udp_addr: tuple, udp_socket: socket.socket):
        """
        Encode the frame to JPEG, encrypt it with AES-GCM, and send it over UDP to the specified address.
        
        :param frame: Numpy array representing the frame.
        :param udp_addr: Tuple (host, port) to send the frame to.
        :param udp_socket: UDP socket to use for sending.
        """
        ret, encoded = cv2.imencode(".jpg", frame)
        if not ret:
            raise ValueError("Failed to encode frame to JPEG")
        data = encoded.tobytes()
        cipher = AES.new(self.aes_key, AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(data)
        to_send = cipher.nonce + tag + ct
        length = struct.pack('I', len(to_send))
        udp_socket.sendto(length + to_send, udp_addr)

    def recv_frame_udp(self, udp_socket: socket.socket) -> np.ndarray:
        """
        Receive an AES-GCM encrypted JPEG-encoded frame from the UDP socket, decrypt it, and decode it.
        
        :param udp_socket: UDP socket to receive from.
        :return: Decoded frame as a numpy array.
        """
        data, _ = udp_socket.recvfrom(65535)  # Assuming max UDP packet size
        length = struct.unpack('I', data[:4])[0]
        data = data[4:4+length]
        nonce, tag, ct = data[:16], data[16:32], data[32:]
        cipher = AES.new(self.aes_key, AES.MODE_GCM, nonce=nonce)
        pt = cipher.decrypt_and_verify(ct, tag)
        buf = np.frombuffer(pt, np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Failed to decode frame from JPEG")
        return frame

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        data = b''
        while len(data) < n:
            more = sock.recv(n - len(data))
            if not more:
                raise ConnectionClosedError()
            data += more
        return data

    def close(self):
        if self.conn:
            self.conn.close()
        if self.role == 'client' or not self.conn:
            self.sock.close()