import threading
import time
import numpy as np
import cv2
from image_utils import ImgUtils
from pid_controller import PID
from admin_gui import GUI as AdminGUI
from spec_gui import SpectatorGUI
from auth_window import AuthWindow
from protocol import Protocol
import socket

class Client(threading.Thread):
    def __init__(self, server_ip, server_port):
        super().__init__(daemon=True)
        self.protocol = Protocol('client', server_ip, server_port)
        self.gui = None
        self.pid = PID()
        self.running = False
        # Create UDP socket and bind to an available port
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('', 0))
        self.udp_port = self.udp_socket.getsockname()[1]

    def connect(self):
        while True:
            try:
                self.protocol.connect()
                print(f"Connected to server {self.protocol.host}:{self.protocol.port}")
                break
            except (ConnectionRefusedError, socket.timeout):
                print("Connection failed. Trying again in 2 seconds...")
                time.sleep(2)

    # Required by AuthWindow
    def send_message(self, msg: dict):
        self.protocol.send_json(msg)

    def recv_message(self) -> dict:
        return self.protocol.recv_json()

    def run(self):
        self.running = True
        try:
            while self.running:
                # Receive UDP datagram for JPEG-encoded frame
                data, _ = self.udp_socket.recvfrom(65535)
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

                mask = ImgUtils.threshold(frame)
                warped = ImgUtils.warp(mask)
                (error, pid_out,
                 left, right,
                 lf, rf,
                 derivative, integral, prev_error) = self.pid.process(warped)

                if self.gui.control_flags.get("stopped", False):
                    left = right = 0.0
                    lf = rf = 0

                pwm = {
                    "type": self.protocol.CMDS['PWM'],
                    "left_duty": left,
                    "right_duty": right,
                    "left_freq": lf,
                    "right_freq": rf
                }
                self.protocol.send_json(pwm)

                mask_bgr   = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
                pid_img    = self.gui.pid_graph.update(error, pid_out)

                info = (
                    f"Err: {error:.2f} | PID: {pid_out:.4f}\n"
                    f"I: {integral:.4f}  D: {derivative:.4f}\n"
                    f"Ld:{left:.3f}  Rd:{right:.3f} | "
                    f"Lf:{lf}  Rf:{rf}"
                )
                self.gui.update_gui(frame, mask_bgr, warped_bgr, pid_img, info)
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            self.protocol.close()

def main():
    client = Client("raspitwo.local", 8000)
    client.connect()

    auth_win = AuthWindow(client)
    auth_win.mainloop()

    if not auth_win.authenticated:
        print("Authentication failed or cancelled")
        return

    # Send UDP port registration to server
    client.protocol.send_json({"type": "UDP_PORT", "port": client.udp_port})

    if getattr(auth_win, 'role', None) == "ADMIN":
        gui = AdminGUI()
    else:
        gui = SpectatorGUI()

    client.gui = gui
    gui.server = client

    gui.set_car_ip(f"{client.protocol.host}:{client.protocol.port}")

    client.start()
    gui.mainloop()

if __name__ == "__main__":
    main()
