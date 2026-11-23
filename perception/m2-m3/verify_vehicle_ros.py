"""Humble callback smoke check with synthetic hardware feedback."""

import json
from time import sleep
from types import SimpleNamespace

import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.parameter import Parameter
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String
from std_srvs.srv import SetBool

from suixing_risk.chassis_ros import ChassisNode
from suixing_risk.sensor_sync import SensorSync


def verify():
    rclpy.init(args=[])
    nodes = []
    try:
        config = {"d6_frame": "d6", "left_frame": "left", "right_frame": "right"}
        config.update({f"{name}_extrinsic": [0., 0., 0., 0., 0., 0., 1.]
                       for name in ("d6", "left", "right")})
        from unittest.mock import patch
        from rclpy.node import Node
        original = Node.__init__

        def with_parameters(node, name, **kwargs):
            values = config if name == "suixing_sensor_sync" else {
                "wheelbase_m": 0.5, "max_steering_rad": 0.5}
            return original(node, name, parameter_overrides=[
                Parameter(key, value=value) for key, value in values.items()], **kwargs)

        with patch.object(Node, "__init__", with_parameters):
            chassis = ChassisNode()
            nodes.append(chassis)
            stereo = SensorSync()
            nodes.append(stereo)
        samples = []
        stereo.outputs = [SimpleNamespace(publish=samples.append)] * 4
        now = stereo.get_clock().now().nanoseconds
        left, right = Image(width=8, height=8, encoding="mono8"), Image(width=8, height=8, encoding="mono8")
        li, ri = CameraInfo(width=8, height=8), CameraInfo(width=8, height=8)
        base_projection = [10., 0., 4., 0., 0., 10., 4., 0., 0., 0., 1., 0.]
        li.p = base_projection
        ri.p = base_projection[:3] + [-1.] + base_projection[4:]
        for i, m in enumerate((left, right, li, ri)):
            m.header.frame_id = ("left", "right")[i % 2]
            m.header.stamp = Time(nanoseconds=now - (4-i) * 1_000_000).to_msg()
        stereo.receive_pair(left, right, li, ri)
        assert len(samples) == 4 and all(m.header.stamp == left.header.stamp for m in samples)
        right.header.stamp = Time(nanoseconds=now - 20_000_000).to_msg()
        stereo.receive_pair(left, right, li, ri)
        assert len(samples) == 4

        commands, odometry = [], []
        chassis.command = SimpleNamespace(publish=lambda m: commands.append(json.loads(m.data)))
        chassis.odom = SimpleNamespace(publish=odometry.append)
        chassis.tf = SimpleNamespace(sendTransform=lambda m: None)

        def feedback(estop=False):
            now = chassis.get_clock().now().nanoseconds
            chassis.receive_feedback(String(data=json.dumps({
                "stamp_ns": now, "speed_mps": 0.0, "steering_rad": 0.0,
                "motion_permitted": True, "estop_active": estop, "fault": False,
                "brake_applied": True,
            })))

        def candidate(lifetime=30_000_000):
            now = chassis.get_clock().now()
            message = TwistStamped()
            message.header.frame_id = "base_link"
            message.header.stamp = now.to_msg()
            message.twist.linear.x = 0.2
            message.twist.angular.z = 0.2
            chassis.receive_status(String(data=json.dumps({
                "stamp_ns": now.nanoseconds, "valid_until_ns": now.nanoseconds + lifetime})))
            chassis.receive_candidate(message)
            chassis.tick()

        feedback()
        assert odometry[-1].header.frame_id == "odom"
        candidate()
        assert commands[-1]["brake"]
        assert chassis.arm(SetBool.Request(data=True), SetBool.Response()).success
        candidate()
        assert not commands[-1]["brake"] and commands[-1]["steering_rad"] > 0
        sleep(0.04)
        chassis.tick()
        assert commands[-1]["brake"]
        feedback(True)
        feedback()
        candidate()
        assert commands[-1]["brake"] and not chassis.gate.armed
        print("PASS stereo calibration and synchronization, wheel odometry, command expiry and e-stop")
    finally:
        for node in reversed(nodes):
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    verify()
