import json
import socket
import struct
import os
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Random import get_random_bytes

class Protocol:
    @staticmethod
    def encrypt_message(message, aes_key):
        """Encrypt a message (dict or bytes) with AES-GCM."""
        if isinstance(message, dict):
            message = json.dumps(message).encode('utf-8')
        nonce = os.urandom(12)  # 12-byte nonce for GCM
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(message)
        return nonce + ciphertext + tag  # nonce (12) + ciphertext + tag (16)

    @staticmethod
    def decrypt_message(encrypted, aes_key):
        """Decrypt an AES-GCM encrypted message."""
        nonce = encrypted[:12]
        tag = encrypted[-16:]
        ciphertext = encrypted[12:-16]
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
        try:
            message = cipher.decrypt_and_verify(ciphertext, tag)
            return json.loads(message.decode('utf-8')) if ciphertext else None
        except ValueError:
            return None

    @staticmethod
    def send_encrypted_message(conn, message, aes_key):
        """Send an encrypted message with length prefix."""
        encrypted = Protocol.encrypt_message(message, aes_key)
        conn.sendall(struct.pack("!I", len(encrypted)))
        conn.sendall(encrypted)

    @staticmethod
    def receive_encrypted_message(conn, aes_key):
        """Receive an encrypted message."""
        len_bytes = Protocol.recv_all(conn, 4)
        if not len_bytes:
            return None
        length = struct.unpack("!I", len_bytes)[0]
        encrypted = Protocol.recv_all(conn, length)
        if not encrypted:
            return None
        return Protocol.decrypt_message(encrypted, aes_key)

    @staticmethod
    def recv_all(conn, n):
        """Receive exactly n bytes from the connection."""
        data = bytearray()
        while len(data) < n:
            packet = conn.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)

    @staticmethod
    def send_encrypted_frame(conn, frame, aes_key):
        """Send a frame with encrypted metadata and data."""
        metadata = {
            "type": "frame",
            "shape": list(frame.shape),
            "dtype": str(frame.dtype)
        }
        Protocol.send_encrypted_message(conn, metadata, aes_key)
        frame_data = frame.tobytes()
        encrypted_data = Protocol.encrypt_message(frame_data, aes_key)
        conn.sendall(struct.pack("!I", len(encrypted_data)))
        conn.sendall(encrypted_data)

    @staticmethod
    def receive_encrypted_frame(conn, aes_key):
        """Receive an encrypted frame."""
        import numpy as np  # Assuming numpy is used for frames
        metadata = Protocol.receive_encrypted_message(conn, aes_key)
        if not metadata or metadata["type"] != "frame":
            return None
        len_bytes = Protocol.recv_all(conn, 4)
        if not len_bytes:
            return None
        length = struct.unpack("!I", len_bytes)[0]
        encrypted_data = Protocol.recv_all(conn, length)
        if not encrypted_data:
            return None
        frame_data = Protocol.decrypt_message(encrypted_data, aes_key)
        if frame_data:
            return np.frombuffer(frame_data, dtype=metadata["dtype"]).reshape(metadata["shape"])
        return None