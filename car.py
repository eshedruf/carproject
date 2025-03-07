import RPi.GPIO as GPIO
import time
import threading

# ---------------------------
# Pin definitions (renamed)
# ---------------------------
ena = 23  # PWM output for right motor
in1 = 5   # Motor driver control pin
in2 = 6   # Motor driver control pin
in3 = 17  # Motor driver control pin
in4 = 27  # Motor driver control pin
enb = 24  # PWM output for left motor

# ---------------------------
# GPIO Setup
# ---------------------------
GPIO.setmode(GPIO.BCM)
for pin in (ena, in1, in2, in3, in4, enb):
    GPIO.setup(pin, GPIO.OUT)

# ---------------------------
# Software PWM Class
# ---------------------------
class SoftwarePWM(threading.Thread):
    """
    A simple software PWM implementation that runs in its own thread.
    You can update both the duty cycle and the frequency on the fly.
    """
    def __init__(self, pin, frequency=100, duty_cycle=0):
        """
        :param pin: GPIO pin number (BCM numbering)
        :param frequency: Frequency in Hz
        :param duty_cycle: Initial duty cycle (0 to 100 percent)
        """
        super().__init__()
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = duty_cycle  # in percent
        self._stop_event = threading.Event()
        self.daemon = True  # Ensure thread exits when main program exits

        # Start with the pin low
        GPIO.output(self.pin, GPIO.LOW)

    def run(self):
        while not self._stop_event.is_set():
            period = 1.0 / self.frequency  # Total period for one PWM cycle
            on_time = period * (self.duty_cycle / 100.0)
            off_time = period - on_time

            if on_time > 0:
                GPIO.output(self.pin, GPIO.HIGH)
                time.sleep(on_time)
            if off_time > 0:
                GPIO.output(self.pin, GPIO.LOW)
                time.sleep(off_time)

    def change_duty_cycle(self, duty_cycle):
        """Update the duty cycle (0 to 100 percent)."""
        self.duty_cycle = duty_cycle

    def change_frequency(self, frequency):
        """Update the PWM frequency in Hz."""
        self.frequency = frequency

    def stop(self):
        """Signal the thread to stop and turn off the pin."""
        self._stop_event.set()
        GPIO.output(self.pin, GPIO.LOW)

# ---------------------------
# Initialize PWM threads for ena and enb
# ---------------------------
DEFAULT_FREQUENCY = 100  # Default frequency in Hz (can be overridden)
ena_pwm = SoftwarePWM(ena, frequency=DEFAULT_FREQUENCY, duty_cycle=0)
enb_pwm = SoftwarePWM(enb, frequency=DEFAULT_FREQUENCY, duty_cycle=0)
ena_pwm.start()
enb_pwm.start()

# ---------------------------
# Motor Control Functions (using duty_cycle and frequency)
# ---------------------------
def move_forward(duty_cycle=0, frequency=100):
    """
    Move forward.
    
    :param duty_cycle: Fraction (0 to 1) representing duty cycle (e.g., 0.1 for 10%)
    :param frequency: PWM frequency in Hz
    """
    GPIO.output(in1, GPIO.HIGH)
    GPIO.output(in2, GPIO.LOW)
    GPIO.output(in3, GPIO.LOW)
    GPIO.output(in4, GPIO.HIGH)
    
    duty = duty_cycle * 100  # Convert fraction to percent
    ena_pwm.change_duty_cycle(duty)
    enb_pwm.change_duty_cycle(duty)
    ena_pwm.change_frequency(frequency)
    enb_pwm.change_frequency(frequency)

def move_backward(duty_cycle=0, frequency=100):
    """
    Move backward.
    
    :param duty_cycle: Fraction (0 to 1) representing duty cycle
    :param frequency: PWM frequency in Hz
    """
    GPIO.output(in1, GPIO.LOW)
    GPIO.output(in2, GPIO.HIGH)
    GPIO.output(in3, GPIO.HIGH)
    GPIO.output(in4, GPIO.LOW)
    
    duty = duty_cycle * 100
    ena_pwm.change_duty_cycle(duty)
    enb_pwm.change_duty_cycle(duty)
    ena_pwm.change_frequency(frequency)
    enb_pwm.change_frequency(frequency)

def turn_left(duty_cycle=0, frequency=100):
    """
    Turn left by driving only the right wheel.
    
    :param duty_cycle: Fraction (0 to 1) representing duty cycle for the right wheel
    :param frequency: PWM frequency in Hz
    """
    GPIO.output(in1, GPIO.HIGH)
    GPIO.output(in2, GPIO.LOW)
    # Left wheel stopped
    GPIO.output(in3, GPIO.LOW)
    GPIO.output(in4, GPIO.LOW)
    
    ena_pwm.change_duty_cycle(duty_cycle * 100)
    enb_pwm.change_duty_cycle(0)
    ena_pwm.change_frequency(frequency)
    enb_pwm.change_frequency(frequency)

def turn_right(duty_cycle=0, frequency=100):
    """
    Turn right by driving only the left wheel.
    
    :param duty_cycle: Fraction (0 to 1) representing duty cycle for the left wheel
    :param frequency: PWM frequency in Hz
    """
    GPIO.output(in1, GPIO.LOW)
    GPIO.output(in2, GPIO.LOW)
    # Right wheel stopped
    GPIO.output(in3, GPIO.LOW)
    GPIO.output(in4, GPIO.HIGH)
    
    ena_pwm.change_duty_cycle(0)
    enb_pwm.change_duty_cycle(duty_cycle * 100)
    ena_pwm.change_frequency(frequency)
    enb_pwm.change_frequency(frequency)

def stop():
    """Stop all movement."""
    ena_pwm.change_duty_cycle(0)
    enb_pwm.change_duty_cycle(0)
    # Optionally, turn off the direction pins:
    for pin in (in1, in2, in3, in4):
        GPIO.output(pin, GPIO.LOW)

# ---------------------------
# Testing: Run both wheels at 10% duty cycle and 1Hz frequency
# ---------------------------
try:
    print("moving forward")
    move_forward(duty_cycle=0.15, frequency=100)
    time.sleep(5)  # Let it run for 5 seconds
    print("moving backward")
    move_backward(duty_cycle=0.15, frequency=100)
    time.sleep(5)
    print("turn right, only left wheel moving")
    turn_right(duty_cycle=0.15, frequency=100)
    time.sleep(5)
    print("turn left, only right wheel moving")
    turn_left(duty_cycle=0.15, frequency=100)
    time.sleep(5)
    stop()
    
finally:
    # Stop PWM threads and clean up GPIO
    ena_pwm.stop()
    enb_pwm.stop()
    GPIO.cleanup()
