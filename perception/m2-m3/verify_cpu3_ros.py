"""Capture the actual JSON and wire messages from RiskNode using fixed inputs."""

from dataclasses import asdict
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import rclpy

from suixing_risk.geometry import Pose, StereoEvidence, Scan
from suixing_risk.protocol import decode
from suixing_risk.ros_node import RiskNode
from suixing_risk.simulate import ray_scan


def scan_from_json(data):
    return Scan(**dict(data, pose=Pose(**data["pose"]))) if data else None


def verify(root, generate):
    rclpy.init(args=["--ros-args", "-p", "publish_wire_frame:=true"])
    node = RiskNode()
    try:
        jsons, frames = [], []
        node.publisher = SimpleNamespace(publish=lambda msg: jsons.append(json.loads(msg.data)))
        node.wire_publisher = SimpleNamespace(publish=lambda msg: frames.append(bytes(msg.data)))
        node.session = "0123456789abcdef"
        stamp = 1_000_000_000
        for index, (name, now, has_sources) in enumerate((
                ("normal", stamp + 20_000_000, True),
                ("exact_expiry", stamp + 140_000_000, True),
                ("both_missing", stamp + 200_000_000, False)), 1):
            folder = root / name
            if generate:
                folder.mkdir(parents=True, exist_ok=True)
                scan = ray_scan(stamp)
                stereo = ray_scan(stamp, pose=Pose(0.03))
                data = {"generated_ns": now, "speed_mps": 0.6,
                        "scan": asdict(scan) if has_sources else None,
                        "stereo_coverage": asdict(stereo) if has_sources else None}
                (folder / "input.json").write_text(json.dumps(data, indent=2) + "\n")
            data = json.loads((folder / "input.json").read_text())
            node.scan = scan_from_json(data["scan"])
            coverage = scan_from_json(data["stereo_coverage"])
            node.stereo = StereoEvidence(coverage.stamp_ns, coverage.lifetime_ms, (),
                                         coverage=coverage) if coverage else None
            node.tracks = ()
            odom = SimpleNamespace(twist=SimpleNamespace(twist=SimpleNamespace(
                linear=SimpleNamespace(x=data["speed_mps"]))))
            with patch.object(node, "get_clock", return_value=SimpleNamespace(
                    now=lambda: SimpleNamespace(nanoseconds=data["generated_ns"]))), \
                    patch.object(node, "find_odometry", return_value=odom):
                node.publish_risk()
            assert len(jsons) == len(frames) == index
            result, frame = jsons[-1], frames[-1]
            decoded = decode(frame)
            expected = "CLEAR" if name == "normal" else "UNKNOWN"
            assert set(result["risk"].values()) == {expected}
            assert decoded["risk"] == result["risk"]
            assert decoded["sample_ns"] == result["sample_ns"]
            assert result["valid_for_ms"] == (120 if name == "normal" else None)
            assert result["suggested_speed_limit_mps"] == (None if name == "normal" else 0.0)
            assert len(frame) == 64
            if generate:
                (folder / "expected.json").write_text(json.dumps(result, indent=2) + "\n")
                (folder / "risk.bin").write_bytes(frame)
                (folder / "risk.hex").write_text(frame.hex(" ") + "\n")
            assert result == json.loads((folder / "expected.json").read_text())
            assert frame == (folder / "risk.bin").read_bytes()
            print(f"PASS {name}: ROS JSON, {len(frame)} bytes, {expected}, CRC valid")
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    verify(Path(__file__).resolve().parent / "fixtures", parser.parse_args().generate)
