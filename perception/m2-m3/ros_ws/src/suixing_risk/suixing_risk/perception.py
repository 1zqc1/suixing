"""Stereo measurements and transforms used by both adapters."""

from dataclasses import dataclass
from functools import lru_cache
from math import atan2, ceil, isfinite

import numpy as np

from .freespace import build_grid
from .geometry import Obstacle, Pose, Scan, StereoEvidence


@dataclass(frozen=True)
class Transform:
    translation: tuple
    rotation_xyzw: tuple

    def matrix(self):
        q = np.asarray(self.rotation_xyzw, dtype=float)
        length = np.linalg.norm(q)
        if not np.isfinite(length) or length < 1e-10 or not np.isfinite(self.translation).all():
            raise ValueError("invalid TF translation or quaternion")
        x, y, z, w = q / length
        return np.array([
            [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
            [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
            [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
        ])

    def planar_pose(self):
        matrix = self.matrix()
        if abs(matrix[2, 2] - 1.0) > 0.01:
            raise ValueError("D6 scan plane must be horizontal for M1")
        return Pose(*self.translation[:2], atan2(matrix[1, 0], matrix[0, 0]))


@dataclass(frozen=True)
class StereoPixels:
    """Valid stereo points with their corresponding raw left-image pixels."""
    width: int
    height: int
    uv: np.ndarray
    xyz: np.ndarray


def scan_from_values(stamp, lifetime, start, increment, minimum, maximum, ranges, transform,
                     received_ns=None):
    if (not all(isfinite(v) for v in (start, increment, minimum, maximum))
            or increment <= 0 or not 0 < minimum < maximum or not ranges):
        raise ValueError("invalid D6 scan geometry")
    return Scan(stamp, lifetime, start, increment, minimum, maximum, tuple(ranges),
                transform.planar_pose(), received_ns)


def _matching_cost(left, right, disparity, reverse):
    # Compare only pixels that are within both images, including the 5x5 window.
    width = left.shape[1]
    difference = np.full(left.shape, 255, dtype=np.float32)
    if reverse:
        difference[:, :width-disparity] = np.abs(left[:, :width-disparity] - right[:, disparity:])
    else:
        difference[:, disparity:] = np.abs(left[:, disparity:] - right[:, :width-disparity])
    integral = np.pad(difference, ((1, 0), (1, 0))).cumsum(axis=0, dtype=np.int64).cumsum(axis=1)
    cost = np.full(left.shape, np.inf, dtype=np.float32)
    cost[2:-2, 2:-2] = integral[5:, 5:] - integral[:-5, 5:] - integral[5:, :-5] + integral[:-5, :-5]
    if reverse:
        cost[:, width-disparity-2:] = np.inf
    else:
        cost[:, :disparity+2] = np.inf
    return cost


def _match(left, right, max_disparity, reverse=False):
    best = np.full(left.shape, np.inf, dtype=np.float32)
    alternate = best.copy()
    disparity = np.zeros(left.shape, dtype=np.uint16)
    for offset in range(1, max_disparity + 1):
        cost = _matching_cost(left, right, offset, reverse)
        better = cost < best
        alternate = np.where(better, best, np.minimum(alternate, cost))
        best = np.minimum(cost, best)
        disparity[better] = offset
    unique = (alternate > best * 1.12 + 2.0) & (best <= 25 * 35)
    disparity[~unique] = 0
    return disparity


def _sgbm_disparity(left, right, limit):
    """Return positive subpixel disparities with a signed right-to-left check."""
    import cv2

    if left.dtype != np.uint8 or right.dtype != np.uint8:
        raise ValueError("SGBM requires mono uint8 images")
    block_size = 5
    # OpenCV requires a multiple of 16. Search zero too so it can be rejected
    # instead of forcing the best positive match, then enforce the caller's cap.
    count = ceil((limit + 1) / 16) * 16
    width = left.shape[1]
    if width <= count + block_size // 2:
        raise ValueError("image too narrow for SGBM search range")

    settings = dict(numDisparities=count, blockSize=block_size,
                    P1=8 * block_size**2, P2=32 * block_size**2,
                    uniquenessRatio=12)
    try:
        forward = cv2.StereoSGBM_create(minDisparity=0, **settings).compute(left, right)
        reverse = cv2.StereoSGBM_create(minDisparity=1-count, **settings).compute(right, left)
    except cv2.error as error:
        raise ValueError("OpenCV SGBM matching failed") from error
    # StereoSGBM stores disparities as signed fixed-point values at 1/16 px.
    forward = forward.astype(np.float32) / 16
    reverse = reverse.astype(np.float32) / 16
    yy, xx = np.indices(left.shape)
    right_x = np.rint(xx - forward).astype(np.int32)
    other = reverse[yy, np.clip(right_x, 0, width - 1)]
    valid = ((forward > 0) & (forward <= limit) & (right_x >= 0) & (right_x < width)
             & (other < 0) & (other >= -limit) & (np.abs(forward + other) <= 1))
    return np.where(valid, forward, np.float32(0))


def disparity_map(left, right, max_disparity=24, *, backend="sad"):
    if left.shape != right.shape or left.ndim != 2 or min(left.shape) < 8:
        raise ValueError("stereo images must be matching mono arrays")
    limit = min(max_disparity, left.shape[1] - 5)
    if limit < 2:
        raise ValueError("stereo search range too small")
    if backend == "sgbm":
        return _sgbm_disparity(left, right, limit)
    if backend != "sad":
        raise ValueError(f"unknown disparity backend: {backend}")
    left, right = left.astype(np.float32), right.astype(np.float32)
    forward = _match(left, right, limit)
    reverse = _match(right, left, limit, reverse=True)
    yy, xx = np.indices(left.shape)
    other = reverse[yy, np.maximum(0, xx - forward)].astype(np.int32)
    return np.where((forward > 0) & (other > 0) &
                    (np.abs(other - forward.astype(np.int32)) <= 1), forward, 0)


def stereo_intrinsics(left_cal, right_cal):
    """Projection terms and baseline in metres for a rectified pair."""
    projection = np.array(left_cal["p"], dtype=float).reshape((3, 4))
    right_projection = np.array(right_cal["p"], dtype=float).reshape((3, 4))
    if not np.isfinite(projection).all() or not np.isfinite(right_projection).all():
        raise ValueError("projection contains non-finite values")
    fx, fy = projection[0, 0], projection[1, 1]
    if fx <= 0 or fy <= 0 or right_projection[0, 0] <= 0:
        raise ValueError("missing rectified projection")
    baseline = -right_projection[0, 3] / right_projection[0, 0]
    if not 0 < baseline < 1:
        raise ValueError("missing stereo baseline in right projection")
    return fx, fy, projection[0, 2], projection[1, 2], right_projection[0, 2], baseline


def disparity_limit(left_cal, right_cal, min_depth_m, cap=192):
    """Largest useful disparity for the nearest depth the caller cares about."""
    if not 0.05 <= min_depth_m <= 5.0:
        raise ValueError("min_depth_m must be within the supported stereo range")
    fx, _, cx, _, right_cx, baseline = stereo_intrinsics(left_cal, right_cal)
    width = int(left_cal["width"])
    return max(2, min(cap, width - 5, ceil(fx * baseline / min_depth_m + cx - right_cx)))


@lru_cache(maxsize=4)
def _rectification_maps(width, height, model, intrinsic, distortion, rotation, projection):
    intrinsic = np.asarray(intrinsic).reshape(3, 3)
    rotation = np.asarray(rotation).reshape(3, 3)
    target = np.asarray(projection).reshape(3, 4)[:, :3]
    distortion = np.asarray(distortion)
    if not all(np.isfinite(a).all() for a in (intrinsic, distortion, rotation, target)):
        raise ValueError("rectification calibration contains non-finite values")
    if not np.any(distortion) and np.allclose(rotation, np.eye(3)) and np.allclose(intrinsic, target):
        return None
    if model not in ("plumb_bob", "rational_polynomial"):
        raise ValueError("unsupported camera distortion model")
    import cv2
    try:
        return cv2.initUndistortRectifyMap(intrinsic, distortion, rotation, target,
                                           (width, height), cv2.CV_32FC1)
    except cv2.error as error:
        raise ValueError("OpenCV stereo rectification failed") from error


def _rectify(image, calibration):
    height, width = image.shape
    terms = (tuple(np.asarray(calibration[field], dtype=float).reshape(-1))
             for field in ("k", "d", "r", "p"))
    maps = _rectification_maps(width, height,
                               calibration.get("distortion_model", "plumb_bob"), *terms)
    if maps is None:
        return image, None
    import cv2
    try:
        return cv2.remap(image, *maps, cv2.INTER_LINEAR), maps
    except cv2.error as error:
        raise ValueError("OpenCV stereo rectification failed") from error


def _within_raw_image(maps, rows, cols, width, height):
    raw_x, raw_y = (image_map[rows, cols] for image_map in maps)
    return (raw_x >= 0) & (raw_x <= width - 1) & (raw_y >= 0) & (raw_y <= height - 1)


def observe_stereo(left, right, left_cal, right_cal, transform, stamp_ns, lifetime_ms,
                   max_disparity=None, min_depth_m=0.25, received_ns=None, *,
                   capture_pixels=False, max_disparity_cap=192, disparity_backend="sad"):
    for image, calibration in ((left, left_cal), (right, right_cal)):
        if image.shape != (calibration["height"], calibration["width"]):
            raise ValueError("stereo calibration and image dimensions differ")
    fx, fy, cx, cy, right_cx, baseline = stereo_intrinsics(left_cal, right_cal)
    if max_disparity is None:
        max_disparity = disparity_limit(left_cal, right_cal, min_depth_m, max_disparity_cap)
    width = left.shape[1]
    max_disparity = max(2, min(int(max_disparity), width - 5))

    left_rect, left_maps = _rectify(left, left_cal)
    right_rect, right_maps = _rectify(right, right_cal)
    disparity = disparity_map(left_rect, right_rect, max_disparity, backend=disparity_backend)
    vv, uu = np.nonzero(disparity)
    offsets = disparity[vv, uu]
    denominator = offsets - (cx - right_cx)
    valid = denominator > 0
    # Padded pixels created by rectification do not provide depth or free space.
    if left_maps is not None:
        valid &= _within_raw_image(left_maps, vv, uu, width, left.shape[0])
    if right_maps is not None:
        right_x = np.rint(uu - offsets).astype(np.intp)
        valid &= _within_raw_image(right_maps, vv, right_x, width, right.shape[0])
    vv, uu, denominator = vv[valid], uu[valid], denominator[valid]
    with np.errstate(over="ignore"):
        depth = fx * baseline / denominator
    selected = (depth >= 0.12) & (depth <= 5.0)
    usable_depth = depth[selected]
    points = np.column_stack(((uu[selected] - cx) * usable_depth / fx,
                              (vv[selected] - cy) * usable_depth / fy, usable_depth))
    rotation = np.asarray(left_cal["r"]).reshape((3, 3))
    projected = points @ rotation @ transform.matrix().T + transform.translation
    # Reduce occupied evidence to 10 cm bins for the planar sweep.
    occupied = {}
    for x, y, z in projected:
        if x <= 0 or not 0.05 <= z <= 1.4:
            continue
        cell = (int(np.floor(x * 10)), int(np.floor(y * 10)))
        if cell not in occupied:
            occupied[cell] = Obstacle((cell[0] + 0.5) * 0.1, (cell[1] + 0.5) * 0.1, 0.071)
    # Depth rays also prove where space is free, which is what makes CLEAR reachable.
    coverage = build_grid(projected, transform.translation[:2])
    stats = {
        "valid_disparity_pixels": int(vv.size),
        "median_disparity_px": float(np.median(disparity[vv, uu])) if vv.size else None,
        "median_depth_m": float(np.median(usable_depth)) if usable_depth.size else None,
        "usable_depth_pixels": int(usable_depth.size),
        "occupied_bins": len(occupied),
        "free_cells": len(coverage.free),
        "max_disparity_px": int(max_disparity),
    }
    if capture_pixels:
        u, v = uu[selected], vv[selected]
        if left_maps is not None:
            u, v = left_maps[0][v, u], left_maps[1][v, u]
        # Bound the optional cloud copied into the frame-matching cache.
        stride = max(1, (len(projected) + 59_999) // 60_000)
        stats["stereo_pixels"] = StereoPixels(left.shape[1], left.shape[0],
                                              np.column_stack((u, v))[::stride].copy(),
                                              projected[::stride].copy())
    return StereoEvidence(stamp_ns, lifetime_ms, tuple(occupied.values()), coverage,
                          received_ns), stats
