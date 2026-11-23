"""Associate image detections with same-frame stereo evidence for diagnostics."""

import math

import numpy as np


def scene_objects(detections, pixels):
    """Find coherent depth in each box core and report positions in base_link.

    A box can include background. This method reports supported range evidence for
    display and recording, never a drive command or proof that a region is free.
    """
    if not isinstance(detections, list):
        return []
    u, v = pixels.uv.T
    x, _, z = pixels.xyz.T
    reachable = np.isfinite(pixels.xyz).all(axis=1) & (x > 0) & (z >= 0.05) & (z <= 1.4)
    supported = []
    for detection in detections[:64]:
        if not isinstance(detection, dict):
            continue
        label, box, confidence = (detection.get(key) for key in ("label", "xyxy", "confidence"))
        if (not isinstance(label, str) or not isinstance(box, (tuple, list)) or len(box) != 4
                or not all(type(n) in (float, int) and math.isfinite(n) for n in box)
                or type(confidence) not in (float, int) or not 0 <= confidence <= 1):
            continue
        x1, y1, x2, y2 = box
        width, height = x2 - x1, y2 - y1
        if width <= 0 or height <= 0:
            continue
        core = (reachable & (u >= x1 + 0.2 * width) & (u <= x2 - 0.2 * width)
                & (v >= y1 + 0.2 * height) & (v <= y2 - 0.2 * height))
        points = pixels.xyz[core]
        if len(points) < 8:
            continue
        lower, upper = np.quantile(points[:, 0], [0.25, 0.75])
        if upper - lower > max(0.15, 0.15 * float(lower)):
            continue
        center = np.median(points, axis=0)
        supported.append({
            "label": label,
            "confidence": float(confidence),
            "xyxy": list(box),
            "position_m": [round(float(n), 3) for n in center],
            "support_pixels": len(points),
        })
    return supported
