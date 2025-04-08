import tkinter as tk
from tkinter import messagebox
import socket
import threading
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Random import get_random_bytes
from protocol import Protocol

class AuthWindow(tk.Tk):
    def __init__(self, host, port):
        super().__init__()
        self.title("Authentication")
        self.authenticated = False
        self.sock = None
        self.aes_key = None
        self.host = host
        self.port = port

        tk.Button(self, text="Sign up", command=self.show_signup).pack()
        tk.Button(self, text="Log in", command=self.show_login).pack()

    def show_signup(self):
        self.clear()
        tk.Label(self, text="Username:").pack()
        self.username_entry = tk.Entry(self)
        self.username_entry.pack()
        tk.Label(self, text="Password:").pack()
        self.password_entry = tk.Entry(self, show="*")
        self.password_entry.pack()
        tk.Label(self, text="Age:").pack()
        self.age_entry = tk.Entry(self)
        self.age_entry.pack()
        tk.Button(self, text="Submit", command=lambda: self.submit("signup")).pack()

    def show_login(self):
        self.clear()
        tk.Label(self, text="Username:").pack()
        self.username_entry = tk.Entry(self)
        self.username_entry.pack()
        tk.Label(self, text="Password:").pack()
        self.password_entry = tk.Entry(self, show="*")
        self.password_entry.pack()
        tk.Button(self, text="Submit", command=lambda: self.submit("login")).pack()

    def clear(self):
        for widget in self.winfo_children():
            widget.destroy()

    def submit(self, auth_type):
        username = self.username_entry.get()
        password = self.password_entry.get()
        age = int(self.age_entry.get()) if auth_type == "signup" else -1
        threading.Thread(target=self.authenticate, args=(auth_type, username, password, age)).start()

    def authenticate(self, auth_type, username, password, age):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))
            public_key = sock.recv(2048)
            rsa_key = RSA.import_key(public_key)
            cipher_rsa = PKCS1_OAEP.new(rsa_key)
            aes_key = get_random_bytes(32)
            encrypted_aes_key = cipher_rsa.encrypt(aes_key)
            sock.sendall(encrypted_aes_key)

            auth_message = {"type": auth_type, "username": username, "password": password, "age": age}
            Protocol.send_encrypted_message(sock, auth_message, aes_key)
            response = Protocol.receive_encrypted_message(sock, aes_key)

            if response and response["type"] == "auth_response" and response["status"] == "success":
                self.authenticated = True
                self.sock = sock
                self.aes_key = aes_key
                messagebox.showinfo("Success", "Authentication successful!")
                self.destroy()
            else:
                messagebox.showerror("Error", response.get("reason", "Authentication failed"))
        except Exception as e:
            messagebox.showerror("Error", str(e))