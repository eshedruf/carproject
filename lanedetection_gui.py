import cv2
import numpy as np
import time
from picamera2 import Picamera2
import utils
from car import MotorController

def empty(a):
    pass

def determine_freq(duty_cycle):
    if duty_cycle < 0.05:
        return 30
    elif duty_cycle < 0.075:
        return 40
    else:
        return 45

# ----------------------------
# Initialize HSV Color Picker Trackbars
# ----------------------------
cv2.namedWindow("HSV")
cv2.resizeWindow("HSV", 640, 240)
cv2.createTrackbar("HUE Min", "HSV", 125, 179, empty)
cv2.createTrackbar("HUE Max", "HSV", 160, 179, empty)
cv2.createTrackbar("SAT Min", "HSV", 50, 255, empty)
cv2.createTrackbar("SAT Max", "HSV", 255, 255, empty)
cv2.createTrackbar("VALUE Min", "HSV", 50, 255, empty)
cv2.createTrackbar("VALUE Max", "HSV", 255, 255, empty)

# ----------------------------
# Initialize Perspective Warp Trackbars (from utils)
# ----------------------------
initialTrackBars = [75, 244, 0, 380]
utils.initializeTrackbars(initialTrackBars, wT=640, hT=380)

# ----------------------------
# Initialize Motor Controller
# ----------------------------
motor = MotorController()

# ----------------------------
# Initialize Picamera2
# ----------------------------
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 380)})
picam2.configure(config)
picam2.start()
time.sleep(2)

# ----------------------------
# Set desired frame rate: n = 5 FPS.
# ----------------------------
frame_rate = 10.0
frame_period = 1.0 / frame_rate

try:
    while True:
        start_time = time.time()
        # Capture a frame from Picamera2 (RGB -> BGR conversion required)
        frame = picam2.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Rotate the frame 180 degrees
        frame = cv2.rotate(frame, cv2.ROTATE_180)

        # -------------------------------------------
        # HSV Thresholding using trackbar values.
        # -------------------------------------------
        imgHsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h_min = cv2.getTrackbarPos("HUE Min", "HSV")
        h_max = cv2.getTrackbarPos("HUE Max", "HSV")
        s_min = cv2.getTrackbarPos("SAT Min", "HSV")
        s_max = cv2.getTrackbarPos("SAT Max", "HSV")
        v_min = cv2.getTrackbarPos("VALUE Min", "HSV")
        v_max = cv2.getTrackbarPos("VALUE Max", "HSV")
        lower = np.array([h_min, s_min, v_min])
        upper = np.array([h_max, s_max, v_max])
        mask = cv2.inRange(imgHsv, lower, upper)
        #cv2.imshow("Threshold", mask)

        # -------------------------------------------
        # Perspective Warp (optional)
        # -------------------------------------------
        h, w, _ = frame.shape
        points = utils.valTrackbars(wT=w, hT=h)
        imgWarp = utils.warpImg(mask, points, w, h)
        cv2.imshow("Warp", imgWarp)

        # -------------------------------------------
        # Compute white pixel ratio between right and left halves using the warped image.
        # -------------------------------------------
        left_half = imgWarp[:, :w//2]
        right_half = imgWarp[:, w//2:]
        left_white = cv2.countNonZero(left_half)
        right_white = cv2.countNonZero(right_half)
        ratio = right_white / (left_white + 1e-6)  # Avoid division by zero

        # -------------------------------------------
        # Determine individual duty cycles for left and right wheels.
        # -------------------------------------------
        # Base duty cycle (when ratio is 1:1)
        base_duty = 0.05
        # Calculate error relative to a perfect balance.
        error = ratio - 1.0  # Positive if more pixels on right, negative if more on left.
        # Scaling factor to control sensitivity.
        k = 0.04
        # Adjust the duty cycles: if error > 0, increase left duty and decrease right duty.
        left_duty = base_duty + k * error
        right_duty = base_duty - k * error

        right_calib = 0.7

        # Clamp the duty cycles within the allowed range (0.07 to 0.11).
        left_duty = max(0.03, min(left_duty, 0.07))
        right_duty = max(0.03, min(right_duty, 0.07)) * right_calib

        print(f"pixels ratio: {ratio}, duty ratio: {(left_duty / right_duty):.3f}")

        # -------------------------------------------
        # Determine PWM frequency based on the maximum duty cycle.
        # -------------------------------------------
        
        left_freq = determine_freq(left_duty)
        right_freq = determine_freq(right_duty)

        # -------------------------------------------
        # Command the car: move forward using individual wheel duty cycles.
        # -------------------------------------------
        # This assumes the MotorController.move_forward method has been adapted to accept
        # left_duty and right_duty parameters separately.
        motor.move_forward(left_duty=left_duty, right_duty=right_duty, left_freq=left_freq, right_freq=right_freq)

        # Show the original video feed.
        #cv2.imshow("Video", frame)

        # Check for exit key.
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Enforce a constant frame rate of 5 FPS.
        elapsed = time.time() - start_time
        if elapsed < frame_period:
            time.sleep(frame_period - elapsed)

except KeyboardInterrupt:
    print("Interrupted by user.")

finally:
    motor.stop()
    motor.cleanup()
    cv2.destroyAllWindows()
    picam2.stop()
    picam2.close()
    