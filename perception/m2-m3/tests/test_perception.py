"""Adaptive disparity and stereo pipeline behaviour."""

import unittest
from importlib.util import find_spec
from unittest.mock import patch

import numpy as np

from suixing_risk.perception import (Transform, _rectification_maps, disparity_limit,
                                     disparity_map, observe_stereo, stereo_intrinsics)


def calibration(width=96, height=64, fx=80.0, cx=48.0, cy=32.0,
                baseline=0.06, right_cx=None):
    right_cx = cx if right_cx is None else right_cx
    left = {
        "width": width, "height": height,
        "p": [fx, 0.0, cx, 0.0, 0.0, fx, cy, 0.0, 0.0, 0.0, 1.0, 0.0],
        "k": [fx, 0.0, cx, 0.0, fx, cy, 0.0, 0.0, 1.0],
        "r": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "d": [0.0, 0.0, 0.0, 0.0, 0.0],
        "distortion_model": "plumb_bob",
    }
    right_p = list(left["p"])
    right_p[2] = right_cx
    right_p[3] = -fx * baseline
    return left, dict(left, p=right_p)


class DisparityLimitTest(unittest.TestCase):
    def test_near_field_is_covered(self):
        left, right = calibration(width=640, height=480, fx=533.0, cx=320.0, cy=240.0)
        self.assertEqual(disparity_limit(left, right, 0.25), 128)

    def test_cap_is_respected(self):
        left, right = calibration(width=1280, height=720, fx=1000.0, cx=640.0, cy=360.0)
        self.assertEqual(disparity_limit(left, right, 0.10), 192)

    def test_search_range_includes_rectified_principal_point_difference(self):
        left, right = calibration(cx=48.0, right_cx=44.0)
        self.assertEqual(disparity_limit(left, right, 0.4), 16)

    def test_invalid_depth_rejected(self):
        left, right = calibration()
        with self.assertRaises(ValueError):
            disparity_limit(left, right, 0.0)
        with self.assertRaises(ValueError):
            disparity_limit(left, right, 9.0)

    def test_baseline_is_read_from_projection(self):
        left, right = calibration()
        fx, _, _, _, _, baseline = stereo_intrinsics(left, right)
        self.assertEqual(fx, 80.0)
        self.assertAlmostEqual(baseline, 0.06)

    def test_missing_baseline_rejected(self):
        left, right = calibration(baseline=0.0)
        with self.assertRaises(ValueError):
            stereo_intrinsics(left, right)


class ObserveStereoTest(unittest.TestCase):
    def test_shifted_pair_recovers_depth_and_free_space(self):
        left_cal, right_cal = calibration()
        rng = np.random.default_rng(7)
        left = rng.integers(0, 256, (64, 96), dtype=np.uint8)
        right = np.roll(left, -4, axis=1)
        right[:, -4:] = 0
        transform = Transform((0.0, 0.0, 0.6), (-0.5, 0.5, -0.5, 0.5))
        evidence, metrics = observe_stereo(left, right, left_cal, right_cal,
                                           transform, 1_000, 100)
        self.assertEqual(metrics["median_disparity_px"], 4.0)
        self.assertAlmostEqual(metrics["median_depth_m"], 1.2, places=3)
        self.assertGreater(metrics["free_cells"], 0)
        self.assertIsNotNone(evidence.coverage)
        self.assertIsNone(evidence.received_ns)

    def test_explicit_disparity_overrides_auto(self):
        left_cal, right_cal = calibration()
        rng = np.random.default_rng(8)
        left = rng.integers(0, 256, (64, 96), dtype=np.uint8)
        right = np.roll(left, -4, axis=1)
        right[:, -4:] = 0
        transform = Transform((0.0, 0.0, 0.6), (-0.5, 0.5, -0.5, 0.5))
        _, metrics = observe_stereo(left, right, left_cal, right_cal, transform,
                                    1_000, 100, 6)
        self.assertEqual(metrics["max_disparity_px"], 6)

    def test_size_mismatch_rejected(self):
        left_cal, right_cal = calibration()
        transform = Transform((0.0, 0.0, 0.6), (-0.5, 0.5, -0.5, 0.5))
        with self.assertRaises(ValueError):
            observe_stereo(np.zeros((48, 96), dtype=np.uint8),
                           np.zeros((48, 96), dtype=np.uint8),
                           left_cal, right_cal, transform, 1, 100)


@unittest.skipUnless(find_spec("cv2"), "OpenCV is optional")
class OpenCVStereoTest(unittest.TestCase):
    transform = Transform((0.0, 0.0, 0.6), (-0.5, 0.5, -0.5, 0.5))

    def setUp(self):
        rng = np.random.default_rng(37)
        self.left = rng.integers(0, 256, (64, 96), dtype=np.uint8)
        self.right = np.roll(self.left, -4, axis=1)
        self.right[:, -4:] = 0

    def test_signed_reverse_agrees_with_shift_and_recovers_depth(self):
        left_cal, right_cal = calibration()
        disparity = disparity_map(self.left, self.right, 19, backend="sgbm")
        self.assertGreater(np.count_nonzero(disparity), 1_000)
        self.assertEqual(float(np.median(disparity[disparity > 0])), 4.0)
        self.assertLessEqual(float(disparity.max()), 19.0)
        evidence, metrics = observe_stereo(self.left, self.right, left_cal, right_cal,
                                           self.transform, 1_000, 100,
                                           disparity_backend="sgbm")
        self.assertAlmostEqual(metrics["median_depth_m"], 1.2, places=2)
        self.assertGreater(metrics["free_cells"], 0)
        self.assertIsNotNone(evidence.coverage)

    def test_nonpositive_or_out_of_range_disparity_cannot_prove_depth(self):
        flat = np.full(self.left.shape, 100, np.uint8)
        self.assertFalse(np.any(disparity_map(flat, flat, 24, backend="sgbm")))
        bounded = disparity_map(self.left, self.right, 2, backend="sgbm")
        self.assertLessEqual(float(bounded.max()), 2.0)

    def test_narrow_image_or_wrong_dtype_rejected(self):
        with self.assertRaisesRegex(ValueError, "too narrow"):
            disparity_map(self.left[:, :24], self.right[:, :24], 24, backend="sgbm")
        with self.assertRaisesRegex(ValueError, "uint8"):
            disparity_map(self.left.astype(np.float32), self.right, 24, backend="sgbm")

    def test_rectification_maps_reused_and_invalidated_by_calibration(self):
        import cv2

        left_cal, right_cal = calibration()
        left_cal["d"] = [0.02, 0.0, 0.0, 0.0, 0.0]
        right_cal["d"] = list(left_cal["d"])
        _rectification_maps.cache_clear()
        self.addCleanup(_rectification_maps.cache_clear)

        def process(stamp):
            return observe_stereo(self.left, self.right, left_cal, right_cal, self.transform,
                                  stamp, 100, capture_pixels=True)

        with patch.object(cv2, "initUndistortRectifyMap", wraps=cv2.initUndistortRectifyMap) as maps:
            _, first = process(1_000)
            _, second = process(2_000)
            self.assertEqual(maps.call_count, 2)
            np.testing.assert_array_equal(first["stereo_pixels"].uv, second["stereo_pixels"].uv)
            right_cal["d"][0] = 0.03
            process(3_000)
            self.assertEqual(maps.call_count, 3)

    def test_pixels_padded_by_rectification_do_not_prove_depth(self):
        left_cal, right_cal = calibration()
        right_cal["k"] = list(right_cal["k"])
        right_cal["k"][2] = 28.0
        matched = np.zeros(self.left.shape, dtype=np.uint16)
        matched[32, [10, 48]] = 4
        with patch("suixing_risk.perception.disparity_map", return_value=matched):
            _, metrics = observe_stereo(self.left, self.right, left_cal, right_cal,
                                        self.transform, 1_000, 100, capture_pixels=True)
        self.assertEqual(metrics["valid_disparity_pixels"], 1)
        np.testing.assert_array_equal(metrics["stereo_pixels"].uv, [[48, 32]])


if __name__ == "__main__":
    unittest.main()
