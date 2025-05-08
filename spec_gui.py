import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import numpy as np

class SpectatorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spectator View")
        self.geometry("1200x800")
        self.configure(bg="white")

        # Same StringVars as AdminGUI
        self.car_ip = tk.StringVar(value="Car IP: Not connected")
        self.info   = tk.StringVar()
        self.control_flags = {}   # just for compatibility
        self.server = None        # filled in by client_main

        # Dummy PID-graph so client.pid_graph.update(...) won’t crash
        self.pid_graph = type("Stub", (), {
            "update": lambda *args, **kwargs: np.zeros((380, 640, 3), dtype=np.uint8)
        })()

        self._build_widgets()

    def _build_widgets(self):
        top = ttk.Frame(self)
        top.pack(pady=5, fill=tk.X)

        ttk.Label(top, textvariable=self.car_ip, font=("Helvetica",12)).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Close", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        # Only one large label for the camera feed
        self.orig_lbl = tk.Label(self)
        self.orig_lbl.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

        bot = ttk.Frame(self)
        bot.pack(pady=5, fill=tk.X)
        tk.Label(bot, textvariable=self.info, font=("Helvetica",12), fg="blue").pack()

    def resize_with_aspect_ratio(self, image, target_w, target_h):
        aspect = 640 / 380
        if (target_w / target_h) > aspect:
            nh = target_h
            nw = int(nh * aspect)
        else:
            nw = target_w
            nh = int(nw / aspect)
        return cv2.resize(image, (nw, nh))

    def update_gui(self, orig_img, mask_img, warped_img, pid_img, info_str):
        """
        Signature matches AdminGUI.update_gui:
          orig_img, mask_img, warped_img, pid_img, info_str
        We only display orig_img + info_str.
        """
        w = self.orig_lbl.winfo_width()
        h = self.orig_lbl.winfo_height()
        if w > 1 and h > 1:
            img = self.resize_with_aspect_ratio(orig_img, w, h)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self.photo = ImageTk.PhotoImage(Image.fromarray(img))
            self.orig_lbl.config(image=self.photo)
            self.orig_lbl.image = self.photo  # keep reference to avoid flickering

        self.info.set(info_str)

    def set_car_ip(self, ip):
        self.car_ip.set(f"Car IP: {ip}")
