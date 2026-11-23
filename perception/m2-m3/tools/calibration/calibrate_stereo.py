"""Fit a horizontal stereo rig offline from paired raw chessboard images."""

import argparse
import csv
from dataclasses import dataclass
import json
from math import atan2, degrees, isfinite
from pathlib import Path

import cv2
import numpy as np
import yaml


@dataclass(frozen=True)
class Pair:
    split: str
    left: Path
    right: Path
    skew_ms: float | None


@dataclass(frozen=True)
class Corners:
    pair: Pair
    left: np.ndarray
    right: np.ndarray


def positive(value):
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite value")
    return number


def read_pairs(path):
    pairs = []
    used = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"split", "left", "right"}.issubset(reader.fieldnames or []):
            raise ValueError("manifest requires split,left,right columns")
        for row in reader:
            split = (row["split"] or "").strip()
            if split not in ("fit", "holdout"):
                raise ValueError(f"line {reader.line_num}: expected fit or holdout")
            if not (row["left"] or "").strip() or not (row["right"] or "").strip():
                raise ValueError(f"line {reader.line_num}: empty image path")
            left, right = ((path.parent / row[side].strip()).resolve() for side in ("left", "right"))
            if left == right or left in used or right in used:
                raise ValueError(f"line {reader.line_num}: repeated image")
            used.update((left, right))
            stamps = [(row.get(key) or "").strip() for key in ("left_stamp_ns", "right_stamp_ns")]
            if any(stamps) and not all(stamps):
                raise ValueError(f"line {reader.line_num}: supply both timestamps or neither")
            skew_ms = None
            if all(stamps):
                first, second = map(int, stamps)
                if min(first, second) < 0:
                    raise ValueError(f"line {reader.line_num}: negative timestamp")
                skew_ms = abs(first - second) / 1e6
            pairs.append(Pair(split, left, right, skew_ms))
    return pairs


def load_corners(pairs, pattern, max_skew_ms):
    accepted = {"fit": [], "holdout": []}
    rejected = []
    image_size = None
    for pair in pairs:
        if pair.skew_ms is not None and pair.skew_ms > max_skew_ms:
            rejected.append(dict(left=str(pair.left), right=str(pair.right), reason="timestamp skew"))
            continue
        flags = cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION
        left, right = [cv2.imread(str(path), flags) for path in (pair.left, pair.right)]
        if left is None or right is None:
            rejected.append(dict(left=str(pair.left), right=str(pair.right), reason="image unreadable"))
            continue
        if left.shape != right.shape or (image_size is not None and left.shape[::-1] != image_size):
            raise ValueError(f"mixed image sizes at {pair.left} and {pair.right}")
        found_left, points_left = cv2.findChessboardCornersSB(left, pattern)
        found_right, points_right = cv2.findChessboardCornersSB(right, pattern)
        if not (found_left and found_right):
            rejected.append(dict(left=str(pair.left), right=str(pair.right), reason="board not found"))
            continue
        image_size = left.shape[::-1]
        # The detector can traverse a rectangular board from either end. The two
        # cameras are forward-facing with matching pixel axes.
        cols, rows = pattern
        left_grid = points_left.reshape(rows, cols, 2)
        right_grid = points_right.reshape(rows, cols, 2)
        across = np.dot(left_grid[0, -1] - left_grid[0, 0], right_grid[0, -1] - right_grid[0, 0])
        down = np.dot(left_grid[-1, 0] - left_grid[0, 0], right_grid[-1, 0] - right_grid[0, 0])
        if across < 0 and down < 0:
            points_right = points_right[::-1].copy()
        elif across <= 0 or down <= 0:
            rejected.append(dict(left=str(pair.left), right=str(pair.right), reason="corner orientation"))
            continue
        accepted[pair.split].append(Corners(pair, points_left, points_right))
    if len(accepted["fit"]) < 10 or len(accepted["holdout"]) < 3:
        raise ValueError(
            f"need at least 10 fit and 3 holdout detections, found "
            f"{len(accepted['fit'])} fit and {len(accepted['holdout'])} holdout "
            f"with {len(rejected)} rejected pairs"
        )
    return accepted, rejected, image_size


def board_points(pattern, square_m):
    cols, rows = pattern
    points = np.zeros((cols * rows, 3), dtype=np.float32)
    points[:, :2] = np.mgrid[:cols, :rows].T.reshape(-1, 2) * square_m
    return points


def camera_info(name, size, intrinsic, distortion, rotation, projection):
    def matrix(array):
        return dict(rows=array.shape[0], cols=array.shape[1], data=array.flatten().tolist())

    return dict(
        image_width=size[0], image_height=size[1], camera_name=name,
        camera_matrix=matrix(intrinsic), distortion_model="plumb_bob",
        distortion_coefficients=matrix(distortion.reshape(1, -1)),
        rectification_matrix=matrix(rotation), projection_matrix=matrix(projection),
    )


def heldout_projection_rmse(board, corners, intrinsic, distortion):
    ok, rotation, translation = cv2.solvePnP(board, corners, intrinsic, distortion)
    if not ok:
        raise ValueError("holdout pose estimation failed")
    projection, _ = cv2.projectPoints(board, rotation, translation, intrinsic, distortion)
    residual = corners.reshape(-1, 2) - projection.reshape(-1, 2)
    return float(np.sqrt(np.mean(np.sum(residual ** 2, axis=-1))))


def heldout_metrics(board, pairs, left_cam, right_cam):
    results = []
    vertical_errors = []
    for sample in pairs:
        left = cv2.undistortPoints(sample.left, *left_cam[:2], R=left_cam[2], P=left_cam[3])
        right = cv2.undistortPoints(sample.right, *right_cam[:2], R=right_cam[2], P=right_cam[3])
        vertical = np.abs(left.reshape(-1, 2)[:, 1] - right.reshape(-1, 2)[:, 1])
        vertical_errors.extend(vertical)
        results.append(dict(
            left=str(sample.pair.left), right=str(sample.pair.right), skew_ms=sample.pair.skew_ms,
            vertical_p95_px=float(np.percentile(vertical, 95)),
            left_reprojection_rmse_px=heldout_projection_rmse(board, sample.left, *left_cam[:2]),
            right_reprojection_rmse_px=heldout_projection_rmse(board, sample.right, *right_cam[:2]),
        ))
    return float(np.percentile(vertical_errors, 95)), results


def common_field_of_view(left_roi, right_roi, projection):
    x0 = max(left_roi[0], right_roi[0])
    y0 = max(left_roi[1], right_roi[1])
    x1 = min(left_roi[0] + left_roi[2], right_roi[0] + right_roi[2])
    y1 = min(left_roi[1] + left_roi[3], right_roi[1] + right_roi[3])
    if x1 <= x0 or y1 <= y0:
        raise ValueError("rectified images have no common valid rectangle")

    def angle(low, high, center, focal):
        return degrees(atan2(high - center, focal) - atan2(low - center, focal))

    return dict(
        common_roi_xywh=[x0, y0, x1 - x0, y1 - y0],
        horizontal_deg=angle(x0, x1 - 1, projection[0, 2], projection[0, 0]),
        vertical_deg=angle(y0, y1 - 1, projection[1, 2], projection[1, 1]),
    )


def calibrate(args):
    pairs = read_pairs(args.manifest)
    pattern = args.cols, args.rows
    accepted, rejected, size = load_corners(pairs, pattern, args.max_pair_skew_ms)
    board = board_points(pattern, args.square_m)
    fit = accepted["fit"]
    objects = [board for _ in fit]
    left, right = [sample.left for sample in fit], [sample.right for sample in fit]
    left_rmse, k1, d1, _, _ = cv2.calibrateCamera(objects, left, size, None, None)
    right_rmse, k2, d2, _, _ = cv2.calibrateCamera(objects, right, size, None, None)
    stereo_rmse, k1, d1, k2, d2, rotation, translation, _, _ = cv2.stereoCalibrate(
        objects, left, right, k1, d1, k2, d2, size, flags=cv2.CALIB_FIX_INTRINSIC,
    )
    r1, r2, p1, p2, _, roi1, roi2 = cv2.stereoRectify(
        k1, d1, k2, d2, size, rotation, translation, flags=cv2.CALIB_ZERO_DISPARITY, alpha=0,
    )
    baseline_m = float(-p2[0, 3] / p2[0, 0])
    if not 0 < baseline_m < 1:
        raise ValueError("expected horizontal left-to-right rig with baseline between 0 and 1 m")
    left_cam, right_cam = (k1, d1, r1, p1), (k2, d2, r2, p2)
    vertical_p95, holdout = heldout_metrics(board, accepted["holdout"], left_cam, right_cam)
    worst_vertical_p95 = max(sample["vertical_p95_px"] for sample in holdout)
    worst_reprojection = max(max(sample["left_reprojection_rmse_px"],
                                 sample["right_reprojection_rmse_px"]) for sample in holdout)
    checks = {}
    if args.max_fit_rmse_px is not None:
        checks["stereo_fit_rmse"] = stereo_rmse <= args.max_fit_rmse_px
    if args.max_holdout_vertical_p95_px is not None:
        checks["holdout_vertical_p95"] = worst_vertical_p95 <= args.max_holdout_vertical_p95_px
    if args.max_holdout_rmse_px is not None:
        checks["holdout_reprojection_rmse"] = worst_reprojection <= args.max_holdout_rmse_px
    if args.measured_baseline_m is not None:
        checks["baseline_error"] = abs(baseline_m - args.measured_baseline_m) <= args.max_baseline_error_m
    skews = [s.pair.skew_ms for group in accepted.values() for s in group if s.pair.skew_ms is not None]
    report = dict(
        image_size=list(size), board_inner_corners=list(pattern), square_size_m=args.square_m,
        fit_count=len(fit), holdout_count=len(holdout), rejected_pairs=rejected,
        left_fit_rmse_px=left_rmse, right_fit_rmse_px=right_rmse, stereo_fit_rmse_px=stereo_rmse,
        holdout_vertical_p95_px=vertical_p95, worst_holdout_vertical_p95_px=worst_vertical_p95,
        worst_holdout_monocular_rmse_px=worst_reprojection, holdout=holdout, baseline_m=baseline_m,
        right_from_left_rotation=rotation.tolist(), right_from_left_translation_m=translation.ravel().tolist(),
        rectified_far_field=common_field_of_view(roi1, roi2, p1),
        stamped_accepted_pairs=len(skews), max_accepted_pair_skew_ms=max(skews, default=None),
        limits=dict(max_pair_skew_ms=args.max_pair_skew_ms, max_fit_rmse_px=args.max_fit_rmse_px,
                    max_holdout_vertical_p95_px=args.max_holdout_vertical_p95_px,
                    max_holdout_rmse_px=args.max_holdout_rmse_px,
                    measured_baseline_m=args.measured_baseline_m, max_baseline_error_m=args.max_baseline_error_m),
        checks=checks, checks_passed=all(checks.values()) if checks else None,
    )
    return report, camera_info(args.left_name, size, *left_cam), camera_info(args.right_name, size, *right_cam)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--cols", type=int, required=True, help="number of inner corners per row")
    parser.add_argument("--rows", type=int, required=True, help="number of inner corners per column")
    parser.add_argument("--square-m", type=positive, required=True)
    parser.add_argument("--left-name", default="left_camera")
    parser.add_argument("--right-name", default="right_camera")
    parser.add_argument("--max-pair-skew-ms", type=positive, default=5.0)
    parser.add_argument("--max-fit-rmse-px", type=positive)
    parser.add_argument("--max-holdout-vertical-p95-px", type=positive,
                        help="limit applied to the worst per-image held-out vertical P95")
    parser.add_argument("--max-holdout-rmse-px", type=positive,
                        help="limit applied to the worst held-out monocular reprojection RMSE")
    parser.add_argument("--measured-baseline-m", type=positive)
    parser.add_argument("--max-baseline-error-m", type=positive)
    args = parser.parse_args()
    if min(args.cols, args.rows) < 3 or args.rows == args.cols:
        parser.error("a rectangular board with unequal inner-corner counts of at least 3 is required")
    if (args.measured_baseline_m is None) != (args.max_baseline_error_m is None):
        parser.error("supply the measured baseline and its error limit together")
    if args.left_name == args.right_name:
        parser.error("left and right camera names must differ")
    if args.out.exists():
        parser.error(f"output path already exists: {args.out}")
    try:
        report, left_info, right_info = calibrate(args)
        report_json = json.dumps(report, indent=2, allow_nan=False)
        args.out.mkdir(parents=True)
        (args.out / "report.json").write_text(report_json + "\n", encoding="utf-8")
        if report["checks_passed"] is False:
            print(f"Calibration checks failed. See {args.out / 'report.json'}")
            return 1
        for filename, info in (("left.yaml", left_info), ("right.yaml", right_info)):
            (args.out / filename).write_text(
                yaml.safe_dump(info, sort_keys=False), encoding="utf-8",
            )
    except (ValueError, OSError, cv2.error) as error:
        parser.error(str(error))
    print(f"Stereo calibration written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
