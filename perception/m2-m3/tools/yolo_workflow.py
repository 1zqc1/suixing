"""Audit a local YOLO dataset, fine-tune weights, or export and check ONNX."""

import argparse
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
from math import isfinite
from pathlib import Path
import shutil
import tempfile


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def read_names(raw):
    if isinstance(raw, Mapping):
        expected = set(range(len(raw)))
        try:
            indexed = {int(key): label for key, label in raw.items()
                       if isinstance(key, (int, str)) and not isinstance(key, bool)}
        except ValueError as error:
            raise ValueError("class IDs must start at zero and be contiguous") from error
        if set(indexed) != expected:
            raise ValueError("class IDs must start at zero and be contiguous")
        raw = [indexed[index] for index in range(len(indexed))]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("names must be a nonempty list or numbered mapping")
    if any(not isinstance(name, str) or not name or name != name.strip() for name in raw):
        raise ValueError("class names must be nonempty strings without surrounding spaces")
    if len(set(raw)) != len(raw):
        raise ValueError("class names must be unique")
    return list(raw)


def images_at(folder):
    if not folder.is_dir():
        raise ValueError(f"image directory does not exist: {folder}")
    return sorted(path for path in folder.rglob("*") if path.is_file()
                  and path.suffix.lower() in IMAGE_EXTENSIONS)


def local_path(value, base):
    if not isinstance(value, (str, Path)) or not value:
        raise ValueError("expected a local path")
    return (base / value).resolve()


def label_path(image):
    parts = list(image.parts)
    try:
        index = len(parts) - 1 - parts[::-1].index("images")
    except ValueError as error:
        raise ValueError(f"image must be inside an images/ directory: {image}") from error
    parts[index] = "labels"
    return Path(*parts).with_suffix(".txt")


def read_labels(path, n_classes):
    ids = []
    if not path.exists():
        return ids
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            index, x, y, width, height = line.split()
            index = int(index)
            x, y, width, height = map(float, (x, y, width, height))
        except ValueError as error:
            raise ValueError(f"{path}:{number}: expected class_id cx cy width height") from error
        if (not 0 <= index < n_classes or not all(isfinite(v) for v in (x, y, width, height))
                or not 0 < width <= 1 or not 0 < height <= 1
                or x - width / 2 < -1e-5 or x + width / 2 > 1 + 1e-5
                or y - height / 2 < -1e-5 or y + height / 2 > 1 + 1e-5):
            raise ValueError(f"{path}:{number}: class ID or normalized bounding box out of range")
        ids.append(index)
    return ids


def load_image(path):
    import cv2
    import numpy as np

    content = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR) if content else None
    if image is None:
        raise ValueError(f"could not decode image: {path}")
    if min(image.shape[:2]) < 10:
        raise ValueError(f"image dimensions are below 10 pixels: {path}")
    if path.suffix.lower() in (".jpg", ".jpeg") and not content.endswith(b"\xff\xd9"):
        raise ValueError(f"JPEG is missing its end marker: {path}")
    return image, hashlib.sha256(content).hexdigest()


def audit_dataset(source):
    import yaml

    source = source.resolve()
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(config, Mapping):
        raise ValueError("data YAML must contain a mapping")
    names = read_names(config.get("names"))
    if config.get("nc", len(names)) != len(names):
        raise ValueError("nc differs from the number of class names")
    root = local_path(config.get("path", "."), source.parent)
    resolved = {"path": str(root), "names": dict(enumerate(names))}
    summary = {"data_yaml": str(source), "data_yaml_sha256": file_sha256(source),
               "names": names, "splits": {}}
    seen = {}
    for split in ("train", "val", "test"):
        if split == "test" and split not in config:
            continue
        folder = local_path(config.get(split), root)
        resolved[split] = str(folder)
        images = images_at(folder)
        if not images:
            raise ValueError(f"no supported images in {split}: {folder}")
        counts = Counter()
        labels = set()
        digest = hashlib.sha256()
        negatives = unlabelled = 0
        for image in images:
            _, image_hash = load_image(image)
            prior = seen.get(image_hash)
            if prior is not None:
                raise ValueError(f"duplicate image bytes in {prior[0]} and {split}: {prior[1]}, {image}")
            seen[image_hash] = split, image
            label = label_path(image)
            if label in labels:
                raise ValueError(f"two image files use the same label path: {label}")
            labels.add(label)
            category_ids = read_labels(label, len(names))
            counts.update(category_ids)
            negatives += not category_ids
            unlabelled += not label.is_file()
            label_hash = file_sha256(label) if label.is_file() else None
            record = [image.relative_to(folder).as_posix(), image_hash, label_hash]
            digest.update(json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n")
        if split in ("train", "val") and not counts:
            raise ValueError(f"{split} needs at least one annotated object")
        if split == "train" and len(counts) != len(names):
            missing = ", ".join(name for index, name in enumerate(names) if not counts[index])
            raise ValueError(f"train has no instances of: {missing}")
        summary["splits"][split] = {
            "directory": str(folder), "images": len(images), "background_images": negatives,
            "missing_label_files": unlabelled, "sha256": digest.hexdigest(),
            "objects": {name: counts[index] for index, name in enumerate(names)},
        }
    return resolved, summary


def run_audit(args):
    _, report = audit_dataset(args.data)
    write_json(args.report, report)


def stage_training_dataset(config, destination):
    """Give Ultralytics a fresh label-cache location for each training run."""
    staged = {"path": str(destination.resolve()), "names": config["names"]}
    for split in ("train", "val", "test"):
        if split not in config:
            continue
        source = Path(config[split])
        images = destination / "images" / split
        for original in images_at(source):
            image = images / original.relative_to(source)
            image.parent.mkdir(parents=True, exist_ok=True)
            try:
                image.symlink_to(original)
            except OSError:
                shutil.copyfile(original, image)
            provided = label_path(original)
            if provided.is_file():
                target = label_path(image)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(provided, target)
        staged[split] = str(images.resolve())
    return staged


def train(args):
    from ultralytics import YOLO, __version__ as ultralytics_version
    import torch
    import yaml

    config, report = audit_dataset(args.data)
    checkpoint = check_checkpoint(args.checkpoint)
    model = YOLO(str(checkpoint), task="detect")
    args.output.mkdir(parents=True, exist_ok=False)
    dataset = args.output / "dataset.resolved.yaml"
    staged = stage_training_dataset(config, args.output / "dataset")
    dataset.write_text(yaml.safe_dump(staged, allow_unicode=True, sort_keys=False), encoding="utf-8")
    write_json(args.output / "dataset-audit.json", report)
    settings = {
        "data": str(dataset.resolve()), "imgsz": args.imgsz, "epochs": args.epochs,
        "batch": args.batch, "device": args.device, "workers": args.workers,
        "seed": args.seed, "deterministic": True, "val": True, "plots": True,
        "project": str(args.output.resolve()), "name": "train", "exist_ok": False,
    }
    write_json(args.output / "training-inputs.json", {
        "checkpoint": str(checkpoint), "checkpoint_sha256": file_sha256(checkpoint),
        "ultralytics_version": ultralytics_version, "torch_version": torch.__version__,
        "settings": settings,
    })
    model.train(**settings)
    best = args.output / "train" / "weights" / "best.pt"
    if not best.is_file():
        raise RuntimeError("training finished without a best.pt checkpoint")
    write_json(args.output / "training-result.json", {
        "best": str(best.relative_to(args.output)), "best_sha256": file_sha256(best),
    })


def check_checkpoint(path):
    if path.suffix.lower() != ".pt" or not path.is_file():
        raise ValueError(f"local PyTorch .pt checkpoint is required: {path}")
    return path.resolve()


def iou(left, right):
    x1, y1, x2, y2 = left
    a1, b1, a2, b2 = right
    overlap = max(0, min(x2, a2) - max(x1, a1)) * max(0, min(y2, b2) - max(y1, b1))
    return overlap / ((x2 - x1) * (y2 - y1) + (a2 - a1) * (b2 - b1) - overlap)


def detection_parity(reference, actual, min_iou, max_conf_delta):
    unmatched = list(actual)
    matched = 0
    for detection in reference:
        positions = [index for index, candidate in enumerate(unmatched)
                     if candidate.class_id == detection.class_id
                     and abs(candidate.confidence - detection.confidence) <= max_conf_delta]
        if positions:
            best = max(positions, key=lambda index: iou(unmatched[index].xyxy, detection.xyxy))
            if iou(unmatched[best].xyxy, detection.xyxy) >= min_iou:
                unmatched.pop(best)
                matched += 1
    return matched, matched == len(reference) == len(actual)


def raw_prediction(output, names):
    import numpy as np

    prediction = np.asarray(output)
    features = 4 + len(names)
    if prediction.ndim != 3 or prediction.shape[0] != 1:
        raise ValueError(f"expected a batch-one detection tensor, got {prediction.shape}")
    if prediction.shape[1] == features:
        prediction = prediction.transpose(0, 2, 1)
    if prediction.shape[2] != features or not np.isfinite(prediction).all():
        raise ValueError(f"invalid raw detections with shape {prediction.shape}")
    return prediction


def check_parity(checkpoint, model_path, folder, min_iou, max_conf_delta):
    """Apply the production preprocessing and decoder to both backends."""
    import numpy as np
    import torch
    from ultralytics import YOLO

    from suixing_risk.semantic import YoloV8Detector, _decode_output, _prepare_image

    detector = YoloV8Detector(model_path)
    yolo = YOLO(str(checkpoint), task="detect")
    names = read_names(yolo.names)
    metadata = detector.session.get_modelmeta().custom_metadata_map
    if "names" not in metadata or tuple(names) != detector.names:
        raise ValueError("ONNX class names differ from the checkpoint or metadata is missing")
    torch_model = yolo.model.cpu().float().eval()
    images = images_at(folder)
    if not images:
        raise ValueError(f"no parity images in {folder}")
    records = []
    with torch.inference_mode():
        for path in images:
            image, image_hash = load_image(path)
            tensor, transform = _prepare_image(image, detector.input_size, detector.dtype)
            reference = torch_model(torch.from_numpy(tensor))
            if isinstance(reference, (tuple, list)):
                reference = reference[0]
            reference = raw_prediction(reference.cpu().numpy(), names)
            actual, = detector.session.run([detector.output_name], {detector.input_name: tensor})
            actual = raw_prediction(actual, names)
            if reference.shape != actual.shape:
                raise ValueError(f"backend output shapes differ for {path}: {reference.shape}, {actual.shape}")
            decode_args = (names, image.shape, transform, detector.confidence, detector.iou)
            expected = _decode_output(reference, *decode_args)
            observed = _decode_output(actual, *decode_args)
            matched, passed = detection_parity(expected, observed, min_iou, max_conf_delta)
            records.append({
                "image": path.relative_to(folder).as_posix(), "sha256": image_hash,
                "pytorch_count": len(expected), "onnx_count": len(observed), "matched": matched,
                "largest_box_coordinate_delta_px": float(np.max(np.abs(reference[..., :4] - actual[..., :4]))),
                "largest_raw_score_delta": float(np.max(np.abs(reference[..., 4:] - actual[..., 4:]))),
                "passed": passed,
            })
    passed = all(row["passed"] for row in records) and any(row["matched"] for row in records)
    return {"passed": passed, "names": names, "input_hw": detector.input_size,
            "provider": detector.session.get_providers(), "confidence": detector.confidence,
            "nms_iou": detector.iou, "min_box_iou": min_iou, "max_conf_delta": max_conf_delta,
            "images": records}


def export(args):
    import onnx
    import onnxruntime
    import torch
    from ultralytics import YOLO, __version__ as ultralytics_version

    checkpoint = check_checkpoint(args.checkpoint)
    if args.output.exists():
        raise ValueError(f"export output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yolo-export-", dir=args.output.parent) as stage:
        copy = Path(stage).resolve() / "model.pt"
        shutil.copyfile(checkpoint, copy)
        settings = {"format": "onnx", "imgsz": args.imgsz, "batch": 1, "dynamic": False,
                    "device": "cpu", "half": False, "simplify": False, "nms": False,
                    "opset": args.opset}
        exported = Path(YOLO(str(copy), task="detect").export(**settings))
        onnx.checker.check_model(str(exported))
        parity = check_parity(copy, exported, args.images, args.min_box_iou, args.max_conf_delta)
        parity.update(checkpoint_sha256=file_sha256(copy), onnx_sha256=file_sha256(exported),
                      export=settings, ultralytics_version=ultralytics_version,
                      torch_version=torch.__version__, onnx_version=onnx.__version__,
                      onnxruntime_version=onnxruntime.__version__)
        args.output.mkdir()
        write_json(args.output / "parity.json", parity)
        if not parity["passed"]:
            raise RuntimeError(f"ONNX parity did not pass; see {args.output / 'parity.json'}")
        shutil.copyfile(exported, args.output / "model.onnx")
        write_json(args.output / "classes.json", parity["names"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    audit = commands.add_parser("audit", help="validate local splits and annotation format")
    audit.set_defaults(action=run_audit)
    audit.add_argument("--data", required=True, type=Path)
    audit.add_argument("--report", required=True, type=Path)

    training = commands.add_parser("train", help="fine-tune a local detection checkpoint")
    training.set_defaults(action=train)
    training.add_argument("--data", required=True, type=Path)
    training.add_argument("--checkpoint", required=True, type=Path)
    training.add_argument("--output", required=True, type=Path)
    training.add_argument("--imgsz", type=int, default=640)
    training.add_argument("--epochs", type=int, default=50)
    training.add_argument("--batch", type=int, default=8)
    training.add_argument("--workers", type=int, default=2)
    training.add_argument("--device", default="cpu")
    training.add_argument("--seed", type=int, default=20261123)

    exporting = commands.add_parser("export", help="export and compare ONNX with PyTorch")
    exporting.set_defaults(action=export)
    exporting.add_argument("--checkpoint", required=True, type=Path)
    exporting.add_argument("--images", required=True, type=Path)
    exporting.add_argument("--output", required=True, type=Path)
    exporting.add_argument("--imgsz", type=int, default=640)
    exporting.add_argument("--opset", type=int, default=17)
    exporting.add_argument("--min-box-iou", type=float, default=0.99)
    exporting.add_argument("--max-conf-delta", type=float, default=0.01)

    args = parser.parse_args()
    if hasattr(args, "imgsz") and (args.imgsz <= 0 or args.imgsz % 32):
        parser.error("--imgsz must be a positive multiple of 32")
    if hasattr(args, "epochs") and (args.epochs <= 0 or args.batch <= 0 or args.workers < 0):
        parser.error("--epochs and --batch must be positive and --workers nonnegative")
    if hasattr(args, "opset") and (args.opset <= 0 or not 0 < args.min_box_iou <= 1
                                    or not 0 <= args.max_conf_delta <= 1):
        parser.error("invalid opset, IoU threshold or confidence tolerance")
    try:
        args.action(args)
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
