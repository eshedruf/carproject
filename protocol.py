import tkinter as tk
import json

class AuthWindow(tk.Tk):
    def __init__(self, client):
        super().__init__()
        self.title("Authentication")
        self.geometry("300x200")
        self.client = client
        self.authenticated = False
        self._build_widgets()

    def _build_widgets(self):
        tk.Label(self, text="Username:").pack()
        self.username_entry = tk.Entry(self)
        self.username_entry.pack()

        tk.Label(self, text="Password:").pack()
        self.password_entry = tk.Entry(self, show='*')
        self.password_entry.pack()

        tk.Label(self, text="Age (for signup):").pack()
        self.age_entry = tk.Entry(self)
        self.age_entry.pack()

        tk.Button(self, text="Sign Up", command=self.signup).pack()
        tk.Button(self, text="Log In", command=self.login).pack()

        self.message_label = tk.Label(self, text="", fg="red")
        self.message_label.pack()

    def signup(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        age = self.age_entry.get()
        if not username or not password or not age:
            self.message_label.config(text="All fields are required for signup")
            return
        try:
            age = int(age)
        except ValueError:
            self.message_label.config(text="Age must be an integer")
            return
        request = {"type": "signup", "username": username, "password": password, "age": age}
        self.client.send_message(request)
        response = self.client.recv_message()
        if response["status"] == "success":
            self.message_label.config(text="Signup successful, please log in", fg="green")
        else:
            self.message_label.config(text=response["message"], fg="red")

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        if not username or not password:
            self.message_label.config(text="Username and password are required")
            return
        request = {"type": "login", "username": username, "password": password}
        self.client.send_message(request)
        response = self.client.recv_message()
        if response["status"] == "success":
            self.authenticated = True
            self.destroy()
        else:
            self.message_label.config(text=response["message"], fg="red")