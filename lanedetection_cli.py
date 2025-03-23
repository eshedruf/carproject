import cv2
import numpy as np
import time
from picamera2 import Picamera2
from car import MotorController

def determine_freq(duty_cycle):
    if duty_cycle < 0.05:
        return 30
    elif duty_cycle < 0.075:
        return 40
    else:
        return 45

# Initialize Motor Controller
motor = MotorController()

# Initialize Picamera2
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 380)})
picam2.configure(config)
picam2.start()
time.sleep(2)

frame_rate = 10.0
frame_period = 1.0 / frame_rate

try:
    while True:
        start_time = time.time()
        # Capture frame (convert from RGB to BGR)
        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame = cv2.rotate(frame, cv2.ROTATE_180)

        # HSV thresholding with preset values
        imgHsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([125, 50, 50])
        upper = np.array([160, 255, 255])
        mask = cv2.inRange(imgHsv, lower, upper)

        # Get dimensions from the mask (grayscale image)
        h, w = mask.shape

        # Define perspective warp source and destination points.
        # pts1: source points in the original image.
        # pts2: destination points in the warped image.
        pts1 = np.float32([[75, 244], [w - 75, 244], [0, h], [w, h]])
        pts2 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        matrix = cv2.getPerspectiveTransform(pts1, pts2)
        imgWarp = cv2.warpPerspective(mask, matrix, (w, h))

        # Compute white pixel ratio between left and right halves.
        left_half = imgWarp[:, :w//2]
        right_half = imgWarp[:, w//2:]
        left_white = cv2.countNonZero(left_half)
        right_white = cv2.countNonZero(right_half)
        ratio = right_white / (left_white + 1e-6)  # Avoid division by zero

        # Determine duty cycles based on the ratio.
        base_duty = 0.05
        error = ratio - 1.0  # positive if more white on right side.
        k = 0.04
        left_duty = base_duty + k * error
        right_duty = base_duty - k * error
        right_calib = 0.7
        left_duty = max(0.03, min(left_duty, 0.07))
        right_duty = max(0.03, min(right_duty, 0.07)) * right_calib

        print(f"pixels ratio: {ratio}, duty ratio: {(left_duty / right_duty):.3f}")

        left_freq = determine_freq(left_duty)
        right_freq = determine_freq(right_duty)
        motor.move_forward(left_duty=left_duty, right_duty=right_duty,
                           left_freq=left_freq, right_freq=right_freq)

        # Enforce constant frame rate.
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
    