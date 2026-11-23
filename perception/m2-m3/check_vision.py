"""Run YOLOv8 on a real reference image, then exercise simulated avoidance."""

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from suixing_risk.perception import Transform, observe_stereo
from suixing_risk.semantic import YoloV8Detector, annotate_image
from suixing_risk.semantic_geometry import scene_objects
from suixing_risk.simulate_avoidance import scenarios, verify


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def check_association():
    left = np.random.default_rng(7).integers(0, 256, size=(64, 96), dtype=np.uint8)
    right = np.pad(left[:, 4:], ((0, 0), (0, 4)))
    k = [80.0, 0.0, 47.5, 0.0, 80.0, 31.5, 0.0, 0.0, 1.0]
    p = [80.0, 0.0, 47.5, 0.0, 0.0, 80.0, 31.5, 0.0, 0.0, 0.0, 1.0, 0.0]
    left_cal = {"width": 96, "height": 64, "k": k, "p": p, "d": [0] * 5, "r": np.eye(3)}
    right_p = p.copy()
    right_p[3] = -4.8
    right_cal = dict(left_cal, p=right_p)
    transform = Transform((0.0, 0.0, 0.6), (-0.5, 0.5, -0.5, 0.5))
    _, metrics = observe_stereo(left, right, left_cal, right_cal, transform, 1000, 100,
                                capture_pixels=True)
    pixels = metrics["stereo_pixels"]
    box = {"label": "mock_target", "confidence": 0.9, "xyxy": [20, 12, 75, 54]}
    support = scene_objects([box, dict(box, xyxy=[0, 0, 8, 8])], pixels)
    if len(support) != 1 or support[0]["position_m"][0] != 1.2:
        raise RuntimeError("stereo evidence association regression")
    return support


def verify_project(model, image, output):
    image_bytes = image.read_bytes()
    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"could not read test image {image}")
    detector = YoloV8Detector(model)
    start = perf_counter()
    detections = detector.detect(frame)
    elapsed_ms = round((perf_counter() - start) * 1_000, 2)
    labels = [obj.label for obj in detections]
    if not {"person", "bus"}.issubset(labels):
        raise RuntimeError(f"reference image is missing expected classes: found {labels}")

    output.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", annotate_image(frame, detections))
    if not ok:
        raise OSError("unable to write the detection preview")
    (output / "bus-detections.jpg").write_bytes(encoded.tobytes())
    write_json(output / "detections.json", {
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "image_shape": list(frame.shape),
        "inference_ms_single_image": elapsed_ms,
        "detections": [item.as_dict() for item in detections],
    })
    print(f"PASS real YOLOv8 reference image: {', '.join(labels)} ({elapsed_ms:g} ms)")

    write_json(output / "stereo-association.mock.json", check_association())
    print("PASS stereo association: a detection with depth support and one without support")

    results = tuple(scenarios())
    verify(results)
    write_json(output / "avoidance.json", results)
    for result in results:
        print(f"PASS {result['scenario']}: goal={result['goal_reached']}, "
              f"x={result['final_pose']['x_m']:.3f} m, "
              f"minimum clearance={result['min_clearance_m']:.3f} m")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify_project(args.model, args.image, args.output)


if __name__ == "__main__":
    main()
