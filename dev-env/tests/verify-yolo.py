"""Verify the competition's Windows YOLOv8n GPU and ONNX export baseline."""
import hashlib
import json
import os
import platform
from importlib.metadata import version
from pathlib import Path

output = Path(__file__).resolve().parents[1] / "yolo-baseline"
settings = output / "settings"
settings.mkdir(parents=True, exist_ok=True)
os.environ["YOLO_CONFIG_DIR"] = str(settings)
os.environ["YOLO_AUTOINSTALL"] = "false"
os.environ["YOLO_OFFLINE"] = "true"

if __name__ == "__main__":
    print("Starting YOLOv8n verification. Loading PyTorch and ONNX Runtime...", flush=True)

import cv2
import numpy as np
import onnx
import torch
from ultralytics import YOLO
from ultralytics.utils import ASSETS

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def iou(a, b):
    intersect = np.maximum(np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2]), 0).prod()
    return float(intersect / (np.prod(a[2:] - a[:2]) + np.prod(b[2:] - b[:2]) - intersect))

def verify():
    weights = output / "yolov8n.pt"
    expected_sha = "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36"
    if sha256(weights) != expected_sha:
        raise RuntimeError("Weights differ from the pinned GitHub v8.3.0 baseline")
    sample = ASSETS / "bus.jpg"
    frame = cv2.imread(str(sample))
    if frame is None or not torch.cuda.is_available():
        raise RuntimeError("The test requires the Ultralytics bus image and a CUDA GPU")
    options = dict(imgsz=640, rect=False, conf=0.25, iou=0.7, verbose=False, save=False)
    detector = YOLO(str(weights))
    native = detector.predict(frame.copy(), device=0, **options)[0]
    if next(detector.predictor.model.model.parameters()).device.type != "cuda":
        raise RuntimeError("PyTorch inference did not use CUDA")
    export = YOLO(str(weights)).export(format="onnx", opset=13, imgsz=640, dynamic=False,
                                       simplify=False, nms=False, half=False, device="cpu")
    exported = Path(export)
    graph = onnx.load(exported)
    onnx.checker.check_model(graph, full_check=True)
    runtime = YOLO(str(exported), task="detect")
    restored = runtime.predict(frame.copy(), device="cpu", **options)[0]
    session = runtime.predictor.model.session
    providers = session.get_providers()
    shape = session.get_inputs()[0].shape
    if providers != ["CPUExecutionProvider"] or shape != [1, 3, 640, 640]:
        raise RuntimeError(f"Unexpected ONNX runtime configuration: {providers}, {shape}")

    reference = native.boxes.data.cpu().numpy()
    results = restored.boxes.data.cpu().numpy()
    if len(reference) != len(results) or not {"person", "bus"}.issubset(
        {native.names[int(row[5])] for row in reference}
    ):
        raise RuntimeError("Detection counts or required sample classes differ")
    unmatched = set(range(len(results)))
    matches = []
    for row in reference:
        candidates = [i for i in unmatched if int(results[i, 5]) == int(row[5])]
        if not candidates:
            raise RuntimeError("Missing ONNX detection for a PyTorch class")
        index = max(candidates, key=lambda i: iou(row[:4], results[i, :4]))
        overlap = iou(row[:4], results[index, :4])
        delta = abs(float(row[4]) - float(results[index, 4]))
        if overlap < 0.98 or delta > 0.01:
            raise RuntimeError(f"Detection differs: IoU {overlap}, confidence delta {delta}")
        unmatched.remove(index)
        matches.append(dict(label=native.names[int(row[5])], iou=overlap,
                            torch_conf=float(row[4]), onnx_conf=float(results[index, 4]), confidence_delta=delta))
    report = dict(python=platform.python_version(), gpu=torch.cuda.get_device_name(0), cuda=torch.version.cuda,
                  compute_capability=torch.cuda.get_device_capability(0),
                  packages={pkg: version(pkg) for pkg in ("torch", "torchvision", "ultralytics",
                             "opencv-python", "onnx", "onnxruntime", "numpy")},
                  weights_source="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
                  weights_sha256=sha256(weights), sample=str(sample), sample_sha256=sha256(sample),
                  onnx_sha256=sha256(exported), opset=graph.opset_import[0].version,
                  onnx_providers=providers, input_shape=shape, output_shape=session.get_outputs()[0].shape,
                  matches=matches)
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    preview = output / "bus-detections.jpg"
    if not cv2.imwrite(str(preview), native.plot()):
        raise RuntimeError(f"Could not write detection image: {preview}")
    print(f"Detection image: {preview}", flush=True)
    print(f"PASS: {len(matches)} detections, min IoU {min(m['iou'] for m in matches):.7f}, "
          f"max confidence delta {max(m['confidence_delta'] for m in matches):.7f}")

if __name__ == "__main__":
    verify()
