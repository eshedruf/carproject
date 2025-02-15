import socket
import struct
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Random import get_random_bytes


class Client:
    def __init__(self, server_ip="SERVER_IP", port=5000):
        self.server_ip = server_ip
        self.port = port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_public_key = None
        self.aes_key = get_random_bytes(16)  # AES-128 Key (use 32 bytes for AES-256)

    def start(self):
        self.client_socket.connect((self.server_ip, self.port))
        print(f"Connected to server at {self.server_ip}:{self.port}")

        self.receive_rsa_public_key()
        self.send_encrypted_aes_key()
        self.send_commands()

    def receive_rsa_public_key(self):
        """Receives the RSA public key from the server."""
        public_pem = self._recv_msg()
        if public_pem:
            self.server_public_key = RSA.import_key(public_pem)
            print("Received RSA public key from server")

    def send_encrypted_aes_key(self):
        """Encrypts the AES key using the RSA public key and sends it."""
        cipher_rsa = PKCS1_OAEP.new(self.server_public_key)
        encrypted_aes_key = cipher_rsa.encrypt(self.aes_key)
        self._send_msg(encrypted_aes_key)
        print("Sent encrypted AES key to server")

    def send_commands(self):
        """Takes user input, encrypts it with AES, and sends it."""
        try:
            while True:
                command = input("Enter command (or 'exit' to quit): ")
                if command.lower() == "exit":
                    break
                self._send_encrypted(command)
                response = self._recv_encrypted()
                if response is None:
                    print("Server disconnected")
                    break
                print(f"Server response: {response}")
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        finally:
            self.client_socket.close()

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
    client = SecureClient(server_ip="192.168.0.133")  # Change to your server's IP
    client.start()
