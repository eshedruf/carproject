import threading
import time
import numpy as np
import cv2
import socket
from image_utils import ImgUtils
from pid_controller import PID
from admin_gui import GUI as AdminGUI
from spec_gui import SpectatorGUI
from auth_window import AuthWindow
from protocol import Protocol

class Client(threading.Thread):
    def __init__(self, server_ip, server_port):
        super().__init__(daemon=True)
        self.protocol = Protocol('client', server_ip, server_port)
        self.gui = None
        self.pid = PID()
        self.running = False
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('', 0))
        self.udp_port = self.udp_socket.getsockname()[1]
        # prevent blocking forever
        self.udp_socket.settimeout(0.2)

    def connect(self):
        while True:
            try:
                self.protocol.connect()
                print(f"Connected to server {self.protocol.host}:{self.protocol.port}")
                break
            except (ConnectionRefusedError, socket.timeout):
                print("Connection failed. Trying again in 2 seconds...")
                time.sleep(2)

    def send_message(self, msg: dict):
        self.protocol.send_json(msg)

    def recv_message(self) -> dict:
        return self.protocol.recv_json()

    def run(self):
        self.running = True
        frame_count = 0
        while self.running:
            try:
                # Receive frame
                t0 = time.time()
                data, _ = self.udp_socket.recvfrom(65535)
                t1 = time.time()
                print(f"[DEBUG] Frame {frame_count}: UDP recv in {t1 - t0:.3f}s")

                # Decode
                buf = np.frombuffer(data, np.uint8)
                frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if frame is None or frame.size == 0:
                    print(f"[WARNING] Empty frame at {frame_count}")
                    frame_count += 1
                    continue

                # If admin, process; else show only frame
                if getattr(self.gui, 'is_admin', False):
                    try:
                        mask = ImgUtils.threshold(frame)
                        if mask is None or mask.size == 0:
                            raise ValueError("Mask is empty")
                        warped = ImgUtils.warp(mask)
                        if warped is None or warped.size == 0:
                            raise ValueError("Warped image is empty")

                        # PID
                        (error, pid_out,
                         left, right,
                         lf, rf,
                         derivative, integral, prev_error) = self.pid.process(warped)

                        # stopped flag
                        if self.gui.control_flags.get("stopped", False):
                            left = right = 0.0
                            lf = rf = 0

                        # send PWM
                        pwm = {
                            "type": self.protocol.CMDS['PWM'],
                            "left_duty": left,
                            "right_duty": right,
                            "left_freq": lf,
                            "right_freq": rf
                        }
                        self.protocol.send_json(pwm)

                        # build visuals
                        mask_bgr   = cv2.cvtColor(mask,   cv2.COLOR_GRAY2BGR)
                        warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
                        pid_img    = self.gui.pid_graph.update(error, pid_out)

                        info = (
                            f"Err: {error:.2f} | PID: {pid_out:.4f}\n"
                            f"I: {integral:.4f}  D: {derivative:.4f}\n"
                            f"Ld:{left:.3f}  Rd:{right:.3f} | Lf:{lf}  Rf:{rf}"
                        )

                        self.gui.update_gui(frame, mask_bgr, warped_bgr, pid_img, info)
                    except Exception as e:
                        print(f"[ERROR] Frame {frame_count} processing failed: {e}")
                        # still update GUI with raw frame and error
                        self.gui.update_gui(frame, None, None, None, f"Error: {e}")
                else:
                    # Spectator mode
                    self.gui.update_gui(frame, None, None, None, "Spectator mode")

                frame_count += 1

            except socket.timeout:
                continue
            except Exception as e:
                print(f"[ERROR] Client exception at frame {frame_count}: {e}")
                break

        self.protocol.close()
        print("[INFO] Client thread exited")


def main():
    client = Client("raspitwo.local", 8000)
    client.connect()

    auth_win = AuthWindow(client)
    auth_win.mainloop()

    if not auth_win.authenticated:
        print("Authentication failed or cancelled")
        return

    client.protocol.send_json({"type": "UDP_PORT", "port": client.udp_port})

    # assign GUI and role
    if getattr(auth_win, 'role', None) == "ADMIN":
        gui = AdminGUI()
        gui.is_admin = True
    else:
        gui = SpectatorGUI()
        gui.is_admin = False

    client.gui = gui
    gui.server = client
    gui.set_car_ip(f"{client.protocol.host}:{client.protocol.port}")

    client.start()
    gui.mainloop()

if __name__ == "__main__":
    main()