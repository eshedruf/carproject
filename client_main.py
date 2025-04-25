import threading
import time
import numpy as np
import cv2
from image_utils import ImgUtils
from pid_controller import PID
from gui import GUI
from auth_window import AuthWindow
from protocol import Protocol
import socket

class Client(threading.Thread):
    def __init__(self, server_ip, server_port):
        super().__init__(daemon=True)
        self.protocol = Protocol('client', server_ip, server_port)
        self.gui = None  # Will be set later
        self.pid = PID()
        self.running = False

    def connect(self):
        while True:
            try:
                self.protocol.connect()
                break
            except (ConnectionRefusedError, socket.timeout) as e:
                print(f"Connection failed: {e}. Retrying in 2 seconds...")
                time.sleep(2)

    def send_message(self, message: dict):
        self.protocol.send_json(message)

    def recv_message(self) -> dict:
        return self.protocol.recv_json()

    def run(self):
        self.running = True
        try:
            while self.running:
                frame = self.protocol.recv_frame()
                mask = ImgUtils.threshold(frame)
                warped = ImgUtils.warp(mask)
                result = self.pid.process(warped)
                error, pid_out, left, right, lf, rf, derivative, integral, prev_error = result

                if self.gui.control_flags.get("stopped", False):
                    left = right = 0.0
                    lf = rf = 0

                resp_dict = {
                    "type": self.protocol.CMDS['PWM'],
                    "left_duty": left,
                    "right_duty": right,
                    "left_freq": lf,
                    "right_freq": rf
                }
                self.protocol.send_json(resp_dict)

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
        except Exception as e:
            print(f"[Client Error] {e}")
            self.running = False
        finally:
            self.protocol.close()

def main():
    server_ip = "raspitwo.local"
    server_port = 8000
    client = Client(server_ip, server_port)
    client.connect()

    auth_window = AuthWindow(client)
    auth_window.mainloop()

    if auth_window.authenticated:
        gui = GUI()
        client.gui = gui
        gui.server = client
        client.start()
        gui.mainloop()
    else:
        print("Authentication failed.")

if __name__ == "__main__":
    main()