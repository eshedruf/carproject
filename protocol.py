import socket
import struct
import json
import numpy as np
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto import Random

class ConnectionClosedError(Exception):
    pass

class Protocol:
    CMDS = {
        'SIGNUP': 'signup',
        'LOGIN': 'login',
        'PWM': 'pwm',
        'STOP': 'stop'
    }

    def __init__(self, role: str, host: str, port: int):
        self.role = role
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if role == 'server':
            self.sock.bind((host, port))
            self.sock.listen(1)
        self.conn = None
        self.aes_key = None

    def connect(self):
        if self.role != 'client':
            raise RuntimeError("connect can only be called on client")
        self.sock.connect((self.host, self.port))
        self.conn = self.sock
        self._perform_encryption_handshake()

    def accept(self):
        if self.role != 'server':
            raise RuntimeError("accept can only be called on server")
        self.conn, addr = self.sock.accept()
        print(f"Accepted connection from {addr}")
        self._perform_encryption_handshake()

    def _perform_encryption_handshake(self):
        if self.role == 'server':
            rsa_key = RSA.generate(2048)
            rsa_cipher = PKCS1_OAEP.new(rsa_key)
            pub_key = rsa_key.publickey().export_key()
            self.conn.sendall(struct.pack('!I', len(pub_key)))
            self.conn.sendall(pub_key)
            enc_key_len_bytes = self._recvall(4)
            if enc_key_len_bytes is None:
                raise ConnectionClosedError("Connection closed during handshake")
            enc_key_len = struct.unpack('!I', enc_key_len_bytes)[0]
            enc_key = self._recvall(enc_key_len)
            if enc_key is None:
                raise ConnectionClosedError("Connection closed during handshake")
            self.aes_key = rsa_cipher.decrypt(enc_key)
        elif self.role == 'client':
            pub_key_len_bytes = self._recvall(4)
            if pub_key_len_bytes is None:
                raise ConnectionClosedError("Connection closed during handshake")
            pub_key_len = struct.unpack('!I', pub_key_len_bytes)[0]
            pub_key = self._recvall(pub_key_len)
            if pub_key is None:
                raise ConnectionClosedError("Connection closed during handshake")
            rsa_pub = RSA.import_key(pub_key)
            rsa_cipher = PKCS1_OAEP.new(rsa_pub)
            self.aes_key = Random.get_random_bytes(16)
            enc_key = rsa_cipher.encrypt(self.aes_key)
            self.conn.sendall(struct.pack('!I', len(enc_key)))
            self.conn.sendall(enc_key)

    def _recvall(self, count):
        buf = b""
        while count:
            newbuf = self.conn.recv(count)
            if not newbuf:
                return None
            buf += newbuf
            count -= len(newbuf)
        return buf

    def _send_encrypted(self, data: bytes):
        cipher = AES.new(self.aes_key, AES.MODE_EAX)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        self.conn.sendall(struct.pack('!I', len(cipher.nonce)))
        self.conn.sendall(cipher.nonce)
        self.conn.sendall(struct.pack('!I', len(tag)))
        self.conn.sendall(tag)
        self.conn.sendall(struct.pack('!I', len(ciphertext)))
        self.conn.sendall(ciphertext)

    def _recv_encrypted(self) -> bytes:
        nonce_len_bytes = self._recvall(4)
        if nonce_len_bytes is None:
            raise ConnectionClosedError("Connection closed while receiving nonce length")
        nonce_len = struct.unpack('!I', nonce_len_bytes)[0]
        nonce = self._recvall(nonce_len)
        if nonce is None:
            raise ConnectionClosedError("Connection closed while receiving nonce")
        tag_len_bytes = self._recvall(4)
        if tag_len_bytes is None:
            raise ConnectionClosedError("Connection closed while receiving tag length")
        tag_len = struct.unpack('!I', tag_len_bytes)[0]
        tag = self._recvall(tag_len)
        if tag is None:
            raise ConnectionClosedError("Connection closed while receiving tag")
        ct_len_bytes = self._recvall(4)
        if ct_len_bytes is None:
            raise ConnectionClosedError("Connection closed while receiving ciphertext length")
        ct_len = struct.unpack('!I', ct_len_bytes)[0]
        ciphertext = self._recvall(ct_len)
        if ciphertext is None:
            raise ConnectionClosedError("Connection closed while receiving ciphertext")
        cipher = AES.new(self.aes_key, AES.MODE_EAX, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def send_json(self, data: dict):
        json_bytes = json.dumps(data).encode()
        self._send_encrypted(json_bytes)

    def recv_json(self) -> dict:
        json_bytes = self._recv_encrypted()
        return json.loads(json_bytes.decode())

    def send_frame(self, frame: np.ndarray):
        header = {"shape": frame.shape, "dtype": str(frame.dtype)}
        header_bytes = json.dumps(header).encode('utf-8')
        payload = struct.pack('!I', len(header_bytes)) + header_bytes + frame.tobytes()
        self._send_encrypted(payload)

    def recv_frame(self) -> np.ndarray:
        payload = self._recv_encrypted()
        h_len = struct.unpack('!I', payload[:4])[0]
        header = json.loads(payload[4:4 + h_len].decode())
        frame_data = payload[4 + h_len:]
        frame = np.frombuffer(frame_data, dtype=np.dtype(header["dtype"]))
        frame = frame.reshape(header["shape"])
        return frame

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        if self.role == 'client':
            if self.sock:
                self.sock.close()
                self.sock = None
        # For server, keep listening socket open
        self.aes_key = None  # Reset AES key