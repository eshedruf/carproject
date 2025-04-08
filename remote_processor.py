import socket
import struct
import json
import threading
import numpy as np
import cv2
import time
from image_utils import ImgUtils
from pid_controller import PID
from gui import GUI

class RemoteClient(threading.Thread):
    """
    Client thread that persistently connects to the Raspberry Pi,
    processes received images, and sends back PWM values.
    """
    def __init__(self, gui, pi_ip, pi_port):
        super().__init__(daemon=True)
        self.gui = gui
        self.pi_ip = pi_ip
        self.pi_port = pi_port
        self.sock = None
        self.pid = PID()
        self.running = True

    def connect(self):
        """Attempts to connect to the Pi, retrying until successful."""
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.pi_ip, self.pi_port))
                print(f"Connected to Raspberry Pi at {self.pi_ip}:{self.pi_port}")
                return True
            except (ConnectionRefusedError, socket.error) as e:
                print(f"Connection failed ({e}), retrying in 2 seconds...")
                self.sock.close()
                time.sleep(2)  # Wait before retrying
        return False

    def run(self):
        """Main loop: connect, process frames, and reconnect if needed."""
        while self.running:
            if not self.connect():
                break  # Exit if running is False

            try:
                while self.running:
                    # Receive header length
                    head = self._recvall(4)
                    if not head:
                        break
                    h_len = struct.unpack("!I", head)[0]
                    hdr = json.loads(self._recvall(h_len).decode())
                    
                    # Receive frame data
                    d_len = struct.unpack("!I", self._recvall(4))[0]
                    data = self._recvall(d_len)
                    if data is None:
                        break
                    frame = np.frombuffer(data, dtype=np.dtype(hdr["dtype"])).reshape(hdr["shape"])
                    
                    # Process frame
                    mask = ImgUtils.threshold(frame)
                    warped = ImgUtils.warp(mask)
                    result = self.pid.process(warped)
                    error, pid_out, left, right, lf, rf, derivative, integral, prev_error = result
                    
                    # Handle stop flag
                    if self.gui.control_flags.get("stopped", False):
                        left = right = 0.0
                        lf = rf = 0
                    
                    # Send PWM response
                    resp = json.dumps({
                        "left_duty": left,
                        "right_duty": right,
                        "left_freq": lf,
                        "right_freq": rf
                    }) + "\n"
                    self.sock.sendall(resp.encode())
                    
                    # Prepare GUI images
                    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                    warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
                    pid_img = self.gui.pid_graph.update(error, pid_out)
                    
                    # Debug info
                    info = (
                        f"Centroid Err: {error:.2f} | PID: {pid_out:.4f}\n"
                        f"Integral: {integral:.4f} | Deriv: {derivative:.4f} | Prev Err: {prev_error:.4f}\n"
                        f"Left Duty: {left:.3f}, Right Duty: {right:.3f} | "
                        f"Left Freq: {lf}, Right Freq: {rf}"
                    )
                    
                    # Update GUI
                    self.gui.update_gui(frame, mask_bgr, warped_bgr, pid_img, info)
            except (ConnectionError, socket.error) as e:
                print(f"Connection lost ({e}), attempting to reconnect...")
            finally:
                if self.sock:
                    self.sock.close()
                    self.sock = None
            time.sleep(1)  # Small delay before retrying to avoid spamming

    def _recvall(self, count):
        """Helper method to receive exactly 'count' bytes."""
        buf = b""
        while count and self.running:
            new = self.sock.recv(count)
            if not new:
                return None
            buf += new
            count -= len(new)
        return buf if buf else None

    def stop(self):
        """Stops the client thread."""
        self.running = False
        if self.sock:
            self.sock.close()

def main():
    gui = GUI()
    PI_IP = "192.168.0.143"  # Replace with your Pi's IP address
    PI_PORT = 8000
    client = RemoteClient(gui, PI_IP, PI_PORT)
    gui.client = client  # For PID reset or other access
    client.start()
    try:
        gui.mainloop()
    finally:
        client.stop()

if __name__ == "__main__":
    main()