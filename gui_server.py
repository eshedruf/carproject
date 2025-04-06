import cv2
import numpy as np
import time
import socket
import struct
import json
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# ------------------ PID and Image Processing Functions ------------------

# PID Constants
Kp = 0.05      # Proportional gain
Ki = 0.0010     # Integral gain
Kd = 0.03      # Derivative gain

# Global PID state variables
previous_error = 0.0
integral = 0.0

def determine_freq(duty_cycle):
    if duty_cycle < 0.05:
        return 20
    elif duty_cycle < 0.075:
        return 30
    elif duty_cycle < 0.09:
        return 45
    elif duty_cycle < 0.11:
        return 65
    elif duty_cycle < 0.15:
        return 80
    else:
        return 50

def compute_pid(error):
    global previous_error, integral
    integral += error
    derivative = error - previous_error
    output = Kp * error + Ki * integral + Kd * derivative
    previous_error = error
    return output

def map_val(val, in_min, in_max, out_min, out_max):
    return int((val - in_min) / (in_max - in_min) * (out_max - out_min) + out_min)

# PID Graph Setup
GRAPH_WIDTH = 600
GRAPH_HEIGHT = 200
MAX_POINTS = 100  # Number of data points to show
error_list = []
pid_list = []

def update_pid_graph(error, pid_output):
    error_list.append(error)
    pid_list.append(pid_output)
    if len(error_list) > MAX_POINTS:
        error_list.pop(0)
        pid_list.pop(0)

    graph = np.full((GRAPH_HEIGHT, GRAPH_WIDTH, 3), 255, dtype=np.uint8)
    cv2.line(graph, (0, GRAPH_HEIGHT // 2), (GRAPH_WIDTH, GRAPH_HEIGHT // 2), (200, 200, 200), 1)
    spacing = GRAPH_WIDTH / (MAX_POINTS - 1)
    for i in range(1, len(error_list)):
        y1 = map_val(error_list[i-1], -1, 1, GRAPH_HEIGHT - 10, 10)
        y2 = map_val(error_list[i], -1, 1, GRAPH_HEIGHT - 10, 10)
        x1 = int((i - 1) * spacing)
        x2 = int(i * spacing)
        cv2.line(graph, (x1, y1), (x2, y2), (0, 255, 0), 2)
        py1 = map_val(pid_list[i-1], -0.1, 0.1, GRAPH_HEIGHT - 10, 10)
        py2 = map_val(pid_list[i], -0.1, 0.1, GRAPH_HEIGHT - 10, 10)
        cv2.line(graph, (x1, py1), (x2, py2), (255, 0, 0), 2)
    cv2.putText(graph, f"Error: {error:.3f}", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 150, 0), 2)
    cv2.putText(graph, f"PID: {pid_output:.4f}", (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 0, 0), 2)
    return graph

# ------------------ Utility Function ------------------
def resize_image_with_aspect(image, allocated_width, allocated_height):
    """
    Resize the image to the maximum possible dimensions within allocated_width and allocated_height,
    while maintaining its aspect ratio.
    """
    h, w = image.shape[:2]
    scale = min(allocated_width / w, allocated_height / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h))

# ------------------ Server Thread ------------------

class ServerThread(threading.Thread):
    def __init__(self, gui_callback, client_list_callback, control_flags):
        """
        gui_callback: function to update GUI images and info.
        client_list_callback: function to update list of connected clients.
        control_flags: dict containing control flags, e.g., "stopped".
        """
        super().__init__(daemon=True)
        self.gui_callback = gui_callback
        self.client_list_callback = client_list_callback
        self.control_flags = control_flags
        self.running = True
        self.server_sock = None

    def run(self):
        HOST = ''  # Listen on all interfaces
        PORT = 8000
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind((HOST, PORT))
        self.server_sock.listen(5)
        print(f"Server listening on port {PORT}...")
        while self.running:
            print("Waiting for a client to connect...")
            try:
                conn, addr = self.server_sock.accept()
            except Exception as e:
                print("Error accepting connection:", e)
                continue
            print(f"Connected by {addr}")
            self.client_list_callback([str(addr)])
            try:
                while self.running:
                    raw_header_len = self.recvall(conn, 4)
                    if not raw_header_len:
                        break
                    header_len = struct.unpack("!I", raw_header_len)[0]
                    header_bytes = self.recvall(conn, header_len)
                    if not header_bytes:
                        break
                    header = json.loads(header_bytes.decode("utf-8"))
                    
                    raw_data_len_bytes = self.recvall(conn, 4)
                    if not raw_data_len_bytes:
                        break
                    raw_data_len = struct.unpack("!I", raw_data_len_bytes)[0]
                    data = self.recvall(conn, raw_data_len)
                    if not data:
                        break
                    
                    try:
                        frame = np.frombuffer(data, dtype=np.dtype(header["dtype"]))
                        frame = frame.reshape(header["shape"])
                    except Exception as e:
                        print("Error reconstructing image:", e)
                        continue
                    if frame is None or frame.size == 0:
                        continue

                    # --- Image Processing ---
                    imgHsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    lower = np.array([125, 50, 50])
                    upper = np.array([160, 255, 255])
                    mask = cv2.inRange(imgHsv, lower, upper)
                    
                    h, w = mask.shape[:2]
                    w_sub = 50
                    h_sub = 120
                    pts1 = np.float32([[w_sub, h - h_sub], [w - w_sub, h - h_sub], [0, h], [w, h]])
                    pts2 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
                    matrix = cv2.getPerspectiveTransform(pts1, pts2)
                    imgWarp = cv2.warpPerspective(mask, matrix, (w, h))
                    
                    M = cv2.moments(imgWarp)
                    centroid_x = int(M["m10"] / M["m00"]) if M["m00"] != 0 else w // 2
                    error = (centroid_x - (w / 2)) / (w / 2)
                    pid_output = compute_pid(error)
                    base_duty = 0.07
                    left_duty = base_duty + pid_output
                    right_duty = base_duty - pid_output
                    
                    right_calib = 0.65
                    min_duty = base_duty - 0.03
                    max_duty = base_duty + 0.02
                    left_duty = max(min_duty, min(left_duty, max_duty))
                    right_duty = max(min_duty, min(right_duty, max_duty)) * right_calib
                    
                    left_freq = determine_freq(left_duty)
                    right_freq = determine_freq(right_duty)
                    
                    # Override PWM if stopped: duty cycles become 0
                    if self.control_flags.get("stopped", False):
                        left_duty = 0.0
                        right_duty = 0.0
                        left_freq = 0
                        right_freq = 0
                    
                    pwm_info = {
                        "left_duty": left_duty,
                        "right_duty": right_duty,
                        "left_freq": left_freq,
                        "right_freq": right_freq
                    }
                    response = json.dumps(pwm_info) + "\n"
                    conn.sendall(response.encode("utf-8"))
                    
                    # Create visualization images
                    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                    warp_bgr = cv2.cvtColor(imgWarp, cv2.COLOR_GRAY2BGR)
                    
                    # For warp video, draw a constant thin red line at the center...
                    cv2.line(warp_bgr, (w//2, 0), (w//2, h), (0, 0, 255), 2)
                    # ...and a thin orange line at the computed centroid.
                    cv2.line(warp_bgr, (centroid_x, 0), (centroid_x, h), (0, 165, 255), 2)
                    
                    combined = cv2.hconcat([frame, mask_bgr, warp_bgr])
                    pid_graph = update_pid_graph(error, pid_output)
                    
                    # Update GUI (convert BGR to RGB for display)
                    disp_combined = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
                    disp_pid = cv2.cvtColor(pid_graph, cv2.COLOR_BGR2RGB)
                    
                    self.gui_callback(disp_combined, disp_pid, 
                                      f"Centroid: {centroid_x}\nError: {error:.2f}\nPID Output: {pid_output:.4f}\n"
                                      f"Integral: {integral:.4f}\nPrev Error: {previous_error:.4f}\n"
                                      f"Left Duty: {left_duty:.3f}, Right Duty: {right_duty:.3f}\n"
                                      f"Left Freq: {left_freq}, Right Freq: {right_freq}")
            except Exception as e:
                print("Client error:", e)
            finally:
                conn.close()
                self.client_list_callback([])  # Clear client list when disconnected
        self.server_sock.close()

    def recvall(self, conn, length):
        data = b""
        while len(data) < length:
            more = conn.recv(length - len(data))
            if not more:
                return None
            data += more
        return data

    def stop(self):
        self.running = False
        if self.server_sock:
            self.server_sock.close()

# ------------------ Tkinter GUI Application ------------------

class CarControlGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        # Set full screen mode
        self.attributes("-fullscreen", True)
        self.configure(bg="white")
        
        # Shared control flags for server thread
        self.control_flags = {"stopped": False}

        # Style configuration
        style = ttk.Style(self)
        style.configure("TFrame", background="white")
        style.configure("TLabel", background="white", font=("Helvetica", 12))
        style.configure("TButton", font=("Helvetica", 12))

        # Top frame: Client list and control buttons
        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="Connected Clients:").pack(side=tk.LEFT, padx=5)
        self.client_listbox = tk.Listbox(top_frame, height=2, width=40, font=("Helvetica", 12))
        self.client_listbox.pack(side=tk.LEFT, padx=10)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.LEFT, padx=10)
        self.btn_stop = ttk.Button(btn_frame, text="Stop Car", command=self.stop_car)
        self.btn_stop.pack(pady=5, fill=tk.X)
        self.btn_continue = ttk.Button(btn_frame, text="Continue", command=self.continue_car)
        self.btn_continue.pack(pady=5, fill=tk.X)
        self.btn_reset = ttk.Button(btn_frame, text="Reset PID", command=self.reset_pid)
        self.btn_reset.pack(pady=5, fill=tk.X)

        # Middle frame: Processed Views image and PID Graph
        mid_frame = ttk.Frame(self)
        mid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.lbl_view = ttk.Label(mid_frame)
        self.lbl_view.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=10)

        self.lbl_pid = ttk.Label(mid_frame)
        self.lbl_pid.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=10)

        # Bottom frame: Info text
        self.info_text = tk.StringVar()
        self.lbl_info = ttk.Label(self, textvariable=self.info_text, font=("Helvetica", 14), foreground="blue")
        self.lbl_info.pack(side=tk.BOTTOM, pady=10)

        # Start server thread
        self.server_thread = ServerThread(self.update_gui, self.update_client_list, self.control_flags)
        self.server_thread.start()

        self.after(30, self.periodic_update)

    def update_gui(self, view_img, pid_img, info_str):
        # Get current screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Allocate maximum sizes for each image while preserving aspect ratio.
        # We'll allocate 70% of screen width for view image and 30% for PID image,
        # and both images can use up to 80% of screen height.
        allocated_width_view = screen_width * 0.7
        allocated_width_pid = screen_width * 0.3
        allocated_height = screen_height * 0.8
        
        disp_combined = resize_image_with_aspect(view_img, allocated_width_view, allocated_height)
        disp_pid = resize_image_with_aspect(pid_img, allocated_width_pid, allocated_height)
        
        self.latest_view = ImageTk.PhotoImage(image=Image.fromarray(disp_combined))
        self.latest_pid = ImageTk.PhotoImage(image=Image.fromarray(disp_pid))
        self.lbl_view.configure(image=self.latest_view)
        self.lbl_pid.configure(image=self.latest_pid)
        self.info_text.set(info_str)

    def update_client_list(self, clients):
        self.client_listbox.delete(0, tk.END)
        for client in clients:
            self.client_listbox.insert(tk.END, client)

    def stop_car(self):
        self.control_flags["stopped"] = True
        print("Car stopped: Duty cycles set to 0.")

    def continue_car(self):
        self.control_flags["stopped"] = False
        print("Car control resumed.")

    def reset_pid(self):
        global previous_error, integral
        previous_error = 0.0
        integral = 0.0
        print("PID variables reset.")

    def periodic_update(self):
        self.after(30, self.periodic_update)

    def on_close(self):
        self.server_thread.stop()
        self.destroy()

if __name__ == "__main__":
    app = CarControlGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
