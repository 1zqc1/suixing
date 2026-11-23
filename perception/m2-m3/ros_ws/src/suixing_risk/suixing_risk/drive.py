"""Chassis arbitration and feedback odometry, independent of ROS."""

from dataclasses import dataclass
from math import atan, cos, isfinite, pi, sin, tan

from .geometry import Pose, candidate_pose


def number(value):
    return type(value) in (float, int) and isfinite(value)


@dataclass(frozen=True)
class Feedback:
    stamp: int
    speed: float
    steering: float
    motion_permitted: bool
    estop: bool
    fault: bool
    brake_applied: bool


@dataclass(frozen=True)
class DifferentialFeedback:
    stamp: int
    left: float
    right: float
    motion_permitted: bool
    estop: bool
    fault: bool
    brake_applied: bool

    @property
    def speed(self):
        return (self.left + self.right) / 2


def parse_feedback(data, *, differential=False):
    stamp = data["stamp_ns"]
    flags = tuple(data[key] for key in ("motion_permitted", "estop_active", "fault", "brake_applied"))
    if type(stamp) is not int or not 0 < stamp < (1 << 63) or any(type(value) is not bool for value in flags):
        raise ValueError("invalid chassis feedback")
    if differential:
        left, right = (data[key] for key in ("left_wheel_mps", "right_wheel_mps"))
        if not all(number(value) and abs(value) <= 5.0 for value in (left, right)):
            raise ValueError("invalid differential wheel feedback")
        return DifferentialFeedback(stamp, left, right, *flags)
    speed, steering = (data[key] for key in ("speed_mps", "steering_rad"))
    if not number(speed) or abs(speed) > 5.0 or not number(steering) or abs(steering) >= pi / 2:
        raise ValueError("invalid chassis feedback")
    return Feedback(stamp, speed, steering, *flags)


class _DriveGate:
    def __init__(self, max_speed, timeout_ns):
        if not (0 < max_speed <= 0.30 and timeout_ns > 0):
            raise ValueError("invalid chassis speed or timeout")
        self.max_speed = max_speed
        self.timeout_ns = timeout_ns
        self.feedback = None
        self.received = 0
        self.armed = False
        self.estop = False
        self.arm_stamp = 0

    def update_feedback(self, feedback, now, steady):
        if feedback.fault or not feedback.motion_permitted:
            self.armed = False
        if feedback.estop:
            self.estop = True
            self.armed = False
        if not 0 <= now - feedback.stamp < self.timeout_ns:
            return False
        if self.feedback is not None and feedback.stamp <= self.feedback.stamp:
            return False
        self.feedback, self.received = feedback, steady
        return True

    def ready(self, now, steady):
        f = self.feedback
        return (f is not None and 0 <= now - f.stamp < self.timeout_ns
                and 0 <= steady - self.received < self.timeout_ns
                and f.motion_permitted and not f.estop and not f.fault)

    def arm(self, enabled, now, steady):
        self.armed = False
        if not enabled:
            return True
        if (not self.ready(now, steady) or not self.stationary(self.feedback)
                or not self.feedback.brake_applied):
            return False
        self.arm_stamp = now
        self.estop = False
        self.armed = True
        return True

    def stationary(self, feedback):
        return abs(feedback.speed) <= 0.02

    def output(self, now, steady, candidate, status):
        if not self.ready(now, steady):
            self.armed = False
        if not self.armed or self.estop:
            return 0.0, 0.0, True
        if candidate is None or status is None:
            return 0.0, 0.0, True
        stamp, speed, yaw_rate = candidate
        if (stamp != status[0] or stamp < self.arm_stamp or not stamp <= now < status[1]
                or now - stamp >= self.timeout_ns or not number(speed) or not number(yaw_rate)
                or not 0 < speed <= self.max_speed):
            return 0.0, 0.0, True
        return self.motion(speed, yaw_rate)


class DriveGate(_DriveGate):
    def __init__(self, wheelbase, max_speed, max_steering, timeout_ns):
        super().__init__(max_speed, timeout_ns)
        if not (0 < wheelbase <= 10 and 0 < max_steering < pi / 2):
            raise ValueError("invalid Ackermann calibration")
        self.wheelbase = wheelbase
        self.max_steering = max_steering

    def motion(self, speed, yaw_rate):
        steering = atan(self.wheelbase * yaw_rate / speed)
        if not abs(steering) <= self.max_steering:
            return 0.0, 0.0, True
        return speed, steering, False


class DifferentialDriveGate(_DriveGate):
    """Gate body velocity commands and output left/right linear wheel speeds."""

    def __init__(self, separation, max_speed, max_wheel_speed, timeout_ns):
        super().__init__(max_speed, timeout_ns)
        if not (0 < separation <= 10 and max_speed <= max_wheel_speed <= 5.0):
            raise ValueError("invalid differential calibration or wheel speed limit")
        self.separation = separation
        self.max_wheel_speed = max_wheel_speed

    def stationary(self, feedback):
        return max(abs(feedback.left), abs(feedback.right)) <= 0.02

    def motion(self, speed, yaw_rate):
        difference = yaw_rate * self.separation / 2
        left, right = speed - difference, speed + difference
        # M3 evaluates forward arcs only. Reject instead of changing the checked curvature.
        if not all(0 <= wheel <= self.max_wheel_speed for wheel in (left, right)):
            return 0.0, 0.0, True
        return left, right, False


class WheelOdometry:
    def __init__(self, wheelbase, max_gap_ns):
        if max_gap_ns <= 0:
            raise ValueError("odometry feedback gap must be positive")
        self.wheelbase = wheelbase
        self.max_gap_ns = max_gap_ns
        self.pose = Pose()
        self.previous = None

    def update(self, feedback):
        previous, self.previous = self.previous, feedback
        if previous is None:
            return self.pose
        elapsed = feedback.stamp - previous.stamp
        if not 0 < elapsed <= self.max_gap_ns:
            return None
        step = self.step(previous, feedback, elapsed / 1e9)
        yaw = (self.pose.yaw + step.yaw + pi) % (2 * pi) - pi
        self.pose = Pose(*self.pose.apply(step.x, step.y), yaw)
        return self.pose

    def step(self, previous, feedback, seconds):
        speed = (feedback.speed + previous.speed) / 2
        steering = (feedback.steering + previous.steering) / 2
        return candidate_pose(speed, tan(steering) / self.wheelbase, seconds)

    def yaw_rate(self, feedback):
        return feedback.speed * tan(feedback.steering) / self.wheelbase


class DifferentialWheelOdometry(WheelOdometry):
    def yaw_rate(self, feedback):
        return (feedback.right - feedback.left) / self.wheelbase

    def step(self, previous, feedback, seconds):
        distance = (previous.speed + feedback.speed) * seconds / 2
        yaw = (self.yaw_rate(previous) + self.yaw_rate(feedback)) * seconds / 2
        if abs(yaw) < 1e-6:
            return Pose(distance, distance * yaw / 2, yaw)
        return Pose(distance * sin(yaw) / yaw, distance * (1 - cos(yaw)) / yaw, yaw)
