import tkinter as tk
from PIL import Image, ImageTk
import cv2
import queue

class SpectatorGUI(tk.Tk):
    """Simple GUI that displays only the raw camera feed for spectators."""
    def __init__(self, frame_queue):
        super().__init__()
        self.title("Car Viewer")
        self.geometry("800x500")
        self.configure(bg="black")

        self.car_ip = tk.StringVar(value="Car IP: Not connected")
        self.frame_queue = frame_queue

        self._build_widgets()
        self._check_queue()

    def _build_widgets(self):
        # Top frame for IP display
        top_frame = tk.Frame(self, bg="black")
        top_frame.pack(side=tk.TOP, fill=tk.X)
        ip_lbl = tk.Label(top_frame, textvariable=self.car_ip,
                          fg="white", bg="black", font=("Arial", 12))
        ip_lbl.pack(side=tk.LEFT, padx=10, pady=5)

        # Middle frame for video
        mid_frame = tk.Frame(self, bg="black")
        mid_frame.pack(expand=True, fill=tk.BOTH)
        self.video_lbl = tk.Label(mid_frame, bg="black")
        self.video_lbl.pack(expand=True, fill=tk.BOTH)

    def _check_queue(self):
        # Poll the queue for new frames
        try:
            while True:
                frame = self.frame_queue.get_nowait()
                self._display_frame(frame)
        except queue.Empty:
            pass
        # Check again after 10ms
        self.after(10, self._check_queue)

    def _display_frame(self, frame):
        # Resize frame to label size while keeping aspect ratio
        w = self.video_lbl.winfo_width()
        h = self.video_lbl.winfo_height()
        if w > 1 and h > 1:
            aspect = frame.shape[1] / frame.shape[0]
            if w / aspect <= h:
                new_w = w
                new_h = int(w / aspect)
            else:
                new_h = h
                new_w = int(h * aspect)
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            # Convert BGR to RGB for Tkinter
            img = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            photo = ImageTk.PhotoImage(img)
            self.video_lbl.config(image=photo)
            self.video_lbl.image = photo  # keep a reference

    def set_car_ip(self, ip: str):
        self.car_ip.set(f"Car IP: {ip}")
