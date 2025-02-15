import socket
import struct
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES


class Server:
    def __init__(self, host="0.0.0.0", port=5000):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket = None
        self.client_addr = None
        self.private_key = RSA.generate(2048)
        self.public_key = self.private_key.publickey()
        self.aes_key = None

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"Server listening on {self.host}:{self.port}")

        self.client_socket, self.client_addr = self.server_socket.accept()
        print(f"Connection from {self.client_addr}")

        self.send_rsa_public_key()
        self.receive_encrypted_aes_key()
        self.listen_for_messages()

    def send_rsa_public_key(self):
        """Sends the RSA public key to the client."""
        self._send_msg(self.public_key.export_key())
        print("Sent RSA public key to client")

    def receive_encrypted_aes_key(self):
        """Receives the AES key encrypted with RSA and decrypts it."""
        encrypted_aes_key = self._recv_msg()
        if encrypted_aes_key:
            cipher_rsa = PKCS1_OAEP.new(self.private_key)
            self.aes_key = cipher_rsa.decrypt(encrypted_aes_key)
            print("Received and decrypted AES key")

    def listen_for_messages(self):
        """Receives and decrypts messages from the client."""
        while True:
            plaintext = self._recv_encrypted()
            if plaintext is None:
                print("Connection closed by client")
                break
            print(f"Received: {plaintext}")
            self._send_encrypted(f"Command '{plaintext}' received")

        self.client_socket.close()
        self.server_socket.close()

    def _send_msg(self, msg):
        """Sends a message prefixed with its length."""
        msg_length = struct.pack(">I", len(msg))
        self.client_socket.sendall(msg_length + msg)

    def _recv_msg(self):
        """Receives a message with a prefixed 4-byte length."""
        raw_length = self._recvall(4)
        if not raw_length:
            return None
        msg_length = struct.unpack(">I", raw_length)[0]
        return self._recvall(msg_length)

    def _recvall(self, n):
        """Ensures receiving exactly `n` bytes."""
        data = b""
        while len(data) < n:
            packet = self.client_socket.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data

    def _send_encrypted(self, plaintext):
        """Encrypts and sends a message using AES."""
        cipher = AES.new(self.aes_key, AES.MODE_EAX)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        self._send_msg(cipher.nonce + tag + ciphertext)

    def _recv_encrypted(self):
        """Receives and decrypts an AES-encrypted message."""
        packet = self._recv_msg()
        if packet is None:
            return None
        nonce, tag, ciphertext = packet[:16], packet[16:32], packet[32:]
        cipher = AES.new(self.aes_key, AES.MODE_EAX, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()


if __name__ == "__main__":
    server = SecureServer()
    server.start()
