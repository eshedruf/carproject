# pid_controller.py
import cv2

class PID:
    """PID controller for computing error, output, and debug data."""
    Kp = 0.05
    Ki = 0.0010
    Kd = 0.03
    
    def __init__(self):
        self.prev_error = 0.0
        self.integral = 0.0
    
    def compute(self, error):
        """
        Compute PID output along with derivative and current integral.
        Returns (pid_output, derivative, integral, prev_error_before_update).
        """
        derivative = error - self.prev_error
        self.integral += error
        output = self.Kp * error + self.Ki * self.integral + self.Kd * derivative
        prev = self.prev_error
        self.prev_error = error
        return output, derivative, self.integral, prev
    
    def process(self, warped):
        """
        Process warped image to compute centroid, error, PID output,
        motor duty cycles, frequencies, and debug data.
        Returns:
          error, pid_output, left, right, lf, rf, derivative, integral, prev_error.
        """
        h, w = warped.shape
        M = cv2.moments(warped)
        cx = int(M["m10"] / M["m00"]) if M["m00"] != 0 else w // 2
        error = (cx - w / 2) / (w / 2)
        pid_output, derivative, integral, prev_error = self.compute(error)
        base = 0.07
        left = base + pid_output
        right = base - pid_output
        min_duty = base - 0.03
        max_duty = base + 0.02
        left = max(min_duty, min(left, max_duty))
        right = max(min_duty, min(right, max_duty)) * 0.65
        lf = self.determine_freq(left)
        rf = self.determine_freq(right)
        return error, pid_output, left, right, lf, rf, derivative, integral, prev_error
    
    @staticmethod
    def determine_freq(duty):
        """Determine PWM frequency from duty cycle."""
        if duty < 0.05:
            return 20
        elif duty < 0.075:
            return 30
        elif duty < 0.09:
            return 45
        elif duty < 0.11:
            return 65
        elif duty < 0.15:
            return 80
        else:
            return 50
    
    def reset(self):
        """Reset PID state."""
        self.prev_error = 0.0
        self.integral = 0.0
