"""Validate calibrated stereo input and publish a common capture timestamp."""

from copy import copy
from math import isfinite

import rclpy
from geometry_msgs.msg import TransformStamped
from message_filters import ApproximateTimeSynchronizer, Subscriber
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.parameter import Parameter
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import StaticTransformBroadcaster

from .perception import stereo_intrinsics


def capture_stamp(messages, now, skew_ns, max_age_ns):
    stamps = [m.header.stamp.sec * 1_000_000_000 + m.header.stamp.nanosec for m in messages]
    oldest = min(stamps)
    if 0 < oldest <= max(stamps) <= now and now - oldest < max_age_ns and max(stamps) - oldest <= skew_ns:
        return oldest
    return None


class SensorSync(Node):
    channels = ("left/image_raw", "right/image_raw", "left/camera_info", "right/camera_info")

    def __init__(self):
        super().__init__("suixing_sensor_sync")
        self.skew = self.declare_parameter("max_pair_skew_ms", 5).value * 1_000_000
        self.age = self.declare_parameter("max_input_age_ms", 100).value * 1_000_000
        if not 0 < self.skew <= 20_000_000 or not self.skew < self.age:
            raise ValueError("invalid stereo time synchronization limits")
        prefix = self.declare_parameter("raw_stereo_ns", "/stereo_driver").value.rstrip("/")
        if not prefix.startswith("/") or prefix == "/stereo":
            raise ValueError("raw_stereo_ns must be an absolute namespace distinct from /stereo")
        self.frames = tuple(self.declare_parameter(f"{name}_frame", "").value
                            for name in ("d6", "left", "right"))
        if len(set(self.frames)) != 3 or any(not f or f == "base_link" for f in self.frames):
            raise ValueError("set the measured D6 and optical frame names")
        transforms = []
        for name, frame in zip(("d6", "left", "right"), self.frames):
            values = self.declare_parameter(f"{name}_extrinsic", Parameter.Type.DOUBLE_ARRAY).value
            if (len(values) != 7 or not all(isfinite(n) for n in values)
                    or abs(sum(n*n for n in values[3:]) - 1) > 0.001):
                raise ValueError(f"invalid measured {name} extrinsic")
            tf = TransformStamped()
            tf.header.frame_id = "base_link"
            tf.header.stamp = self.get_clock().now().to_msg()
            tf.child_frame_id = frame
            t, q = tf.transform.translation, tf.transform.rotation
            t.x, t.y, t.z, q.x, q.y, q.z, q.w = values
            transforms.append(tf)
        self.broadcaster = StaticTransformBroadcaster(self)
        self.broadcaster.sendTransform(transforms)
        kinds = (Image, Image, CameraInfo, CameraInfo)
        self.outputs = [self.create_publisher(kind, f"/stereo/{channel}", qos_profile_sensor_data)
                        for kind, channel in zip(kinds, self.channels)]
        self.inputs = [Subscriber(self, kind, f"{prefix}/{channel}", qos_profile=qos_profile_sensor_data)
                       for kind, channel in zip(kinds, self.channels)]
        # Humble ApproximateTimeSynchronizer checks strictly less than slop.
        self.sync = ApproximateTimeSynchronizer(self.inputs, 8, (self.skew + 1) / 1e9)
        self.sync.registerCallback(self.receive_pair)

    def receive_pair(self, left, right, left_info, right_info):
        messages = left, right, left_info, right_info
        oldest = capture_stamp(messages, self.get_clock().now().nanoseconds, self.skew, self.age)
        if oldest is None:
            return
        for image, info, frame in zip((left, right), (left_info, right_info), self.frames[1:]):
            if (image.header.frame_id != frame or info.header.frame_id != frame
                    or (image.width, image.height) != (info.width, info.height)
                    or image.encoding not in ("mono8", "rgb8", "bgr8")):
                self.get_logger().warning("stereo frame, dimensions or encoding mismatch",
                                          throttle_duration_sec=5.0)
                return
        try:
            stereo_intrinsics({"p": left_info.p}, {"p": right_info.p})
        except ValueError:
            self.get_logger().warning("missing or invalid stereo projection calibration",
                                      throttle_duration_sec=5.0)
            return
        for outgoing, incoming in zip(self.outputs, messages):
            message = copy(incoming)
            message.header = copy(incoming.header)
            message.header.stamp = copy(incoming.header.stamp)
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(oldest, 1_000_000_000)
            outgoing.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = SensorSync()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
