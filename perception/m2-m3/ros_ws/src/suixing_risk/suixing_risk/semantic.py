"""CPU inference for raw (NMS-free) YOLOv8 detection ONNX exports."""

import argparse
import ast
from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np


COCO_NAMES = tuple(
    "person|bicycle|car|motorcycle|airplane|bus|train|truck|boat|traffic light|fire hydrant|"
    "stop sign|parking meter|bench|bird|cat|dog|horse|sheep|cow|elephant|bear|zebra|giraffe|"
    "backpack|umbrella|handbag|tie|suitcase|frisbee|skis|snowboard|sports ball|kite|baseball bat|"
    "baseball glove|skateboard|surfboard|tennis racket|bottle|wine glass|cup|fork|knife|spoon|"
    "bowl|banana|apple|sandwich|orange|broccoli|carrot|hot dog|pizza|donut|cake|chair|couch|"
    "potted plant|bed|dining table|toilet|tv|laptop|mouse|remote|keyboard|cell phone|microwave|"
    "oven|toaster|sink|refrigerator|book|clock|vase|scissors|teddy bear|hair drier|toothbrush".split("|")
)


@dataclass(frozen=True)
class Detection:
    class_id: int
    label: str
    confidence: float
    xyxy: tuple[float, float, float, float]

    def as_dict(self):
        return {"class_id": self.class_id, "label": self.label, "confidence": self.confidence, "xyxy": list(self.xyxy)}


def _class_names(names):
    if isinstance(names, Mapping):
        indexed = {int(index): label for index, label in names.items()}
        if sorted(indexed) != list(range(len(names))):
            raise ValueError("class name indices must start at zero and be contiguous")
        names = [indexed[i] for i in range(len(indexed))]
    if not isinstance(names, (list, tuple)) or not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("class names must be a nonempty list or a dictionary of labels")
    return tuple(names)


def _prepare_image(image, input_size, dtype):
    import cv2

    if image.dtype != np.uint8 or image.ndim not in (2, 3) or min(image.shape[:2]) == 0:
        raise ValueError("expected a nonempty uint8 gray or BGR image")
    if image.ndim == 2:
        rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 3:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    else:
        raise ValueError("expected exactly three channels for a color image")

    height, width = image.shape[:2]
    target_h, target_w = input_size
    scale = min(target_w / width, target_h / height)
    new_w, new_h = max(1, round(width * scale)), max(1, round(height * scale))
    x_pad, y_pad = (target_w - new_w) // 2, (target_h - new_h) // 2
    padded = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
    padded[y_pad:y_pad + new_h, x_pad:x_pad + new_w] = cv2.resize(rgb, (new_w, new_h))
    normalized = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=dtype) / dtype(255.0)
    return normalized, (x_pad, y_pad, new_w / width, new_h / height)


def _decode_output(output, names, image_shape, letterbox, confidence, iou):
    prediction = np.asarray(output)
    if prediction.ndim != 3 or prediction.shape[0] != 1:
        raise ValueError(f"expected a batch-one raw detection tensor, got {prediction.shape}")
    prediction = prediction[0]
    num_features = 4 + len(names)
    if prediction.shape[0] == num_features:
        prediction = prediction.T
    if prediction.shape[1] != num_features:
        raise ValueError(f"expected 4 box coordinates and {len(names)} class scores, got {prediction.shape}")

    probabilities = prediction[:, 4:]
    class_ids = np.argmax(np.where(np.isfinite(probabilities), probabilities, -np.inf), axis=1)
    scores = probabilities[np.arange(len(prediction)), class_ids]
    valid = ((scores >= confidence) & (scores <= 1.0) &
             np.isfinite(prediction[:, :4]).all(axis=1) & (prediction[:, 2:4] > 0).all(axis=1))
    xywh, scores, class_ids = prediction[valid, :4].astype(np.float64), scores[valid], class_ids[valid]

    width, height = image_shape[1], image_shape[0]
    x_pad, y_pad, sx, sy = letterbox
    corners = np.concatenate((xywh[:, :2] - xywh[:, 2:] / 2, xywh[:, :2] + xywh[:, 2:] / 2), axis=1)
    corners[:, 0::2] = np.clip((corners[:, 0::2] - x_pad) / sx, 0, width)
    corners[:, 1::2] = np.clip((corners[:, 1::2] - y_pad) / sy, 0, height)
    boxes_with_area = (corners[:, 2:] > corners[:, :2]).all(axis=1)
    boxes = corners[boxes_with_area]
    scores, class_ids = scores[boxes_with_area], class_ids[boxes_with_area]
    areas = np.prod(boxes[:, 2:] - boxes[:, :2], axis=1)

    # Keep score ordering stable and suppress overlaps within the same class.
    pending = np.argsort(-scores, kind="stable")[:3000]
    kept = []
    while pending.size and len(kept) < 100:
        index, pending = pending[0], pending[1:]
        kept.append(index)
        common_size = np.maximum(
            np.minimum(boxes[index, 2:], boxes[pending, 2:]) -
            np.maximum(boxes[index, :2], boxes[pending, :2]), 0.0,
        )
        intersection = np.prod(common_size, axis=1)
        overlap = intersection / (areas[index] + areas[pending] - intersection)
        pending = pending[(overlap <= iou) | (class_ids[pending] != class_ids[index])]

    return [
        Detection(int(class_ids[i]), names[class_ids[i]], float(scores[i]), tuple(float(x) for x in boxes[i]))
        for i in kept
    ]


class YoloV8Detector:
    """Run a single NCHW detection image on an ONNX Runtime CPU session."""

    def __init__(self, model_path, confidence=0.25, iou=0.45, input_size=(640, 640), class_names=None):
        import onnxruntime as ort

        if not (0.0 < confidence <= 1.0 and 0.0 <= iou <= 1.0):
            raise ValueError("confidence must be in (0, 1] and NMS IoU in [0, 1]")
        if len(input_size) != 2 or any(not isinstance(x, int) or x <= 0 for x in input_size):
            raise ValueError("input size must contain positive (height, width) integers")
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1 or len(inputs[0].shape) != 4:
            raise ValueError("expected a single-image detection model exported with nms=False")
        self.input_name, self.output_name = inputs[0].name, outputs[0].name
        shape = inputs[0].shape
        if any(isinstance(dim, int) and dim != required for dim, required in zip(shape[:2], (1, 3))):
            raise ValueError("expected a batch-one model with three NCHW color channels")
        self.input_size = tuple(
            dim if isinstance(dim, int) else default for dim, default in zip(shape[2:], input_size)
        )
        input_types = {"tensor(float)": np.float32, "tensor(float16)": np.float16}
        self.dtype = input_types.get(inputs[0].type)
        if self.dtype is None:
            raise ValueError(f"unsupported model input type {inputs[0].type}")
        metadata = self.session.get_modelmeta().custom_metadata_map
        if metadata.get("task", "detect") != "detect":
            raise ValueError("expected a YOLOv8 object detection model")
        if class_names is None:
            model_names = metadata.get("names")
            class_names = ast.literal_eval(model_names) if model_names else COCO_NAMES
        self.names = _class_names(class_names)
        self.confidence, self.iou = confidence, iou

    def detect(self, image_bgr):
        tensor, letterbox = _prepare_image(image_bgr, self.input_size, self.dtype)
        output, = self.session.run([self.output_name], {self.input_name: tensor})
        return _decode_output(output, self.names, image_bgr.shape, letterbox, self.confidence, self.iou)


def annotate_image(image_bgr, detections):
    """Return a display copy with detection classes and confidence."""
    import cv2

    image = cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR) if image_bgr.ndim == 2 else image_bgr.copy()
    for detection in detections:
        x1, y1, x2, y2 = (round(x) for x in detection.xyxy)
        color = (40, 180, 40)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        label = f"{detection.label} {detection.confidence:.2f}"
        cv2.putText(image, label, (x1, max(15, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--names", type=Path, help="JSON list or dictionary of class names")
    parser.add_argument("--output", type=Path, help="save the detection JSON")
    parser.add_argument("--annotated", type=Path, help="save an image with detection boxes")
    args = parser.parse_args()
    import cv2

    payload = np.frombuffer(args.image.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(payload, cv2.IMREAD_COLOR)
    if image is None:
        parser.error(f"could not decode image {args.image}")
    names = json.loads(args.names.read_text(encoding="utf-8")) if args.names else None
    detector = YoloV8Detector(args.model, args.confidence, args.iou, class_names=names)
    detections = detector.detect(image)
    result = json.dumps({
        "model": str(args.model), "image": str(args.image),
        "width": image.shape[1], "height": image.shape[0],
        "detections": [detection.as_dict() for detection in detections],
    }, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)
    if args.annotated:
        ok, encoded = cv2.imencode(args.annotated.suffix, annotate_image(image, detections))
        if not ok:
            parser.error(f"could not encode annotation {args.annotated}")
        args.annotated.write_bytes(encoded.tobytes())


if __name__ == "__main__":
    main()
