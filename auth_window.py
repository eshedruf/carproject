import tkinter as tk
import json

class AuthWindow(tk.Tk):
    def __init__(self, client):
        super().__init__()
        self.title("Authentication")
        self.geometry("600x400")
        self.client = client
        self.authenticated = False
        self.role = None
        self._build_initial_widgets()

    def _build_initial_widgets(self):
        self.message_label = tk.Label(self, text="Please choose an option:", fg="blue")
        self.message_label.pack(pady=10)

        tk.Button(self, text="Sign Up", command=self.show_signup).pack(pady=5)
        tk.Button(self, text="Log In", command=self.show_login).pack(pady=5)

    def show_signup(self):
        self.clear_window()
        self._build_signup_widgets()

    def show_login(self):
        self.clear_window()
        self._build_login_widgets()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def _build_signup_widgets(self):
        tk.Label(self, text="Username:").pack()
        self.username_entry = tk.Entry(self)
        self.username_entry.pack()

        tk.Label(self, text="Password:").pack()
        self.password_entry = tk.Entry(self, show='*')
        self.password_entry.pack()

        tk.Label(self, text="Age:").pack()
        self.age_entry = tk.Entry(self)
        self.age_entry.pack()

        tk.Button(self, text="Submit Sign Up", command=self.signup).pack(pady=10)

        self.message_label = tk.Label(self, text="", fg="red")
        self.message_label.pack()

    def _build_login_widgets(self):
        tk.Label(self, text="Username:").pack()
        self.username_entry = tk.Entry(self)
        self.username_entry.pack()

        tk.Label(self, text="Password:").pack()
        self.password_entry = tk.Entry(self, show='*')
        self.password_entry.pack()

        tk.Button(self, text="Submit Log In", command=self.login).pack(pady=10)

        self.message_label = tk.Label(self, text="", fg="red")
        self.message_label.pack()

    def signup(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        age = self.age_entry.get()
        if not username or not password or not age:
            self.message_label.config(text="All fields are required for signup")
            return
        request = {"type": "signup", "username": username, "password": password, "age": age}
        self.client.send_message(request)
        response = self.client.recv_message()
        if response["status"] == "success":
            self.authenticated = True
            self.role = "SPECTATOR"
            self.destroy()
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
            if username == "admin" and password == "admin":
                self.role = "ADMIN"
            else:
                self.role = "SPECTATOR"
            self.destroy()
        else:
            self.message_label.config(text=response["message"], fg="red")