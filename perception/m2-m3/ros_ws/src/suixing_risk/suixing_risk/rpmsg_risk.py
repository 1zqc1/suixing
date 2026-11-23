"""Forward raw risk payloads to an explicitly selected Linux RPMsg endpoint."""

import os
import stat
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray

from .protocol import decode


class RiskForwarder(Node):
    def __init__(self):
        super().__init__("suixing_rpmsg_risk")
        device = Path(self.declare_parameter("device", "").value).resolve()
        if device.parent != Path("/dev") or not device.name.startswith("rpmsg") or not stat.S_ISCHR(device.stat().st_mode):
            raise ValueError("device must be the team's /dev/rpmsg character endpoint")
        self.fd = os.open(device, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.create_subscription(UInt8MultiArray, "/suixing/risk_frame", self.forward, 1)

    def forward(self, message):
        frame = bytes(message.data)
        try:
            decoded = decode(frame)
            now = self.get_clock().now().nanoseconds
            age = now - decoded["generated_ns"]
            if age < 0 or age >= 100_000_000:
                return
            lifetime = decoded["valid_for_ms"]
            if lifetime is not None and age >= lifetime * 1_000_000:
                return
            if os.write(self.fd, frame) != len(frame):
                raise OSError("short RPMsg write")
        except (OSError, ValueError) as error:
            self.get_logger().warning(f"risk frame not forwarded: {error}", throttle_duration_sec=2.0)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = RiskForwarder()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            os.close(node.fd)
            node.destroy_node()
        rclpy.try_shutdown()
