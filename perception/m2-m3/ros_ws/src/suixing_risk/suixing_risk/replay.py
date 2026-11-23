"""Validate the original M1 handoff and produce teammate A's replay evidence."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from .geometry import fresh, summarize
from .perception import Transform, observe_stereo, scan_from_values


def read_messages(path):
    try:
        from rclpy.serialization import deserialize_message
    except ImportError:
        from rosbags.highlevel import AnyReader
        from rosbags.typesys import Stores, get_typestore

        with AnyReader([path], default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as reader:
            for connection, timestamp, raw in reader.messages():
                yield connection.topic, timestamp, reader.deserialize(raw, connection.msgtype)
    else:
        from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions
        from rosidl_runtime_py.utilities import get_message

        reader = SequentialReader()
        reader.open(StorageOptions(uri=str(path), storage_id="sqlite3"), ConverterOptions("cdr", "cdr"))
        types = {topic.name: get_message(topic.type) for topic in reader.get_all_topics_and_types()}
        while reader.has_next():
            topic, raw, timestamp = reader.read_next()
            yield topic, timestamp, deserialize_message(raw, types[topic])


def tf_transform(tf):
    t, q = tf.transform.translation, tf.transform.rotation
    return Transform((t.x, t.y, t.z), (q.x, q.y, q.z, q.w))


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_image(root, row):
    payload = row["payload"]
    image = (root / payload["path"]).resolve()
    if not image.is_relative_to(root.resolve()) or payload["encoding"] != "mono8":
        raise ValueError("invalid M1 PGM reference")
    width, height = payload["width"], payload["height"]
    expected = f"P5\n{width} {height}\n255\n".encode("ascii")
    data = image.read_bytes()
    if not data.startswith(expected) or len(data) != width * height + len(expected):
        raise ValueError(f"invalid M1 PGM {image.name}")
    return np.frombuffer(data[len(expected):], dtype=np.uint8).reshape(height, width)


def replay(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    calibrations = json.loads((root / "sensors" / "stereo-calibration.mock.json").read_text(encoding="utf-8"))
    counts, transforms = Counter(), {}
    for topic, _, message in read_messages(root / "mock-bag"):
        counts[topic] += 1
        if topic == "/tf_static":
            for tf in message.transforms:
                if tf.header.frame_id == "base_link":
                    transforms[tf.child_frame_id] = tf_transform(tf)
    if dict(counts) != manifest["bag_topic_counts"]:
        raise ValueError("bag topic counts differ from manifest")
    d6 = load_jsonl(root / "sensors" / "d6-scan.mock.jsonl")
    images = load_jsonl(root / "sensors" / "stereo.mock.jsonl")
    pairs = {}
    for row in images:
        key = row["session_id"], int(row["stamp_ns"])
        pair = pairs.setdefault(key, {})
        if row["source"] in pair:
            raise ValueError("duplicate stereo image")
        pair[row["source"]] = row
    for seq, row in enumerate(d6, start=1):
        stamp, received = int(row["stamp_ns"]), int(row["received_ros_ns"])
        age = (received - stamp) / 1e6
        payload = row["payload"]
        scan = None
        if row["quality"] != "invalid" and row["stamp_source"] == "device" and fresh(stamp, row["valid_for_ms"], received):
            scan = scan_from_values(stamp, row["valid_for_ms"], payload["angle_min_rad"],
                                    payload["angle_increment_rad"], payload["range_min_m"],
                                    payload["range_max_m"], payload["ranges_m"], transforms[row["frame_id"]])
        stereo, metrics = None, None
        for (_, pair_stamp), pair in pairs.items():
            if pair_stamp != stamp or set(pair) != {"stereo_left", "stereo_right"}:
                continue
            left, right = pair["stereo_left"], pair["stereo_right"]
            if not all(item["quality"] == "valid" and item["stamp_source"] == "device"
                       and fresh(pair_stamp, item["valid_for_ms"], received) for item in (left, right)):
                continue
            configs = calibrations["cameras"]
            stereo, metrics = observe_stereo(load_image(root, left), load_image(root, right),
                                             configs[left["frame_id"]], configs[right["frame_id"]],
                                             transforms[left["frame_id"]], pair_stamp,
                                             min(left["valid_for_ms"], right["valid_for_ms"]))
        unknown_indices = [i for i, value in enumerate(payload["ranges_m"]) if value is None]
        yield {
            "data_version": manifest["data_version"],
            "data_origin": manifest["data_origin"],
            "sample_seq": row["seq"],
            "scan_age_ms": age,
            "scan_accepted": scan is not None,
            "missing_beam_indices": unknown_indices,
            "missing_beam_angles_rad": [payload["angle_min_rad"] + i * payload["angle_increment_rad"]
                                        for i in unknown_indices],
            "stereo": metrics,
            "summary": summarize("m1-replay", seq, received, scan, stereo),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    for row in replay(args.bundle):
        print(json.dumps(row, allow_nan=False))


if __name__ == "__main__":
    main()
