"""Exercise the semantic ROS node with the public BGR reference image."""

from array import array
import argparse
import json
from pathlib import Path
import time

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    pixels = cv2.imread(str(args.sample), cv2.IMREAD_COLOR)
    if pixels is None:
        raise ValueError(f"could not decode {args.sample}")
    # Keep the DDS fixture compact while retaining both reference classes.
    scale = 320 / max(pixels.shape[:2])
    pixels = cv2.resize(pixels, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    height, width = pixels.shape[:2]

    rclpy.init(args=[])
    probe = Node("suixing_vision_smoke")
    try:
        publisher = probe.create_publisher(Image, "/suixing/vision_fixture/image", 3)
        frame = Image(height=height, width=width, encoding="bgr8", is_bigendian=0, step=width*3,
                      data=array("B", pixels.tobytes()))
        frame.header.stamp.sec = 1700000000
        frame.header.frame_id = "vision_fixture_optical"
        received, annotated = [], []
        probe.create_subscription(String, "/suixing/detections", lambda msg: received.append(json.loads(msg.data)), 5)
        probe.create_subscription(Image, "/suixing/detections/image",
                                  lambda msg: annotated.append(msg), qos_profile_sensor_data)
        deadline = time.monotonic() + 25.0
        last_published = 0.0
        sent = 0
        report = None
        while time.monotonic() < deadline:
            if publisher.get_subscription_count() and time.monotonic() - last_published >= 0.75:
                publisher.publish(frame)
                last_published = time.monotonic()
                sent += 1
            rclpy.spin_once(probe, timeout_sec=0.2)
            if not received or not annotated:
                continue
            result = received[-1]
            labels = {item["label"] for item in result["detections"]}
            annotation = annotated[-1]
            if (result["frame_id"] == frame.header.frame_id
                    and result["stamp_ns"] == 1700000000 * 1_000_000_000
                    and result["image_width"] == width and result["image_height"] == height
                    and {"person", "bus"}.issubset(labels)
                    and annotation.header == frame.header
                    and (annotation.width, annotation.height, annotation.encoding) == (width, height, "bgr8")):
                report = result
                break
        if report is None:
            labels = [item.get("label") for item in received[-1]["detections"]] if received else []
            raise RuntimeError(f"ROS image smoke failed: sent={sent}, detections={len(received)}, "
                               f"annotated={len(annotated)}, latest_labels={labels}")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("PASS Humble semantic node received an image and published detections and annotation")
    finally:
        probe.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
