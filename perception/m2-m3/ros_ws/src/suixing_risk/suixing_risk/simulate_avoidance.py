"""Headless closed-loop avoidance baseline using idealized ray sensors."""

import argparse
from collections import Counter
from dataclasses import dataclass
from math import cos, hypot, sin, sqrt
import json

from .avoidance import DIRECTIONS, STOP, select_direction
from .geometry import Config, Obstacle, Pose, Scan, StereoEvidence, candidate_pose, clearance, cluster, summarize


STEP_S = 0.1
STEP_MS = 100
SPEED_MPS = 0.50
LIFETIME_MS = 140
GOAL_TOLERANCE_M = 0.18
CONFIG = Config(horizon_s=1.8, curvature_per_m=1.15)


@dataclass(frozen=True)
class Scenario:
    name: str
    goal: tuple
    bounds: tuple
    obstacles: tuple = ()
    dropout_step: int | None = None
    max_steps: int = 100


def ray_distance(origin, heading, bounds, obstacles):
    x, y = origin
    dx, dy = cos(heading), sin(heading)
    xmin, xmax, ymin, ymax = bounds
    limits = []
    for origin_m, direction, low, high in ((x, dx, xmin, xmax), (y, dy, ymin, ymax)):
        if abs(direction) > 1e-9:
            limits.append(((high if direction > 0 else low) - origin_m) / direction)
    distance = min(limits)
    for obstacle in obstacles:
        ox, oy = obstacle.x - x, obstacle.y - y
        along = ox * dx + oy * dy
        perpendicular = ox * dy - oy * dx
        inside = obstacle.radius**2 - perpendicular**2
        if inside >= 0.0:
            near = along - sqrt(inside)
            if 0.0 <= near < distance:
                distance = near
    return distance


def simulated_scan(stamp_ns, robot_pose, sensor_pose, scenario, stereo=False):
    start, step, count = (-1.22, 0.02, 123) if stereo else (-1.58, 0.02, 159)
    origin = robot_pose.apply(sensor_pose.x, sensor_pose.y)
    heading = robot_pose.yaw + sensor_pose.yaw
    ranges = tuple(ray_distance(origin, heading + start + index * step,
                                scenario.bounds, scenario.obstacles) for index in range(count))
    return Scan(stamp_ns, LIFETIME_MS, start, step, 0.03, 30.0, ranges, sensor_pose)


def move(pose, curvature, elapsed_s):
    local = candidate_pose(SPEED_MPS, curvature, elapsed_s)
    return Pose(*pose.apply(local.x, local.y), pose.yaw + local.yaw)


def measured_clearance(pose, scenario):
    """Ground truth footprint clearance, kept out of the direction selector."""
    xmin, xmax, ymin, ymax = scenario.bounds
    corners = [pose.apply(x, y) for x in (-CONFIG.back_m, CONFIG.front_m)
               for y in (-CONFIG.half_width_m, CONFIG.half_width_m)]
    wall = min(min(x - xmin, xmax - x, y - ymin, ymax - y) for x, y in corners)
    return min([wall] + [clearance(obstacle, pose, 0.0, CONFIG) for obstacle in scenario.obstacles])


def rollout(scenario):
    """Observe the world anew, choose a clear path, and advance the virtual robot."""
    pose = Pose()
    scan, stereo = None, None
    curvature = dict(straight=0.0, left=CONFIG.curvature_per_m, right=-CONFIG.curvature_per_m)
    minimum_clearance = measured_clearance(pose, scenario)
    trace = []
    reached = False
    for step in range(scenario.max_steps):
        now_ns = 1_000_000_000 + step * int(STEP_S * 1e9)
        if scenario.dropout_step is None or step < scenario.dropout_step:
            scan = simulated_scan(now_ns, pose, Pose(), scenario)
            low_scan = simulated_scan(now_ns, pose, Pose(0.03, 0.0), scenario, stereo=True)
            stereo = StereoEvidence(now_ns, LIFETIME_MS, cluster(low_scan), coverage=low_scan)
        risk = summarize(scenario.name, step + 1, now_ns, scan, stereo, speed=SPEED_MPS,
                         config=CONFIG)
        goal_x, goal_y = scenario.goal

        def distance_to_goal(next_pose):
            return hypot(next_pose.x - goal_x, next_pose.y - goal_y)

        reached = distance_to_goal(pose) <= GOAL_TOLERANCE_M
        # Lookahead ranks actions by progress. The independent risk summary authorizes each action.
        order = sorted(DIRECTIONS, key=lambda name: distance_to_goal(move(pose, curvature[name], 1.2)))
        action = STOP if reached else select_direction(risk, order, min_valid_ms=STEP_MS)
        trace.append({
            "time_s": round(step * STEP_S, 3),
            "x_m": round(pose.x, 6),
            "y_m": round(pose.y, 6),
            "yaw_rad": round(pose.yaw, 6),
            "direction": action,
            "risk": risk["risk"],
            "valid_for_ms": risk["valid_for_ms"],
            "sensor_dropout": scenario.dropout_step is not None and step >= scenario.dropout_step,
        })
        if reached:
            break
        if action != STOP:
            for substep in range(1, 11):
                probe = move(pose, curvature[action], STEP_S * substep / 10)
                minimum_clearance = min(minimum_clearance, measured_clearance(probe, scenario))
            pose = move(pose, curvature[action], STEP_S)
    counts = Counter(row["direction"] for row in trace)
    return {
        "scenario": scenario.name,
        "data_origin": "sim",
        "goal_m": {"x": scenario.goal[0], "y": scenario.goal[1]},
        "room_bounds_m": dict(zip(("x_min", "x_max", "y_min", "y_max"), scenario.bounds)),
        "obstacles": [{"x_m": obstacle.x, "y_m": obstacle.y, "radius_m": obstacle.radius}
                      for obstacle in scenario.obstacles],
        "footprint_m": {"front": CONFIG.front_m, "back": CONFIG.back_m, "half_width": CONFIG.half_width_m},
        "clearance_sample_period_s": STEP_S / 10,
        "goal_reached": reached,
        "final_pose": {"x_m": round(pose.x, 6), "y_m": round(pose.y, 6), "yaw_rad": round(pose.yaw, 6)},
        "min_clearance_m": round(minimum_clearance, 6),
        "max_lateral_offset_m": max(abs(row["y_m"]) for row in trace),
        "direction_counts": dict(counts),
        "trace": trace,
    }


def scenarios():
    """Run a bypass, an impassable corridor, and loss of both observations."""
    wide_room = (-2.0, 5.0, -2.0, 2.0)
    yield rollout(Scenario("bypass", (2.65, 0.0), wide_room, (Obstacle(1.35, 0.35, 0.12),)))
    yield rollout(Scenario("blocked", (3.65, 0.0), (-2.0, 5.0, -0.65, 0.65),
                           (Obstacle(2.0, 0.0, 0.38),), max_steps=35))
    yield rollout(Scenario("dropout", (2.65, 0.0), wide_room, dropout_step=10, max_steps=30))


def verify(results):
    for result in results:
        if result["min_clearance_m"] <= 0.0:
            raise RuntimeError(f"{result['scenario']}: simulated contact")
        for row in result["trace"]:
            direction = row["direction"]
            if direction != STOP and (row["risk"][direction] != "CLEAR"
                                      or row["valid_for_ms"] is None or row["valid_for_ms"] < STEP_MS):
                raise RuntimeError(f"{result['scenario']}: moved without fresh clearance")
    bypass, blocked, dropout = results
    if not bypass["goal_reached"] or bypass["max_lateral_offset_m"] < 0.15:
        raise RuntimeError("bypass: did not route around the obstacle and reach the goal")
    if blocked["goal_reached"] or not 0.0 < blocked["final_pose"]["x_m"] < 1.0:
        raise RuntimeError("blocked: failed to advance and then stop before the obstacle")
    if not all(row["direction"] == STOP for row in blocked["trace"][-5:]):
        raise RuntimeError("blocked: did not remain stopped")
    dropout_rows = [row for row in dropout["trace"] if row["sensor_dropout"]]
    if (not dropout_rows or all(row["valid_for_ms"] is not None for row in dropout_rows)
            or any(row["direction"] != STOP for row in dropout_rows)
            or dropout_rows[-1]["x_m"] != dropout_rows[0]["x_m"] or dropout["goal_reached"]):
        raise RuntimeError("dropout: failed to stop once observations expired")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="store_true", help="include each simulated decision in JSONL")
    args = parser.parse_args()
    results = tuple(scenarios())
    verify(results)
    for result in results:
        if not args.trace:
            result = {key: value for key, value in result.items() if key != "trace"}
        print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
