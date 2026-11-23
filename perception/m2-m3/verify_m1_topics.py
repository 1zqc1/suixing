"""Replay the original M1 CDR messages and capture real ROS topic publications."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from time import monotonic

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.serialization import deserialize_message
from rosgraph_msgs.msg import Clock
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import String, UInt8MultiArray

from suixing_risk.protocol import decode
from suixing_risk.ros_node import RiskNode, stamp_ns


LIFETIME_MS = 100


def verify(bag, output):
    print(f"bag={bag.name} sha256={hashlib.sha256(bag.read_bytes()).hexdigest()}", flush=True)
    with closing(sqlite3.connect(bag.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("""
            SELECT name, type, timestamp, data
            FROM messages JOIN topics ON topics.id = messages.topic_id
            ORDER BY timestamp, messages.id
        """).fetchall()
    assert len(rows) == 11
    rclpy.init(args=["--ros-args", "-p", "publish_wire_frame:=true",
                     "-p", "use_sim_time:=true", "-p", f"lifetime_ms:={LIFETIME_MS}",
                     "-p", "risk_period_ms:=10"])
    node = RiskNode()
    driver = rclpy.create_node("m1_acceptance", use_global_arguments=False)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    executor.add_node(driver)
    summaries, frames = {}, {}
    driver.create_subscription(String, "/suixing/risk_summary",
                               lambda msg: store_summary(summaries, msg), 10)
    driver.create_subscription(UInt8MultiArray, "/suixing/risk_frame",
                               lambda msg: store_frame(frames, msg), 10)
    clock = driver.create_publisher(Clock, "/clock", 10)
    static_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    publishers = {}

    def wait(check, description):
        deadline = monotonic() + 8
        while not check():
            if monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for {description}")
            executor.spin_once(timeout_sec=0.02)

    def set_clock(ns):
        message = Clock()
        message.clock.sec, message.clock.nanosec = divmod(ns, 1_000_000_000)
        clock.publish(message)
        wait(lambda: node.get_clock().now().nanoseconds == ns, f"/clock at {ns}")

    try:
        node.timer.cancel()
        wait(lambda: clock.get_subscription_count() and
             node.publisher.get_subscription_count() and
             node.wire_publisher.get_subscription_count(), "ROS topic discovery")
        for name, typename, timestamp, blob in rows:
            msg_type = get_message(typename)
            if name not in publishers:
                publishers[name] = driver.create_publisher(
                    msg_type, name, static_qos if name == "/tf_static" else 10)
                wait(publishers[name].get_subscription_count, name)
            set_clock(timestamp)
            msg = deserialize_message(blob, msg_type)
            publishers[name].publish(msg)
            if name == "/tf_static":
                target, source = msg.transforms[0].header.frame_id, msg.transforms[0].child_frame_id
                wait(lambda: node.tf.can_transform(target, source, rclpy.time.Time()), name)
            else:
                key = ("scan" if name == "/d6/scan" else
                       name.split("/")[2] + ("_info" if name.endswith("/camera_info") else ""))
                wait(lambda: node.buffers[key] and
                     stamp_ns(node.buffers[key][-1]) == stamp_ns(msg), name)
            print(f"replayed {timestamp} {name}", flush=True)

        latest = max(stamp_ns(history[-1]) for history in node.buffers.values() if history)
        node.timer.reset()
        deadline = latest + LIFETIME_MS * 1_000_000
        previous = None
        for name, now in (("normal", rows[-1][2] + 10_000_000),
                          ("exact_expiry", deadline), ("both_missing", deadline + 50_000_000)):
            set_clock(now)
            wait(lambda: now in frames and frames[now][0]["seq"] in summaries,
                 f"JSON and binary publications for {name}")
            wire, payload = frames[now]
            summary = summaries[wire["seq"]]
            assert len(payload) == 64 and payload[50:] == bytes(14)
            assert wire["session_id"] == int(summary["session_id"][:8], 16)
            for field in ("seq", "risk", "sample_ns", "scan_valid", "stereo_valid",
                          "valid_for_ms", "suggested_speed_limit_mps"):
                assert summary[field] == wire[field], field
            if name == "normal":
                assert wire["scan_valid"] and wire["stereo_valid"] and wire["aligned"]
                assert node.scan.stamp_ns == node.stereo.stamp_ns == latest
                assert wire["sample_ns"] == latest and wire["valid_for_ms"] == 60
            else:
                assert not wire["scan_valid"] and not wire["stereo_valid"]
                assert set(wire["risk"].values()) == {"UNKNOWN"}
                assert wire["sample_ns"] is None and wire["valid_for_ms"] is None
                assert wire["suggested_speed_limit_mps"] == 0
            if previous is not None:
                assert wire["session_id"] == previous["session_id"]
                assert wire["seq"] > previous["seq"]
                assert wire["generated_ns"] > previous["generated_ns"]
            previous = wire
            folder = output / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "risk.bin").write_bytes(payload)
            (folder / "risk.hex").write_text(payload.hex(" ") + "\n")
            (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            (folder / "decoded.json").write_text(json.dumps(wire, indent=2) + "\n")
            print(f"PASS {name}: generated_ns={now} session=0x{wire['session_id']:08x} "
                  f"seq={wire['seq']} reason={wire['reason']} risk={wire['risk']} 64 bytes CRC OK",
                  flush=True)
    finally:
        executor.shutdown()
        driver.destroy_node()
        node.destroy_node()
        rclpy.try_shutdown()


def store_summary(summaries, msg):
    summary = json.loads(msg.data)
    summaries[summary["seq"]] = summary


def store_frame(frames, msg):
    payload = bytes(msg.data)
    wire = decode(payload)
    frames[wire["generated_ns"]] = wire, payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", type=Path, default=Path(
        "inputs/m1-handoff-v0.1/mock-bag/mock-bag_0.db3"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verify(args.bag, args.output)
