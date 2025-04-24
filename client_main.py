import socket
import struct
import json
import threading
import time
import numpy as np, cv2
from image_utils import ImgUtils
from pid_controller import PID
from gui import GUI

class Client(threading.Thread):
    """Server thread that receives images, processes them, and updates the GUI."""
    
    def __init__(self, gui, server_ip, server_port):
        super().__init__(daemon=True)
        self.gui = gui
        self.pid = PID()
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
            
    def connect(self):
        """Establishes the TCP connection, retries if connection is refused."""
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.server_ip, self.server_port))
                print(f"Connected to remote processor at {self.server_ip}:{self.server_port}")
                break  # If the connection succeeds, break out of the loop
            except (ConnectionRefusedError, socket.timeout) as e:
                print(f"Connection failed, retrying... Error: {e}")
                time.sleep(2)  # Wait before retrying

    
    def run(self):
        try:
            # Ensure socket is connected before starting the loop
            self.connect()

            while True:
                head = self._recvall(4)
                if not head:
                    break
                h_len = struct.unpack("!I", head)[0]
                hdr = json.loads(self._recvall(h_len).decode())
                d_len = struct.unpack("!I", self._recvall(4))[0]
                data = self._recvall(d_len)
                if data is None:
                    break
                frame = np.frombuffer(data, dtype=np.dtype(hdr["dtype"])).reshape(hdr["shape"])

                mask = ImgUtils.threshold(frame)
                warped = ImgUtils.warp(mask)
                result = self.pid.process(warped)
                error, pid_out, left, right, lf, rf, derivative, integral, prev_error = result

                if self.gui.control_flags.get("stopped", False):
                    left = right = 0.0
                    lf = rf = 0

                resp = json.dumps({
                    "left_duty": left,
                    "right_duty": right,
                    "left_freq": lf,
                    "right_freq": rf
                }) + "\n"
                self.sock.sendall(resp.encode())

                mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
                pid_img = self.gui.pid_graph.update(error, pid_out)

                info = (
                    f"Centroid Err: {error:.2f} | PID: {pid_out:.4f}\n"
                    f"Integral: {integral:.4f} | Deriv: {derivative:.4f} | Prev Err: {prev_error:.4f}\n"
                    f"Left Duty: {left:.3f}, Right Duty: {right:.3f} | "
                    f"Left Freq: {lf}, Right Freq: {rf}"
                )

                self.gui.update_gui(frame, mask_bgr, warped_bgr, pid_img, info)
        except (ConnectionResetError, BrokenPipeError, socket.timeout) as e:
            print(f"[Connection Error] {e}")
        finally:
            if self.sock:
                self.sock.close()
    
    def _recvall(self, count):
        """Receive exactly 'count' bytes from the socket."""
        buf = b""
        while count:
            try:
                new = self.sock.recv(count)
                if not new:
                    return None
                buf += new
                count -= len(new)
            except socket.timeout:
                return None
        return buf


def main():
    gui = GUI()
    server_ip = "raspitwo.local"   # Replace with your actual server IP
    server_port = 8000            # Replace with your actual server port
    server = Client(gui, server_ip, server_port)
    gui.server = server  # For PID reset access
    server.start()
    gui.mainloop()


if __name__ == "__main__":
    main()
