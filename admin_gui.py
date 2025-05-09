# GUI for displaying video feed, PID graph, car IP, and debug data.

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
from image_utils import ImgUtils

class PIDGraph:
    """Generates a PID graph image with a 640x380 aspect ratio."""
    GRAPH_WIDTH = 640  # Updated to match the desired aspect ratio
    GRAPH_HEIGHT = 380  # Updated to match the desired aspect ratio
    MAX_POINTS = 100
    
    def __init__(self):
        self.error_list = []
        self.pid_list = []
    
    def map_val(self, val, in_min, in_max, out_min, out_max):
        return int((val - in_min) / (in_max - in_min) * (out_max - out_min) + out_min)
    
    def update(self, error, pid_output):
        """Update PID data and generate the graph image."""
        self.error_list.append(error)
        self.pid_list.append(pid_output)
        if len(self.error_list) > self.MAX_POINTS:
            self.error_list.pop(0)
            self.pid_list.pop(0)
        
        graph = 255 * np.ones((self.GRAPH_HEIGHT, self.GRAPH_WIDTH, 3), dtype=np.uint8)
        cv2.line(graph, (0, self.GRAPH_HEIGHT // 2), (self.GRAPH_WIDTH, self.GRAPH_HEIGHT // 2), (200,200,200), 1)
        spacing = self.GRAPH_WIDTH / (self.MAX_POINTS - 1)
        for i in range(1, len(self.error_list)):
            x1 = int((i - 1) * spacing)
            x2 = int(i * spacing)
            y1 = self.map_val(self.error_list[i-1], -1, 1, self.GRAPH_HEIGHT - 20, 20)
            y2 = self.map_val(self.error_list[i], -1, 1, self.GRAPH_HEIGHT - 20, 20)
            cv2.line(graph, (x1, y1), (x2, y2), (0, 255, 0), 2)
            py1 = self.map_val(self.pid_list[i-1], -0.1, 0.1, self.GRAPH_HEIGHT - 20, 20)
            py2 = self.map_val(self.pid_list[i], -0.1, 0.1, self.GRAPH_HEIGHT - 20, 20)
            cv2.line(graph, (x1, py1), (x2, py2), (255, 0, 0), 2)
        cv2.putText(graph, f"Err: {error:.3f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,150,0), 2)
        cv2.putText(graph, f"PID: {pid_output:.4f}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150,0,0), 2)
        return graph

class AdminGUI(tk.Tk):
    """GUI for displaying video feed, PID graph, car IP, and debug data."""
    
    def __init__(self):
        super().__init__()
        self.title("Car Control")
        self.geometry("1200x800")
        self.configure(bg="white")
        self.info = tk.StringVar()
        self.car_ip = tk.StringVar(value="Car IP: Not connected")
        self.control_flags = {"stopped": False}
        self.server = None  # Set by main so that reset can call PID.reset()
        self._build_widgets()
        self.pid_graph = PIDGraph()
    
    def _build_widgets(self):
        # Top frame for IP and buttons
        top_frame = ttk.Frame(self)
        top_frame.pack(pady=5, fill=tk.X)
        
        ip_label = ttk.Label(top_frame, textvariable=self.car_ip, font=("Helvetica", 12))
        ip_label.pack(side=tk.LEFT, padx=5)
        
        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Stop", command=self.stop).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Continue", command=self.continue_).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Reset PID", command=self.reset).pack(side=tk.LEFT, padx=5)
        
        # Middle frame for the four images
        mid_frame = ttk.Frame(self)
        mid_frame.pack(pady=5, expand=True, fill=tk.BOTH)
        self.orig_lbl = tk.Label(mid_frame)
        self.orig_lbl.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.mask_lbl = tk.Label(mid_frame)
        self.mask_lbl.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.warped_lbl = tk.Label(mid_frame)
        self.warped_lbl.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.pid_lbl = tk.Label(mid_frame)
        self.pid_lbl.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        
        # Bottom frame for debug info
        bot_frame = ttk.Frame(self)
        bot_frame.pack(pady=5, fill=tk.X)
        tk.Label(bot_frame, textvariable=self.info, font=("Helvetica", 12), fg="blue").pack()
    
    def resize_with_aspect_ratio(self, image, target_width, target_height):
        """Resize image to fit within target_width x target_height while maintaining 640:380 ratio."""
        aspect_ratio = 640 / 380
        target_aspect = target_width / target_height
        
        if target_aspect > aspect_ratio:
            new_h = target_height
            new_w = int(new_h * aspect_ratio)
        else:
            new_w = target_width
            new_h = int(new_w / aspect_ratio)
        
        resized = cv2.resize(image, (new_w, new_h))
        return resized
    
    def update_gui(self, orig_img, mask_img, warped_img, pid_img, info_str):
        """Update the four images and debug info with 640:380 aspect ratio preservation."""
        label_width = self.orig_lbl.winfo_width()
        label_height = self.orig_lbl.winfo_height()
        
        if label_width > 1 and label_height > 1:
            orig_resized = self.resize_with_aspect_ratio(orig_img, label_width, label_height)
            mask_resized = self.resize_with_aspect_ratio(mask_img, label_width, label_height)
            warped_resized = self.resize_with_aspect_ratio(warped_img, label_width, label_height)
            pid_resized = self.resize_with_aspect_ratio(pid_img, label_width, label_height)
            
            orig_resized = cv2.cvtColor(orig_resized, cv2.COLOR_BGR2RGB)
            mask_resized = cv2.cvtColor(mask_resized, cv2.COLOR_BGR2RGB)
            warped_resized = cv2.cvtColor(warped_resized, cv2.COLOR_BGR2RGB)
            pid_resized = cv2.cvtColor(pid_resized, cv2.COLOR_BGR2RGB)
            
            self.orig_photo = ImageTk.PhotoImage(image=Image.fromarray(orig_resized))
            self.mask_photo = ImageTk.PhotoImage(image=Image.fromarray(mask_resized))
            self.warped_photo = ImageTk.PhotoImage(image=Image.fromarray(warped_resized))
            self.pid_photo = ImageTk.PhotoImage(image=Image.fromarray(pid_resized))
            
            self.orig_lbl.config(image=self.orig_photo)
            self.orig_lbl.image = self.orig_photo  # keep reference to avoid flickering
            self.mask_lbl.config(image=self.mask_photo)
            self.mask_lbl.image = self.mask_photo
            self.warped_lbl.config(image=self.warped_photo)
            self.warped_lbl.image = self.warped_photo
            self.pid_lbl.config(image=self.pid_photo)
            self.pid_lbl.image = self.pid_photo
        
        self.info.set(info_str)
    
    def stop(self):
        """Set the stop flag so the server sends zero duty cycles."""
        self.control_flags["stopped"] = True
    
    def continue_(self):
        """Clear the stop flag to resume normal control."""
        self.control_flags["stopped"] = False
    
    def reset(self):
        """Reset the PID controller."""
        if self.server:
            self.server.pid.reset()
    
    def set_car_ip(self, ip):
        """Update the displayed car IP address."""
        self.car_ip.set(f"Car IP: {ip}")