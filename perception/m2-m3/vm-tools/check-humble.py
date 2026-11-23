"""Verify optional v0.3 interfaces using public and synthetic fixture data."""

from array import array
from collections import Counter
import json
from pathlib import Path
import sys
import time

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import UInt8MultiArray
from vision_msgs.msg import Detection2DArray

from suixing_risk.protocol import decode


def main():
    sample, report_path = map(Path, sys.argv[1:])
    pixels = cv2.imread(str(sample), cv2.IMREAD_COLOR)
    if pixels is None:
        raise ValueError(f"could not decode {sample}")
    scale = 320 / max(pixels.shape[:2])
    pixels = cv2.resize(pixels, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    height, width = pixels.shape[:2]
    image = Image(height=height, width=width, encoding="bgr8", is_bigendian=0, step=width * 3,
                  data=array("B", pixels.tobytes()))
    image.header.frame_id = "vm_review_color_fixture"

    result = {}
    rclpy.init(args=[])
    probe = Node("suixing_v03_interface_review")

    def receive_detection(message):
        if message.header.frame_id != image.header.frame_id or message.header.stamp.sec != 1700000000:
            return
        items = []
        for item in message.detections:
            if not item.results or not item.id or min(item.bbox.size_x, item.bbox.size_y) <= 0:
                return
            hypothesis = item.results[0].hypothesis
            items.append({"label": hypothesis.class_id, "track_id": item.id,
                          "confidence": hypothesis.score,
                          "center": [item.bbox.center.position.x, item.bbox.center.position.y]})
        if Counter(item["label"] for item in items) == {"person": 4, "bus": 1}:
            result["Detection2DArray"] = {"count": len(items), "detections": items}

    def receive_wire(message):
        data = bytes(message.data)
        packet = decode(data)
        if packet["scan_valid"] and packet["stereo_valid"] and packet["aligned"]:
            corrupted = bytearray(data)
            corrupted[14] ^= 1
            try:
                decode(corrupted)
            except ValueError as error:
                if str(error) != "CRC mismatch":
                    raise
            else:
                raise RuntimeError("corrupted packet was accepted")
            result["RiskSummary"] = {"bytes": len(data), "crc": "verified",
                                     "corrupted_frame": "rejected", "packet": packet}

    try:
        publisher = probe.create_publisher(Image, "/suixing/vision_fixture/image", 3)
        probe.create_subscription(Detection2DArray, "/suixing/detections_2d",
                                  receive_detection, qos_profile_sensor_data)
        probe.create_subscription(UInt8MultiArray, "/suixing/risk_frame", receive_wire, 10)
        deadline = time.monotonic() + 32
        last_sent = 0.0
        sequence = 0
        while time.monotonic() < deadline and len(result) < 2:
            if publisher.get_subscription_count() and time.monotonic() - last_sent > 0.8:
                image.header.stamp.sec = 1700000000
                image.header.stamp.nanosec = sequence * 20_000_000
                publisher.publish(image)
                sequence += 1
                last_sent = time.monotonic()
            rclpy.spin_once(probe, timeout_sec=0.2)
        if len(result) < 2:
            raise RuntimeError(f"missing interface evidence, received {list(result)} (sent {sequence} images)")
        report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("PASS v0.3 Detection2DArray with 5 boxes and track IDs")
        print("PASS v0.3 64-byte RiskSummary over ROS, live D6 and stereo, corrupted CRC rejected")
    finally:
        probe.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
