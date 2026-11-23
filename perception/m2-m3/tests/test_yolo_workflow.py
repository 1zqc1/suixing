"""Training preflight and export comparison regressions."""

from importlib.util import find_spec
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from suixing_risk.semantic import Detection
from tools.yolo_workflow import audit_dataset, detection_parity, stage_training_dataset


@unittest.skipUnless(find_spec("cv2") and find_spec("yaml"), "requires OpenCV and PyYAML")
class DatasetAuditTests(unittest.TestCase):

    def setUp(self):
        import cv2
        import numpy as np

        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for split, shade in (("train", 40), ("val", 80)):
            images = self.root / "images" / split
            labels = self.root / "labels" / split
            images.mkdir(parents=True)
            labels.mkdir(parents=True)
            cv2.imwrite(str(images / "scene.png"), np.full((24, 32, 3), shade, dtype=np.uint8))
            (labels / "scene.txt").write_text("0 0.5 0.5 0.6 0.4\n", encoding="utf-8")
        self.config = self.root / "dataset.yaml"
        self.config.write_text("path: .\ntrain: images/train\nval: images/val\nnames: [person]\n",
                               encoding="utf-8")

    def test_audit_accepts_valid_splits_and_background(self):
        import cv2
        import numpy as np

        cv2.imwrite(str(self.root / "images/val/background.png"), np.zeros((24, 32, 3), dtype=np.uint8))
        resolved, report = audit_dataset(self.config)
        self.assertEqual(resolved["train"], str(self.root / "images/train"))
        self.assertEqual(report["splits"]["train"]["objects"], {"person": 1})
        self.assertEqual(report["splits"]["val"]["images"], 2)
        self.assertEqual(report["splits"]["val"]["background_images"], 1)
        self.assertEqual(report["splits"]["val"]["missing_label_files"], 1)

    def test_training_staging_uses_a_fresh_label_cache_directory(self):
        original_labels = self.root / "labels/train"
        (original_labels.parent / "train.cache").write_bytes(b"old cache")
        resolved, _ = audit_dataset(self.config)
        destination = self.root / "staged"
        staged = stage_training_dataset(resolved, destination)
        self.assertEqual(Path(staged["train"]), destination / "images/train")
        self.assertEqual((destination / "labels/train/scene.txt").read_bytes(),
                         (original_labels / "scene.txt").read_bytes())
        self.assertFalse((destination / "labels/train.cache").exists())
        self.assertEqual((original_labels.parent / "train.cache").read_bytes(), b"old cache")

    def test_audit_rejects_duplicate_image_across_train_and_val(self):
        shutil.copyfile(self.root / "images/train/scene.png", self.root / "images/val/scene.png")
        with self.assertRaisesRegex(ValueError, "duplicate image bytes in train and val"):
            audit_dataset(self.config)

    def test_audit_rejects_box_extent_outside_image(self):
        (self.root / "labels/train/scene.txt").write_text("0 0.9 0.5 0.6 0.4\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "bounding box out of range"):
            audit_dataset(self.config)

    def test_audit_rejects_invalid_image_bytes(self):
        (self.root / "images/train/scene.png").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "could not decode image"):
            audit_dataset(self.config)


class ExportParityTests(unittest.TestCase):

    def test_boxes_match_one_to_one_regardless_of_output_order(self):
        first = Detection(0, "person", 0.80, (10, 10, 20, 40))
        other = Detection(1, "bicycle", 0.60, (10, 10, 20, 40))
        self.assertEqual(detection_parity([first, other], [other, first], .99, .01), (2, True))
        self.assertEqual(detection_parity([first, other], [first, first], .99, .01), (1, False))

    def test_out_of_tolerance_confidence_and_shift_fail(self):
        original = Detection(0, "person", 0.80, (10, 10, 20, 40))
        confidence_changed = Detection(0, "person", 0.70, original.xyxy)
        shifted = Detection(0, "person", 0.80, (11, 10, 21, 40))
        self.assertEqual(detection_parity([original], [confidence_changed], .99, .01), (0, False))
        self.assertEqual(detection_parity([original], [shifted], .99, .01), (0, False))


if __name__ == "__main__":
    unittest.main()
