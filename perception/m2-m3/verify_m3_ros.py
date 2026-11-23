"""Humble topic regressions for directional TTC and differential drive integration."""

import argparse
from array import array
from contextlib import contextmanager
import json
from pathlib import Path
from time import monotonic

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.executors import SingleThreadedExecutor
from rclpy.time import Time
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from std_msgs.msg import String, UInt8MultiArray
from std_srvs.srv import SetBool
from tf2_ros import StaticTransformBroadcaster

from suixing_risk.chassis_ros import ChassisNode
from suixing_risk.protocol import decode
from suixing_risk.ros_node import RiskNode, stamp_ns
from suixing_risk.semantic_ros import SemanticNode
from suixing_risk.simulate import ray_scan


@contextmanager
def nodes(node_type, **parameters):
    args = ["--ros-args"]
    for key, value in parameters.items():
        args.extend(("-p", f"{key}:={value}"))
    rclpy.init(args=args)
    executor = SingleThreadedExecutor()
    try:
        node = node_type()
        executor.add_node(node)
        probe = rclpy.create_node("m3_verification", use_global_arguments=False)
        executor.add_node(probe)
        yield node, probe, executor
    finally:
        registered_nodes = executor.get_nodes()
        executor.shutdown()
        for node in registered_nodes:
            node.destroy_node()
        rclpy.try_shutdown()


def wait(executor, check, description, timeout=5):
    deadline = monotonic() + timeout
    while not check():
        if monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for {description}")
        executor.spin_once(timeout_sec=0.01)


def verify_ttc():
    with nodes(RiskNode, use_sim_time="true", publish_wire_frame="true",
               publish_directional_ttc="true", stereo_enabled="false",
               navigation_odom_age_ms=70, risk_period_ms=10) as (node, probe, executor):
        node.timer.cancel()
        summaries, wire_frames = {}, {}

        def summary_callback(msg):
            result = json.loads(msg.data)
            summaries[result["seq"]] = result

        def frame_callback(msg):
            frame = decode(bytes(msg.data))
            wire_frames[frame["generated_ns"]] = frame

        probe.create_subscription(String, "/suixing/risk_summary", summary_callback, 10)
        probe.create_subscription(UInt8MultiArray, "/suixing/risk_frame", frame_callback, 10)
        clock = probe.create_publisher(Clock, "/clock", 10)
        lidar = probe.create_publisher(LaserScan, "/d6/scan", 10)
        measured_odom = probe.create_publisher(Odometry, "/odom", 10)
        tf_broadcaster = StaticTransformBroadcaster(probe)
        wait(executor, lambda: min(clock.get_subscription_count(), lidar.get_subscription_count(),
                                   measured_odom.get_subscription_count()), "risk input discovery")

        def set_time(ns):
            clock.publish(Clock(clock=Time(nanoseconds=ns).to_msg()))
            wait(executor, lambda: node.get_clock().now().nanoseconds == ns, f"/clock at {ns}")

        def result_at(ns):
            set_time(ns)
            wait(executor, lambda: ns in wire_frames and wire_frames[ns]["seq"] in summaries,
                 f"paired risk output at {ns}")
            wire = wire_frames[ns]
            return summaries[wire["seq"]], wire

        stamp = 1_000_000_000
        set_time(stamp)
        transform = TransformStamped()
        transform.header.frame_id = "base_link"
        transform.child_frame_id = "d6_test"
        transform.transform.rotation.w = 1.0
        tf_broadcaster.sendTransform(transform)
        wait(executor, lambda: node.tf.can_transform("base_link", "d6_test", Time()), "D6 static TF")

        scan = ray_scan(stamp, (0.65, 0.0))
        message = LaserScan(angle_min=scan.start_rad, angle_increment=scan.step_rad,
                            range_min=scan.minimum_m, range_max=scan.maximum_m, ranges=scan.ranges)
        message.header.frame_id = "d6_test"
        message.header.stamp = Time(nanoseconds=stamp).to_msg()
        lidar.publish(message)
        for odom_stamp, speed in ((stamp, 0.25), (stamp + 80_000_000, 0.0)):
            odom = Odometry(child_frame_id="base_link")
            odom.header.frame_id = "odom"
            odom.header.stamp = Time(nanoseconds=odom_stamp).to_msg()
            odom.pose.pose.orientation.w = 1.0
            odom.twist.twist.linear.x = speed
            measured_odom.publish(odom)
        wait(executor, lambda: node.buffers["scan"] and len(node.buffers["odom"]) == 2,
             "scan and both odometry samples")
        assert stamp_ns(node.buffers["scan"][0]) == stamp
        node.timer.reset()

        present, wire = result_at(stamp + 40_000_000)
        assert present["risk"]["straight"] == "DANGER"
        directional = present["ttc_by_direction_s"]
        assert set(directional) == {"left", "straight", "right"}
        assert 0.0 < directional["straight"][0] <= directional["straight"][1] < 1.0
        assert present["ttc_s"] == directional["straight"] == wire["ttc_s"]
        print(f"PASS simulated D6 + /odom: JSON TTC {directional}, binary straight TTC {wire['ttc_s']}")
        expired, wire = result_at(stamp + 70_000_000)
        assert expired["scan_valid"] and expired["ttc_s"] is None and wire["ttc_s"] is None
        assert expired["ttc_by_direction_s"] == dict.fromkeys(directional)
        assert set(expired["risk"].values()) == {"UNKNOWN"}
        print("PASS /odom exact expiry at configured 70 ms and future odometry rejected")


def verify_differential():
    with nodes(ChassisNode, drive_mode="differential", wheel_separation_m=0.5,
               max_wheel_speed_mps=0.4, watchdog_ms=500, feedback_gap_ms=400
               ) as (node, probe, executor):
        commands, odometry = [], []
        probe.create_subscription(String, "/suixing/chassis/command",
                                  lambda msg: commands.append(json.loads(msg.data)), 10)
        probe.create_subscription(Odometry, "/odom", odometry.append, 10)
        feedback = probe.create_publisher(String, "/suixing/chassis/feedback", 10)
        candidate = probe.create_publisher(TwistStamped, "/suixing/cmd_vel_candidate", 10)
        status = probe.create_publisher(String, "/suixing/navigation_status", 10)
        arm = probe.create_client(SetBool, "/suixing/chassis/arm")
        wait(executor, lambda: arm.service_is_ready() and min(feedback.get_subscription_count(),
                                   candidate.get_subscription_count(), status.get_subscription_count()),
             "chassis input discovery")
        wait(executor, lambda: commands and commands[-1]["brake"], "disarmed brake output")

        def send_feedback(left, right, permit=True):
            feedback.publish(String(data=json.dumps({
                "stamp_ns": node.get_clock().now().nanoseconds, "left_wheel_mps": left,
                "right_wheel_mps": right, "motion_permitted": permit, "estop_active": False,
                "fault": False, "brake_applied": True,
            })))

        send_feedback(0.0, 0.0)
        wait(executor, lambda: odometry, "first feedback odometry")
        armed = arm.call_async(SetBool.Request(data=True))
        wait(executor, armed.done, "arm response")
        assert armed.result().success

        now = node.get_clock().now()
        cmd = TwistStamped()
        cmd.header.stamp = now.to_msg()
        cmd.header.frame_id = "base_link"
        cmd.twist.linear.x = cmd.twist.angular.z = 0.2
        candidate.publish(cmd)
        status.publish(String(data=json.dumps({
            "stamp_ns": now.nanoseconds, "valid_until_ns": now.nanoseconds + 200_000_000,
        })))
        wait(executor, lambda: not commands[-1]["brake"], "paired wheel targets")
        motion = commands[-1]
        assert abs(motion["left_wheel_mps"] - 0.15) < 1e-9
        assert abs(motion["right_wheel_mps"] - 0.25) < 1e-9
        send_feedback(0.15, 0.25)
        wait(executor, lambda: len(odometry) >= 2, "measured wheel odometry")
        twist = odometry[-1].twist.twist
        assert abs(twist.linear.x - 0.2) < 1e-9 and abs(twist.angular.z - 0.2) < 1e-9
        send_feedback(0.15, 0.25, permit=False)
        wait(executor, lambda: commands[-1]["brake"] and not node.gate.armed, "permission loss")
        assert commands[-1]["left_wheel_mps"] == commands[-1]["right_wheel_mps"] == 0
        print("PASS differential wheel command, measured odometry, and brake on permission loss")


def verify_semantic_association(backend):
    assets = Path(__file__).resolve().parent / "inputs" / "yolo"
    with nodes(RiskNode, use_sim_time="true", semantic_association="true",
               model_path=assets / "yolov8n.onnx", risk_period_ms=10, stereo_backend=backend,
               publish_perception_diagnostics="true"
               ) as (node, probe, executor):
        node.timer.cancel()
        groups = {"summary": [], "scene": [], "detections": [], "diagnostics": []}
        for key, topic in (("summary", "/suixing/risk_summary"), ("scene", "/suixing/scene_objects"),
                           ("detections", "/suixing/detections"),
                           ("diagnostics", "/suixing/perception_diagnostics")):
            probe.create_subscription(String, topic, lambda msg, k=key: groups[k].append(
                json.loads(msg.data)), 10)
        clock = probe.create_publisher(Clock, "/clock", 10)
        tf = StaticTransformBroadcaster(probe)
        left, right = "left_test_optical", "right_test_optical"
        transforms = []
        for frame, lateral in ((left, 0.05), (right, -0.05)):
            transform = TransformStamped()
            transform.header.frame_id = "base_link"
            transform.child_frame_id = frame
            transform.transform.translation.x = 0.1
            transform.transform.translation.y = lateral
            transform.transform.translation.z = 0.65
            q = transform.transform.rotation
            q.x, q.y, q.z, q.w = -0.5, 0.5, -0.5, 0.5
            transforms.append(transform)
        tf.sendTransform(transforms)
        wait(executor, lambda: node.tf.can_transform("base_link", right, Time()), "stereo static TF")
        wait(executor, clock.get_subscription_count, "simulated clock discovery")

        def set_time(ns):
            clock.publish(Clock(clock=Time(nanoseconds=ns).to_msg()))
            wait(executor, lambda: node.get_clock().now().nanoseconds == ns, f"/clock at {ns}")

        stamp = 2_000_000_000
        set_time(stamp)
        photo = cv2.imread(str(assets / "bus.jpg"))
        scale = 320 / max(photo.shape[:2])
        original = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        shifted = np.zeros_like(original)
        shifted[:, :-8] = original[:, 8:]
        height, width = original.shape[:2]
        fx = 220.0
        cx, cy = width / 2, height / 2
        image_publishers, images = [], []
        for side, pixels, frame, translation in (
                ("left", original, left, 0.0), ("right", shifted, right, -22.0)):
            image_pub = probe.create_publisher(Image, f"/stereo/{side}/image_raw", 10)
            info_pub = probe.create_publisher(CameraInfo, f"/stereo/{side}/camera_info", 10)
            wait(executor, lambda: image_pub.get_subscription_count() and
                 info_pub.get_subscription_count(), f"{side} stereo subscriptions")
            info = CameraInfo(
                width=width, height=height, distortion_model="plumb_bob",
                k=[fx, 0., cx, 0., fx, cy, 0., 0., 1.], d=[0.] * 5,
                r=[1., 0., 0., 0., 1., 0., 0., 0., 1.],
                p=[fx, 0., cx, translation, 0., fx, cy, 0., 0., 0., 1., 0.])
            info.header.frame_id = frame
            info.header.stamp = Time(nanoseconds=stamp).to_msg()
            image = Image(header=info.header, width=width, height=height, encoding="bgr8",
                          step=3 * width, data=array("B", pixels.tobytes()))
            info_pub.publish(info)
            image_pub.publish(image)
            image_publishers.append(image_pub)
            images.append(image)
        wait(executor, lambda: all(node.buffers[key] for key in (
            "left", "right", "left_info", "right_info")), "stereo input buffers")
        node.timer.reset()
        set_time(stamp + 10_000_000)
        wait(executor, lambda: groups["summary"] and groups["summary"][-1]["stereo_valid"],
             "geometry before YOLO")
        assert not groups["summary"][-1]["semantic_used"]
        wait(executor, lambda: groups["diagnostics"], "stereo diagnostics")
        diagnostics = groups["diagnostics"][-1]
        assert diagnostics["stereo_backend"] == backend
        assert abs(diagnostics["stereo"]["median_disparity_px"] - 8) < 0.2
        assert diagnostics["pipeline_ms"] >= diagnostics["stereo"]["processing_ms"] >= 0

        semantic = SemanticNode()
        executor.add_node(semantic)
        wait(executor, lambda: image_publishers[0].get_subscription_count() >= 2,
             "YOLO left-image subscription")
        image_publishers[0].publish(images[0])
        wait(executor, lambda: groups["detections"] and node.semantic_history,
             "actual ONNX detections delivered to the risk node")
        assert groups["detections"][-1]["stamp_ns"] == stamp
        assert {"person", "bus"} <= {item["label"] for item in groups["detections"][-1]["detections"]}
        set_time(stamp + 30_000_000)
        wait(executor, lambda: groups["scene"] and groups["summary"][-1]["semantic_used"],
             "same-frame YOLO and stereo association")
        scene = groups["scene"][-1]
        assert scene["frame_id"] == "base_link" and scene["stamp_ns"] == stamp
        assert scene["objects"] and any(abs(item["position_m"][0] - 2.85) < 0.15
                                        for item in scene["objects"])
        set_time(stamp + 500_000_000)
        wait(executor, lambda: not groups["summary"][-1]["stereo_valid"], "stereo and semantic expiry")
        assert not groups["summary"][-1]["semantic_used"]
        print(f"PASS ONNX + shifted stereo photo ({backend}): {len(scene['objects'])} base_link objects,"
              f" stereo {diagnostics['stereo']['processing_ms']:.1f} ms,"
              " semantic evidence applied and then expired")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stereo-backend", choices=("sad", "sgbm"), default="sad")
    args = parser.parse_args()
    verify_ttc()
    verify_differential()
    verify_semantic_association(args.stereo_backend)
