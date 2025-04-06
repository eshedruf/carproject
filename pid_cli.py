import cv2
import numpy as np
import time
from picamera2 import Picamera2
from car import MotorController

# PID Constants (tune these as needed)
Kp = 0.05      # Proportional gain (adjusted for normalized error)
Ki = 0.0010     # Integral gain
Kd = 0.03      # Derivative gain

# Initialize PID variables
previous_error = 0.0
integral = 0.0

def determine_freq(duty_cycle):
    # Updated thresholds: note that the comparisons are against duty cycles like 0.05, 0.075, etc.
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
    # Accumulate the error for the integral term
    integral += error
    # Compute the derivative (difference between current and previous error)
    derivative = error - previous_error
    # Calculate PID output
    output = Kp * error + Ki * integral + Kd * derivative
    previous_error = error
    return output

# Initialize Motor Controller
motor = MotorController()

# Initialize Picamera2
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 380)})
picam2.configure(config)
picam2.start()
time.sleep(2)

frame_rate = 15.0
frame_period = 1.0 / frame_rate

try:
    while True:
        start_time = time.time()
        # Capture frame and adjust color spaces
        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame = cv2.rotate(frame, cv2.ROTATE_180)

        # Convert to HSV and threshold for purple (the track color)
        imgHsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([125, 50, 50])
        upper = np.array([160, 255, 255])
        mask = cv2.inRange(imgHsv, lower, upper)

        # Get image dimensions
        h, w = mask.shape
        
        w_sub = 50
        h_sub = 120

        # Define perspective warp points (adjust these if needed)
        pts1 = np.float32([[w_sub, h -h_sub], [w - w_sub, h - h_sub], [0, h], [w, h]])
        pts2 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        matrix = cv2.getPerspectiveTransform(pts1, pts2)
        imgWarp = cv2.warpPerspective(mask, matrix, (w, h))

        # Compute the centroid of the white pixels using image moments
        M = cv2.moments(imgWarp)
        if M["m00"] != 0:
            centroid_x = int(M["m10"] / M["m00"])
        else:
            # If no white pixels are found, default the centroid to the center
            centroid_x = w // 2

        # Normalize error: error = (centroid - image center) normalized by half image width
        error = (centroid_x - (w / 2)) / (w / 2)
        pid_output = compute_pid(error)

        # Base duty cycle (tuned experimentally)
        base_duty = 0.07

        # Adjust wheel duty cycles using the PID output.
        # When error is positive (track to the right), we increase left wheel duty and decrease right wheel duty.
        left_duty = base_duty + pid_output
        right_duty = base_duty - pid_output

        # Calibration and clamping: keep duty cycles relative to base_duty.
        # For example, if base_duty is 0.07, then min_duty = 0.07 - 0.03 = 0.04 and max_duty = 0.07 + 0.03 = 0.10.
        right_calib = 0.65
        min_duty = base_duty - 0.03
        max_duty = base_duty + 0.025

        left_duty = max(min_duty, min(left_duty, max_duty))
        right_duty = max(min_duty, min(right_duty, max_duty)) * right_calib

        # For debugging, print out error, pid output, and individual duty cycles.
        print(f"Centroid: {centroid_x}, Error: {error:.2f}, PID output: {pid_output:.4f}, "
              f"Left Duty: {left_duty:.3f}, Right Duty: {right_duty:.3f}, "
              f"Duty Ratio (L/R): {(left_duty / right_duty):.3f}")

        # Determine motor frequencies based on the new duty cycles
        left_freq = determine_freq(left_duty)
        right_freq = determine_freq(right_duty)

        # Move the car forward with the new PID-controlled duty cycles
        motor.move_forward(left_duty=left_duty, right_duty=right_duty,
                           left_freq=left_freq, right_freq=right_freq)

        # Maintain the constant frame rate
        elapsed = time.time() - start_time
        if elapsed < frame_period:
            time.sleep(frame_period - elapsed)

except KeyboardInterrupt:
    print("Interrupted by user.")

finally:
    motor.stop()
    motor.cleanup()
    picam2.stop()
    picam2.close()
