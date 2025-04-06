import cv2
import numpy as np
import time
import socket
import struct
import json

# --- PID Constants ---
Kp = 0.05      # Proportional gain
Ki = 0.0008    # Integral gain
Kd = 0.03     # Derivative gain

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

# --- PID Graph Setup ---
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

def color_half_with_more_white(img):
    """
    Colors the white pixels in the half (left or right) that has more white pixels
    to light green (BGR: [144, 238, 144]). Only white pixels (255,255,255) are recolored.
    """
    h, w, _ = img.shape
    half = w // 2
    # Count white pixels (all channels equal 255) in each half
    left_white = np.sum(np.all(img[:, :half] == [255, 255, 255], axis=-1))
    right_white = np.sum(np.all(img[:, half:] == [255, 255, 255], axis=-1))
    
    if left_white >= right_white:
        col_range = slice(0, half)
    else:
        col_range = slice(half, w)
    
    # Get the selected half region
    img_half = img[:, col_range]
    # Create mask for white pixels in the selected half
    white_mask = np.all(img_half == [255, 255, 255], axis=-1)
    # Set white pixels to light green (BGR)
    img_half[white_mask] = [50, 232, 0]
    # Put the modified half back
    img[:, col_range] = img_half
    return img

# --- Network Server Configuration ---
HOST = ''        # Listen on all interfaces
PORT = 8000      # Must match the port in the client

server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.bind((HOST, PORT))
server_sock.listen(1)
print(f"Server listening on port {PORT}...")

while True:
    print("Waiting for a client to connect...")
    conn, addr = server_sock.accept()
    print(f"Connected by {addr}")
    try:
        while True:
            # ----- Receive Header -----
            raw_header_len = b""
            while len(raw_header_len) < 4:
                more = conn.recv(4 - len(raw_header_len))
                if not more:
                    raise ConnectionError("Socket connection broken or client disconnected")
                raw_header_len += more
            header_len = struct.unpack("!I", raw_header_len)[0]
            header_bytes = b""
            while len(header_bytes) < header_len:
                more = conn.recv(header_len - len(header_bytes))
                if not more:
                    raise ConnectionError("Socket connection broken or client disconnected")
                header_bytes += more
            header = json.loads(header_bytes.decode("utf-8"))
            # Header info printing removed

            # ----- Receive Raw Image Data -----
            raw_data_len_bytes = b""
            while len(raw_data_len_bytes) < 4:
                more = conn.recv(4 - len(raw_data_len_bytes))
                if not more:
                    raise ConnectionError("Socket connection broken or client disconnected")
                raw_data_len_bytes += more
            raw_data_len = struct.unpack("!I", raw_data_len_bytes)[0]
            data = b""
            while len(data) < raw_data_len:
                more = conn.recv(raw_data_len - len(data))
                if not more:
                    raise ConnectionError("Socket connection broken or client disconnected")
                data += more
            
            try:
                frame = np.frombuffer(data, dtype=np.dtype(header["dtype"]))
                frame = frame.reshape(header["shape"])
            except Exception as e:
                print("Error reconstructing image:", e)
                continue
            
            if frame is None or frame.size == 0:
                print("Failed to reconstruct image")
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
            if M["m00"] != 0:
                centroid_x = int(M["m10"] / M["m00"])
            else:
                centroid_x = w // 2
            
            error = (centroid_x - (w / 2)) / (w / 2)
            pid_output = compute_pid(error)
            base_duty = 0.07
            left_duty = base_duty + pid_output
            right_duty = base_duty - pid_output
            
            right_calib = 0.65
            min_duty = base_duty - 0.03
            max_duty = base_duty + 0.025
            left_duty = max(min_duty, min(left_duty, max_duty))
            right_duty = max(min_duty, min(right_duty, max_duty)) * right_calib
            
            left_freq = determine_freq(left_duty)
            right_freq = determine_freq(right_duty)
            
            # Only print the key processing info
            print(f"Centroid: {centroid_x}, Error: {error:.2f}, PID output: {pid_output:.4f}, "
                  f"Left Duty: {left_duty:.3f}, Right Duty: {right_duty:.3f}, "
                  f"Left Freq: {left_freq}, Right Freq: {right_freq}")
            
            pwm_info = {
                "left_duty": left_duty,
                "right_duty": right_duty,
                "left_freq": left_freq,
                "right_freq": right_freq
            }
            response = json.dumps(pwm_info) + "\n"
            conn.sendall(response.encode("utf-8"))
            
            # --- Visualization ---
            # Convert mask and warped image to BGR for visualization.
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            warp_bgr = cv2.cvtColor(imgWarp, cv2.COLOR_GRAY2BGR)
            # Color the half with more white pixels in light green
            mask_bgr = color_half_with_more_white(mask_bgr)
            warp_bgr = color_half_with_more_white(warp_bgr)
            
            combined = cv2.hconcat([frame, mask_bgr, warp_bgr])
            cv2.imshow("Processed Views", combined)
            pid_graph = update_pid_graph(error, pid_output)
            cv2.imshow("PID Graph", pid_graph)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                raise KeyboardInterrupt
    except ConnectionError as e:
        print("Client disconnected:", e)
    except KeyboardInterrupt:
        print("Server interrupted by user.")
        break
    finally:
        conn.close()

server_sock.close()
cv2.destroyAllWindows()
