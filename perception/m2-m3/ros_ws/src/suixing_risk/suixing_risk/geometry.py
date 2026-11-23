"""Planar risk calculation shared by offline replay and the ROS adapter."""

from dataclasses import dataclass
from math import atan2, ceil, cos, floor, hypot, isfinite, sin, tau
from typing import Protocol, runtime_checkable


@runtime_checkable
class Coverage(Protocol):
    """Anything that can prove a planar region was observed and is unobstructed."""

    def covers(self, x: float, y: float, margin: float) -> bool: ...


@dataclass(frozen=True)
class Pose:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

    def apply(self, x, y):
        return (self.x + cos(self.yaw) * x - sin(self.yaw) * y,
                self.y + sin(self.yaw) * x + cos(self.yaw) * y)


@dataclass(frozen=True)
class Scan:
    stamp_ns: int
    lifetime_ms: int
    start_rad: float
    step_rad: float
    minimum_m: float
    maximum_m: float
    ranges: tuple
    pose: Pose = Pose()
    received_ns: int | None = None

    def hits(self):
        for index, distance in enumerate(self.ranges):
            if distance is None or not isfinite(distance) or not self.minimum_m <= distance < self.maximum_m:
                yield None
                continue
            angle = self.start_rad + index * self.step_rad
            yield self.pose.apply(distance * cos(angle), distance * sin(angle))

    def covers(self, x, y, margin):
        dx, dy = x - self.pose.x, y - self.pose.y
        offset = (atan2(dy, dx) - self.pose.yaw - self.start_rad) % tau
        index = offset / self.step_rad
        low, high = floor(index + 1e-9), ceil(index - 1e-9)
        if low < 0 or high >= len(self.ranges):
            return False
        distance = hypot(dx, dy)
        return all(
            value is not None and isfinite(value)
            and self.minimum_m <= value < self.maximum_m
            and self.minimum_m <= distance < value - margin
            for value in (self.ranges[low], self.ranges[high])
        )


@dataclass(frozen=True)
class Obstacle:
    x: float
    y: float
    radius: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    velocity_known: bool = False


@dataclass(frozen=True)
class StereoEvidence:
    stamp_ns: int
    lifetime_ms: int
    obstacles: tuple
    # Real depth gives observed free space; simulation may inject a Scan instead.
    coverage: Coverage | None = None
    received_ns: int | None = None


@dataclass(frozen=True)
class Config:
    horizon_s: float = 2.0
    step_s: float = 0.05
    danger_s: float = 1.0
    front_m: float = 0.30
    back_m: float = 0.55
    half_width_m: float = 0.30
    curvature_per_m: float = 0.55
    margin_m: float = 0.07
    sync_ns: int = 40_000_000
    caution_speed_limit_mps: float = 0.30
    semantic_min_confidence: float = 0.35
    semantic_radius_m: float = 0.35
    # Within an aligned pair, the default accepts either sensor at each probe.
    # Strict mode requires both sensors at each probe.
    require_stereo_coverage: bool = False


# Conservative footprint radii for associated semantic objects.
SEMANTIC_RADIUS_M = {"person": 0.30, "bicycle": 0.40, "motorcycle": 0.45,
                     "car": 0.90, "truck": 1.10, "bus": 1.20}


def fresh(stamp_ns, lifetime_ms, now_ns):
    return lifetime_ms is not None and 0 <= now_ns - stamp_ns < lifetime_ms * 1_000_000


def cluster(scan, gap_m=0.24, max_span_m=0.30):
    groups = []
    group = []
    for point in scan.hits():
        if point is None or (group and
                             (hypot(point[0] - group[-1][0], point[1] - group[-1][1]) > gap_m
                              or hypot(point[0] - group[0][0], point[1] - group[0][1]) > max_span_m)):
            if group:
                groups.append(group)
                group = []
        if point is not None:
            group.append(point)
    if group:
        groups.append(group)
    obstacles = []
    for group in groups:
        x = sum(p[0] for p in group) / len(group)
        y = sum(p[1] for p in group) / len(group)
        radius = max(hypot(px - x, py - y) for px, py in group)
        obstacles.append(Obstacle(x, y, radius))
    return tuple(obstacles)


def track(current, previous, elapsed_s, current_pose, previous_pose):
    if previous is None or not 0.04 <= elapsed_s <= 0.4 or current_pose is None or previous_pose is None:
        return current
    world_previous = [previous_pose.apply(p.x, p.y) for p in previous]
    world_current = [current_pose.apply(p.x, p.y) for p in current]
    candidates = sorted(
        (hypot(x - px, y - py), i, j)
        for i, (x, y) in enumerate(world_current)
        for j, (px, py) in enumerate(world_previous)
        if hypot(x - px, y - py) <= 2.5 * elapsed_s + 0.07
    )
    result = list(current)
    used_current, used_previous = set(), set()
    for _, i, j in candidates:
        if i in used_current or j in used_previous:
            continue
        x, y = world_current[i]
        dx = (x - world_previous[j][0]) / elapsed_s
        dy = (y - world_previous[j][1]) / elapsed_s
        cy, sy = cos(current_pose.yaw), sin(current_pose.yaw)
        item = current[i]
        result[i] = Obstacle(item.x, item.y, item.radius, cy * dx + sy * dy, -sy * dx + cy * dy, True)
        used_current.add(i)
        used_previous.add(j)
    return tuple(result)


def candidate_pose(speed, curvature, seconds):
    heading = speed * curvature * seconds
    if curvature == 0:
        return Pose(speed * seconds, 0.0, 0.0)
    return Pose(sin(heading) / curvature, (1 - cos(heading)) / curvature, heading)


def clearance(obstacle, pose, seconds, config):
    dx = obstacle.x + obstacle.vx * seconds - pose.x
    dy = obstacle.y + obstacle.vy * seconds - pose.y
    x = cos(pose.yaw) * dx + sin(pose.yaw) * dy
    y = -sin(pose.yaw) * dx + cos(pose.yaw) * dy
    return hypot(max(0, x - config.front_m, -config.back_m - x),
                 max(0, abs(y) - config.half_width_m)) - obstacle.radius


def sweep(obstacles, scan, stereo_coverage, speed, curvature, config, evidence_age_s):
    uncertainty = config.margin_m
    steps = ceil(config.horizon_s / config.step_s)
    nearby = any(clearance(ob, Pose(), 0.0, config) <= uncertainty for ob in obstacles)
    hit = (0.0, 0.0) if nearby else None
    if speed is None or not isfinite(speed) or speed < 0:
        return ("DANGER" if hit else "UNKNOWN"), hit, False
    covered = scan is not None or stereo_coverage is not None
    for index in range(1, steps + 1):
        seconds = min(config.horizon_s, config.step_s * index)
        pose = candidate_pose(speed, curvature, seconds)
        if hit is None:
            for obstacle in obstacles:
                # Account for relative translation and turning between two samples.
                radius = hypot(max(config.front_m, config.back_m), config.half_width_m)
                rate = speed * (1 + abs(curvature) * radius) + hypot(obstacle.vx, obstacle.vy)
                if clearance(obstacle, pose, seconds, config) <= uncertainty + rate * config.step_s:
                    hit = (round(config.step_s * (index - 1), 6), round(seconds, 6))
                    break
        if covered:
            lateral = config.half_width_m + uncertainty
            front = config.front_m + uncertainty
            probes = [pose.apply(front, y) for y in (-lateral, 0.0, lateral)]
            for x, y in probes:
                scan_ok = scan is not None and scan.covers(x, y, uncertainty)
                stereo_ok = (stereo_coverage is not None
                             and stereo_coverage.covers(x, y, uncertainty))
                ok = (scan_ok and stereo_ok) if config.require_stereo_coverage else (scan_ok or stereo_ok)
                if not ok:
                    covered = False
                    break
    if hit:
        hit = tuple(round(max(0.0, bound - evidence_age_s), 6) for bound in hit)
    if hit and hit[0] <= config.danger_s:
        return "DANGER", hit, covered
    if hit:
        return "CAUTION", hit, covered
    return ("CLEAR" if covered else "UNKNOWN"), None, covered


def semantic_obstacles(items, config):
    """Turn associated semantic evidence into extra obstacle priors.

    Semantics may only add risk: a missing or rejected entry changes nothing.
    """
    obstacles = []
    for item in items or ():
        if not isinstance(item, dict):
            continue
        label, position = item.get("label"), item.get("position_m")
        confidence = item.get("confidence")
        if (not isinstance(label, str) or not isinstance(position, (list, tuple))
                or len(position) != 3
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not isfinite(confidence) or confidence < config.semantic_min_confidence):
            continue
        try:
            x, y, z = (float(n) for n in position)
        except (TypeError, ValueError):
            continue
        if not all(isfinite(n) for n in (x, y, z)) or x <= 0 or not 0.0 <= z <= 1.6:
            continue
        extra = item.get("extra_radius_m", 0.0)
        if (type(extra) not in (int, float) or not isfinite(extra) or not 0 <= extra <= 1.5):
            continue
        obstacles.append(Obstacle(x, y, SEMANTIC_RADIUS_M.get(label, config.semantic_radius_m) + extra))
    return tuple(obstacles)


def speed_limit(risk, covered, config):
    """Advisory limit for the leader's controller. Zero means hold still."""
    if risk == "DANGER" or not covered:
        return 0.0
    if risk == "CAUTION":
        return config.caution_speed_limit_mps
    return None


def summarize(session_id, seq, now_ns, scan=None, stereo=None, speed=None, d6_tracks=None,
              config=Config(), semantic=None, *, include_directional_ttc=False):
    if scan is not None and not fresh(scan.stamp_ns, scan.lifetime_ms, now_ns):
        scan = None
    if stereo is not None and not fresh(stereo.stamp_ns, stereo.lifetime_ms, now_ns):
        stereo = None
    aligned = scan is not None and stereo is not None and abs(scan.stamp_ns - stereo.stamp_ns) <= config.sync_ns
    obstacles = ()
    semantic_list = ()
    if scan is not None:
        obstacles += cluster(scan) if d6_tracks is None else d6_tracks
    if stereo is not None:
        obstacles += stereo.obstacles
        semantic_list = semantic_obstacles(semantic, config)
        obstacles += semantic_list
    sensors = [item for item in (scan, stereo) if item is not None]
    ages_ns = [now_ns - item.stamp_ns for item in sensors]
    received_ages_ns = [now_ns - (item.received_ns if item.received_ns is not None else item.stamp_ns)
                        for item in sensors]
    oldest_s = max(ages_ns, default=0) / 1e9
    results = {
        name: sweep(obstacles, scan if aligned else None, stereo.coverage if aligned else None,
                    speed, k, config, oldest_s)
        for name, k in (("left", config.curvature_per_m), ("straight", 0.0),
                        ("right", -config.curvature_per_m))
    }
    remaining_ms = min(((item.lifetime_ms * 1_000_000 - age) // 1_000_000
                        for item, age in zip(sensors, ages_ns)), default=None)
    risk = {name: result[0] for name, result in results.items()}
    summary = {
        "session_id": session_id,
        "seq": seq,
        "sample_ns": sensors[0].stamp_ns if len(sensors) == 1 else (
            min(item.stamp_ns for item in sensors) if sensors else None),
        "risk": risk,
        "ttc_s": results["straight"][1],
        "unknown_region": any(not result[2] for result in results.values()),
        "source_age_ms": max(ages_ns) / 1e6 if ages_ns else None,
        "received_age_ms": max(received_ages_ns) / 1e6 if received_ages_ns else None,
        "valid_for_ms": remaining_ms,
        "suggested_speed_limit_mps": speed_limit(risk["straight"], results["straight"][2], config),
        "semantic_used": bool(semantic_list),
        "scan_valid": scan is not None,
        "stereo_valid": stereo is not None,
        "aligned": aligned,
    }
    if include_directional_ttc:
        summary["ttc_by_direction_s"] = {name: result[1] for name, result in results.items()}
    return summary
