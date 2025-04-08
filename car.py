import RPi.GPIO as GPIO
import time
import threading

class MotorController:
    """
    Motor controller that encapsulates pin definitions, PWM threads,
    and motor control functions.
    """
    class SoftwarePWM(threading.Thread):
        def __init__(self, pin, frequency=100, duty_cycle=0):
            super().__init__()
            self.pin = pin
            self.frequency = frequency
            self.duty_cycle = duty_cycle  # in percent
            self._stop_event = threading.Event()
            self.daemon = True  # Ensure thread exits when main program exits
            GPIO.output(self.pin, GPIO.LOW)

        def run(self):
            while not self._stop_event.is_set():
                period = 1.0 / self.frequency
                on_time = period * (self.duty_cycle / 100.0)
                off_time = period - on_time
                if on_time > 0:
                    GPIO.output(self.pin, GPIO.HIGH)
                    time.sleep(on_time)
                if off_time > 0:
                    GPIO.output(self.pin, GPIO.LOW)
                    time.sleep(off_time)

        def change_duty_cycle(self, duty_cycle):
            self.duty_cycle = duty_cycle

        def change_frequency(self, frequency):
            self.frequency = frequency

        def stop(self):
            self._stop_event.set()
            GPIO.output(self.pin, GPIO.LOW)

    def __init__(self, ena=23, in1=5, in2=6, in3=17, in4=27, enb=24, default_frequency=100):
        """
        Initialize the motor controller.
        """
        self.ena = ena   # Right motor PWM pin
        self.in1 = in1   # Right motor control
        self.in2 = in2
        self.in3 = in3   # Left motor control
        self.in4 = in4
        self.enb = enb   # Left motor PWM pin
        self.default_frequency = default_frequency

        GPIO.setmode(GPIO.BCM)
        for pin in (self.ena, self.in1, self.in2, self.in3, self.in4, self.enb):
            GPIO.setup(pin, GPIO.OUT)

        self.ena_pwm = self.SoftwarePWM(self.ena, frequency=self.default_frequency, duty_cycle=0)
        self.enb_pwm = self.SoftwarePWM(self.enb, frequency=self.default_frequency, duty_cycle=0)
        self.ena_pwm.start()
        self.enb_pwm.start()

    def move_forward(self, left_duty, right_duty, left_freq=None, right_freq=None):
        """
        Move forward using the provided left and right duty cycles.
        The left_duty and right_duty parameters are fractions (e.g. 0.05 means 5%).
        """
        if left_freq is None:
            left_freq = self.default_frequency
        if right_freq is None:
            right_freq = self.default_frequency
        

        # Set the direction for forward motion.
        GPIO.output(self.in1, GPIO.HIGH)
        GPIO.output(self.in2, GPIO.LOW)
        GPIO.output(self.in3, GPIO.LOW)
        GPIO.output(self.in4, GPIO.HIGH)

        # Convert duty cycle fractions to percentages.
        left_percent = left_duty * 100
        right_percent = right_duty * 100

        self.ena_pwm.change_duty_cycle(right_percent)  # Right motor PWM (typically the stronger motor)
        self.enb_pwm.change_duty_cycle(left_percent)   # Left motor PWM
        self.ena_pwm.change_frequency(right_freq)      # Right motor frequency
        self.enb_pwm.change_frequency(left_freq)       # Left motor frequency


    def move_backward(self, left_duty, right_duty, left_freq=None, right_freq=None):
        """
        Move backward using the provided left and right duty cycles.
        The left_duty and right_duty parameters are fractions (e.g. 0.05 means 5%).
        """
        if left_freq is None:
            left_freq = self.default_frequency
        if right_freq is None:
            right_freq = self.default_frequency

        # Set the direction for backward motion (reverse of forward).
        GPIO.output(self.in1, GPIO.LOW)
        GPIO.output(self.in2, GPIO.HIGH)
        GPIO.output(self.in3, GPIO.HIGH)
        GPIO.output(self.in4, GPIO.LOW)

        # Convert duty cycle fractions to percentages.
        left_percent = left_duty * 100
        right_percent = right_duty * 100

        self.ena_pwm.change_duty_cycle(right_percent)  # Right motor PWM (typically the stronger motor)
        self.enb_pwm.change_duty_cycle(left_percent)   # Left motor PWM
        self.ena_pwm.change_frequency(right_freq)      # Right motor frequency
        self.enb_pwm.change_frequency(left_freq)       # Left motor frequency

    def stop(self):
        self.ena_pwm.change_duty_cycle(0)
        self.enb_pwm.change_duty_cycle(0)
        for pin in (self.in1, self.in2, self.in3, self.in4):
            GPIO.output(pin, GPIO.LOW)

    def cleanup(self):
        self.ena_pwm.stop()
        self.enb_pwm.stop()
        GPIO.cleanup()


