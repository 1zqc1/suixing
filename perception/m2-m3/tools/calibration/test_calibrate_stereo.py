"""Offline calibration smoke test using rendered images with a known baseline."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np
import yaml


def write_board_pairs(root):
    size = 640, 480
    rows, cols = 6, 9
    cell_px = 50
    square_m = 0.042
    board = (np.indices((rows + 1, cols + 1)).sum(axis=0) % 2 * 255).astype(np.uint8)
    board = np.repeat(np.repeat(board, cell_px, axis=0), cell_px, axis=1)
    source = np.array([[0, 0], [board.shape[1], 0], [board.shape[1], board.shape[0]],
                       [0, board.shape[0]]], dtype=np.float32)
    target = np.array([[0, 0, 0], [cols + 1, 0, 0], [cols + 1, rows + 1, 0],
                       [0, rows + 1, 0]], dtype=np.float32) * square_m
    intrinsics = np.array([[535., 0., 326.], [0., 531., 244.], [0., 0., 1.]])
    distortion = np.zeros(5)
    rng = np.random.default_rng(512)
    with (root / "pairs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("split", "left", "right", "left_stamp_ns", "right_stamp_ns"))
        for index in range(16):
            rotation = rng.uniform(-0.32, 0.32, 3)
            translation = np.array([-0.18, -0.14, rng.uniform(0.68, 1.04)])
            translation[:2] += rng.uniform(-0.08, 0.08, 2)
            names = []
            for side, shift in (("left", 0.), ("right", -0.096)):
                corners, _ = cv2.projectPoints(target, rotation, translation + [shift, 0., 0.],
                                               intrinsics, distortion)
                mapping = cv2.getPerspectiveTransform(source, corners.reshape(4, 2))
                image = cv2.warpPerspective(board, mapping, size, borderValue=127)
                name = f"{side}_{index}.png"
                if not cv2.imwrite(str(root / name), image):
                    raise OSError(f"could not write {name}")
                names.append(name)
            timestamp = index * 100_000_000
            writer.writerow(("fit" if index < 12 else "holdout", *names,
                             timestamp, timestamp + 500_000))


class CalibrationTest(unittest.TestCase):
    def test_accepts_known_baseline_and_blocks_failed_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_board_pairs(root)
            script = Path(__file__).with_name("calibrate_stereo.py")
            command = [sys.executable, str(script), "--manifest", str(root / "pairs.csv"),
                       "--cols", "9", "--rows", "6", "--square-m", "0.042",
                       "--max-fit-rmse-px", "0.5", "--max-holdout-vertical-p95-px", "0.5",
                       "--max-holdout-rmse-px", "0.5", "--max-baseline-error-m", "0.003"]
            output = root / "fits"
            p = subprocess.run([*command, "--out", str(output), "--measured-baseline-m", "0.096"],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertTrue(report["checks_passed"])
            self.assertEqual((report["fit_count"], report["holdout_count"]), (12, 4))
            self.assertEqual(report["stamped_accepted_pairs"], 16)
            self.assertAlmostEqual(report["max_accepted_pair_skew_ms"], 0.5)
            self.assertLess(report["worst_holdout_monocular_rmse_px"], 0.5)
            self.assertGreater(report["rectified_far_field"]["horizontal_deg"], 40)
            right = yaml.safe_load((output / "right.yaml").read_text())
            p2 = right["projection_matrix"]["data"]
            self.assertEqual(right["distortion_model"], "plumb_bob")
            self.assertAlmostEqual(-p2[3] / p2[0], 0.096, delta=0.003)

            output = root / "fails"
            p = subprocess.run([*command, "--out", str(output), "--measured-baseline-m", "0.25"],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 1, p.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertFalse(report["checks"]["baseline_error"])
            self.assertFalse((output / "left.yaml").exists())
            self.assertFalse((output / "right.yaml").exists())


if __name__ == "__main__":
    unittest.main()
