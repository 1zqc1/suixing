"""Headless two-layer ray simulation for clear, crossing and dropout scenarios."""

from math import cos, sin, sqrt
import json

from .geometry import Config, Pose, Scan, StereoEvidence, cluster, summarize, track


PERIOD_NS = 100_000_000
SPEED_MPS = 0.60


def ray_scan(stamp_ns, target_xy=None, pose=Pose()):
    start = -1.3
    step = 0.02
    ranges = []
    for index in range(131):
        angle = start + index * step
        cx, sy = cos(angle), sin(angle)
        distance = (4.5 - pose.x) / cx
        if target_xy is not None:
            x, y = target_xy[0] - pose.x, target_xy[1] - pose.y
            projection = x * cx + y * sy
            cross = x * sy - y * cx
            radius = 0.14
            if abs(cross) < radius:
                hit = projection - sqrt(radius**2 - cross**2)
                if 0.04 <= hit < distance:
                    distance = hit
        ranges.append(distance)
    return Scan(stamp_ns, 140, start, step, 0.04, 20.0, tuple(ranges), pose)


def scenarios():
    stamp = 1_000_000_000
    clear = ray_scan(stamp)
    low = ray_scan(stamp, pose=Pose(0.03, 0, 0))
    stereo = StereoEvidence(stamp, 140, (), coverage=low)
    empty = summarize("sim-empty", 1, stamp, clear, stereo, speed=SPEED_MPS,
                      d6_tracks=())
    yield {"scenario": "clear", "summary": empty}

    previous_pose = Pose(-SPEED_MPS * PERIOD_NS / 1e9, 0.0)
    earlier = ray_scan(stamp - PERIOD_NS, (0.95 - previous_pose.x, 0.99))
    current = ray_scan(stamp, (0.95, 0.90))
    tracks = track(cluster(current), cluster(earlier), PERIOD_NS / 1e9, Pose(), previous_pose)
    crossing = summarize("sim-crossing", 1, stamp, current, stereo, speed=SPEED_MPS, d6_tracks=tracks)
    exact_ttc = (0.95 - Config().front_m - 0.14 - Config().margin_m) / SPEED_MPS
    yield {"scenario": "crossing", "summary": crossing, "analytical_ttc_s": exact_ttc,
           "tracked_clusters": sum(item.velocity_known for item in tracks)}

    stopped = summarize("sim-dropout", 1, stamp + 140_000_000, clear, stereo, speed=SPEED_MPS)
    yield {"scenario": "dropout", "summary": stopped}

    low_only = StereoEvidence(stamp, 140, cluster(ray_scan(stamp, (0.41, 0))),
                              coverage=low)
    hazard = summarize("sim-low-obstacle", 1, stamp, clear, low_only, speed=SPEED_MPS,
                       d6_tracks=())
    yield {"scenario": "low-obstacle", "summary": hazard}

    # Same empty geometry with one associated person: semantics may only add risk.
    semantic = [{"label": "person", "confidence": 0.90, "position_m": [1.2, 0.0, 0.90]}]
    boosted = summarize("sim-semantic", 1, stamp, clear, stereo, speed=SPEED_MPS,
                        d6_tracks=(), semantic=semantic)
    yield {"scenario": "semantic-boost", "summary": boosted}


def main():
    for row in scenarios():
        print(json.dumps(row, allow_nan=False))


if __name__ == "__main__":
    main()
