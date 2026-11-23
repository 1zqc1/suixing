"""ROS-side chassis bridge with independent brake and motion permission inputs."""

import json
from math import cos, sin
from time import monotonic_ns

import rclpy
from geometry_msgs.msg import TransformStamped, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import SetBool
from tf2_ros import TransformBroadcaster

from .drive import DifferentialDriveGate, DifferentialWheelOdometry, DriveGate, WheelOdometry, parse_feedback


def stamp_ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


class ChassisNode(Node):
    def __init__(self):
        super().__init__("suixing_chassis")
        speed = self.declare_parameter("max_speed_mps", 0.25).value
        timeout = self.declare_parameter("watchdog_ms", 100).value * 1_000_000
        feedback_gap = self.declare_parameter("feedback_gap_ms", 100).value * 1_000_000
        mode = self.declare_parameter("drive_mode", "ackermann").value
        publish_odom = self.declare_parameter("publish_wheel_odom", True).value
        self.differential = mode == "differential"
        if self.differential:
            separation = self.declare_parameter("wheel_separation_m", 0.0).value
            wheel_speed = self.declare_parameter("max_wheel_speed_mps", 0.0).value
            self.gate = DifferentialDriveGate(separation, speed, wheel_speed, timeout)
            self.odometry = DifferentialWheelOdometry(separation, feedback_gap) if publish_odom else None
        elif mode == "ackermann":
            wheelbase = self.declare_parameter("wheelbase_m", 0.0).value
            steering = self.declare_parameter("max_steering_rad", 0.0).value
            self.gate = DriveGate(wheelbase, speed, steering, timeout)
            self.odometry = WheelOdometry(wheelbase, feedback_gap) if publish_odom else None
        else:
            raise ValueError("drive_mode must be ackermann or differential")
        self.candidate = self.status = self.active_pair = None
        self.stop_stamp = 0
        self.last_now = 0
        self.command = self.create_publisher(String, "/suixing/chassis/command", 1)
        self.odom = self.create_publisher(Odometry, "/odom", 5) if self.odometry else None
        self.tf = TransformBroadcaster(self) if self.odometry else None
        self.create_subscription(TwistStamped, "/suixing/cmd_vel_candidate", self.receive_candidate, 1)
        self.create_subscription(String, "/suixing/navigation_status", self.receive_status, 1)
        self.create_subscription(String, "/suixing/chassis/feedback", self.receive_feedback, 5)
        self.create_service(SetBool, "/suixing/chassis/arm", self.arm)
        self.timer = self.create_timer(0.005, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def stop_candidate(self, stamp):
        self.active_pair = None
        self.stop_stamp = max(self.stop_stamp, stamp)

    def pair_command(self):
        if (self.candidate is not None and self.status is not None
                and self.candidate[0] == self.status[0] and self.candidate[0] > self.stop_stamp):
            self.active_pair = self.candidate, self.status

    def receive_candidate(self, message):
        stamp = stamp_ns(message.header.stamp)
        speed = message.twist.linear.x
        if message.header.frame_id != "base_link" or not speed > 0:
            self.candidate = None
            self.stop_candidate(stamp)
        elif self.candidate is None or stamp >= self.candidate[0]:
            self.candidate = stamp, speed, message.twist.angular.z
            self.pair_command()

    def receive_status(self, message):
        try:
            data = json.loads(message.data)
            stamp, expires = data["stamp_ns"], data["valid_until_ns"]
            if type(stamp) is not int or type(expires) is not int:
                raise ValueError("invalid candidate deadline")
            remaining = expires - self.get_clock().now().nanoseconds
            if remaining <= 0:
                self.stop_candidate(stamp)
            elif self.status is None or stamp >= self.status[0]:
                self.status = stamp, expires, monotonic_ns() + min(remaining, self.gate.timeout_ns)
                self.pair_command()
        except (ValueError, TypeError, KeyError):
            self.status = None
            self.stop_candidate(self.get_clock().now().nanoseconds)

    def receive_feedback(self, message):
        try:
            f = parse_feedback(json.loads(message.data), differential=self.differential)
        except (ValueError, TypeError, KeyError, OverflowError):
            self.gate.feedback = None
            self.gate.armed = False
            self.tick()
            return
        if self.gate.update_feedback(f, self.get_clock().now().nanoseconds, monotonic_ns()):
            if self.odometry is not None:
                pose = self.odometry.update(f)
                if pose is not None:
                    self.publish_odometry(f, pose)
                else:
                    self.gate.armed = False
        if f.estop or f.fault or not f.motion_permitted:
            self.tick()

    def publish_odometry(self, feedback, pose):
        msg = Odometry()
        msg.header.frame_id = "odom"
        msg.header.stamp = Time(nanoseconds=feedback.stamp).to_msg()
        msg.child_frame_id = "base_link"
        msg.pose.pose.position.x, msg.pose.pose.position.y = pose.x, pose.y
        msg.pose.pose.orientation.z = sin(pose.yaw / 2)
        msg.pose.pose.orientation.w = cos(pose.yaw / 2)
        msg.twist.twist.linear.x = feedback.speed
        msg.twist.twist.angular.z = self.odometry.yaw_rate(feedback)
        # Wheel-only odometry: mark unobserved axes and retain nonzero planar uncertainty.
        for index, value in enumerate((0.05, 0.05, 1e6, 1e6, 1e6, 0.10)):
            msg.pose.covariance[index * 7] = value
            msg.twist.covariance[index * 7] = value
        self.odom.publish(msg)
        transform = TransformStamped(header=msg.header, child_frame_id=msg.child_frame_id)
        transform.transform.translation.x, transform.transform.translation.y = pose.x, pose.y
        transform.transform.rotation = msg.pose.pose.orientation
        self.tf.sendTransform(transform)

    def arm(self, request, response):
        self.candidate = self.status = self.active_pair = None
        response.success = self.gate.arm(request.data, self.get_clock().now().nanoseconds, monotonic_ns())
        response.message = "Armed" if response.success and request.data else (
            "Disarmed" if response.success else "Fresh, stationary, permitted chassis with brake applied required")
        self.tick()
        return response

    def tick(self):
        now = self.get_clock().now().nanoseconds
        if now < self.last_now:
            self.gate.armed = False
            self.gate.feedback = None
            self.candidate = self.status = self.active_pair = None
            self.stop_stamp = 0
            if self.odometry is not None:
                self.odometry.previous = None
        self.last_now = now
        steady = monotonic_ns()
        candidate, status = self.active_pair or (None, None)
        if status is not None and steady >= status[2]:
            self.active_pair = None
            candidate = status = None
        first, second, brake = self.gate.output(now, steady, candidate, status)
        fields = ({"left_wheel_mps": first, "right_wheel_mps": second} if self.differential else
                  {"speed_mps": first, "steering_rad": second})
        self.command.publish(String(data=json.dumps({
            "stamp_ns": now, "valid_until_ns": 0 if brake else status[1],
            **fields, "brake": brake,
        }, allow_nan=False)))


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ChassisNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            if rclpy.ok():
                node.gate.armed = False
                node.tick()
            node.destroy_node()
        rclpy.try_shutdown()
