import socket
import threading
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from protocol import Protocol

class PiServer:
    def __init__(self, host='0.0.0.0', port=5000):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.server.listen()
        # RSA key generation
        self.rsa_key = RSA.generate(2048)
        self.rsa_public_key = self.rsa_key.publickey().export_key()
        self.rsa_decryptor = PKCS1_OAEP.new(self.rsa_key)
        # In-memory user database (temporary)
        self.users = {
            "user1": {"password": "pass1", "age": 25}
        }

    def run(self):
        while True:
            conn, addr = self.server.accept()
            print(f"Connected by {addr}")
            threading.Thread(target=self.handle_client, args=(conn,), daemon=True).start()

    def handle_client(self, conn):
        try:
            # RSA handshake
            conn.sendall(self.rsa_public_key)
            encrypted_aes_key = Protocol.recv_all(conn, 256)  # RSA 2048 ciphertext size
            if not encrypted_aes_key:
                conn.close()
                return
            aes_key = self.rsa_decryptor.decrypt(encrypted_aes_key)

            # Authentication
            auth_message = Protocol.receive_encrypted_message(conn, aes_key)
            if not auth_message:
                conn.close()
                return

            if auth_message["type"] == "login":
                success = self.check_login(auth_message["username"], auth_message["password"])
                response = {"type": "auth_response", "status": "success" if success else "failure",
                            "reason": "" if success else "invalid credentials"}
            elif auth_message["type"] == "signup":
                success = self.handle_signup(auth_message["username"], auth_message["password"], auth_message["age"])
                response = {"type": "auth_response", "status": "success" if success else "failure",
                            "reason": "" if success else "username exists"}
            else:
                response = {"type": "auth_response", "status": "failure", "reason": "invalid message"}
                conn.close()
                return

            Protocol.send_encrypted_message(conn, response, aes_key)
            if not success:
                conn.close()
                return

            # Main frame processing loop (assuming car object exists)
            self.process_frames(conn, aes_key)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            conn.close()

    def check_login(self, username, password):
        return username in self.users and self.users[username]["password"] == password

    def handle_signup(self, username, password, age):
        if username in self.users:
            return False
        self.users[username] = {"password": password, "age": age}
        return True

    def process_frames(self, conn, aes_key):
        while True:
            frame = self.car.capture_frame()  # Assuming this method exists
            Protocol.send_encrypted_frame(conn, frame, aes_key)
            pwm_response = Protocol.receive_encrypted_message(conn, aes_key)
            if not pwm_response or pwm_response["type"] != "pwm_response":
                break
            self.car.process_pwm_response(pwm_response["data"])  # Assuming this method exists

if __name__ == "__main__":
    server = PiServer()
    server.run()