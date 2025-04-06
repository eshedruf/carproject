import socket, struct, json, threading
import numpy as np, cv2
from image_utils import ImgUtils
from pid_controller import PID
from gui import GUI

class Server(threading.Thread):
    """Server thread that receives images, processes them, and updates the GUI."""
    
    def __init__(self, gui):
        super().__init__(daemon=True)
        self.gui = gui
        self.sock = socket.socket()
        self.sock.bind(('', 8000))
        self.sock.listen(5)
        self.pid = PID()
    
    def run(self):
        conn, addr = self.sock.accept()
        self.gui.set_car_ip(addr[0])
        print(f"Connected by {addr}")
        while True:
            head = self._recvall(conn, 4)
            if not head: break
            h_len = struct.unpack("!I", head)[0]
            hdr = json.loads(self._recvall(conn, h_len).decode())
            d_len = struct.unpack("!I", self._recvall(conn, 4))[0]
            data = self._recvall(conn, d_len)
            if data is None:
                break
            frame = np.frombuffer(data, dtype=np.dtype(hdr["dtype"])).reshape(hdr["shape"])
            
            mask = ImgUtils.threshold(frame)
            warped = ImgUtils.warp(mask)
            result = self.pid.process(warped)
            # Unpack all PID values
            error, pid_out, left, right, lf, rf, derivative, integral, prev_error = result
            
            # If stop flag is active, force outputs to 0
            if self.gui.control_flags.get("stopped", False):
                left = right = 0.0
                lf = rf = 0
            
            # Send response with keys matching pi_client.py expectations
            resp = json.dumps({
                "left_duty": left,
                "right_duty": right,
                "left_freq": lf,
                "right_freq": rf
            }) + "\n"
            conn.sendall(resp.encode())
            
            # Prepare the four images for the GUI
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            warped_bgr = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
            pid_img = self.gui.pid_graph.update(error, pid_out)
            
            # Create debug info string
            info = (
                f"Centroid Err: {error:.2f} | PID: {pid_out:.4f}\n"
                f"Integral: {integral:.4f} | Deriv: {derivative:.4f} | Prev Err: {prev_error:.4f}\n"
                f"Left Duty: {left:.3f}, Right Duty: {right:.3f} | "
                f"Left Freq: {lf}, Right Freq: {rf}"
            )
            
            # Update GUI with the four individual images
            self.gui.update_gui(frame, mask_bgr, warped_bgr, pid_img, info)
        conn.close()
    
    def _recvall(self, conn, count):
        buf = b""
        while count:
            new = conn.recv(count)
            if not new:
                return None
            buf += new
            count -= len(new)
        return buf

def main():
    gui = GUI()
    server = Server(gui)
    gui.server = server  # For PID reset access
    server.start()
    gui.mainloop()

if __name__ == "__main__":
    main()