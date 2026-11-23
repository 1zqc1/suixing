"""Forward-only local goal tracking using the existing M3 swept corridors."""

from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, sin

from .geometry import Config, Pose, candidate_pose, fresh, summarize


NAV_CONFIG = Config(horizon_s=3.5, curvature_per_m=1.15)


@dataclass(frozen=True)
class Decision:
    speed: float = 0.0
    yaw_rate: float = 0.0
    reason: str = "waiting"
    valid_until_ns: int = 0
    avoiding: bool = False


def navigate(goal, measured_speed, now_ns, scan, stereo, tracks, objects, *,
             speed_limit, tolerance, config=NAV_CONFIG, preferred_turn=None, arc_check=None):
    """Evaluate in base_link. Use the exact curvature sent to the controller."""
    if goal is None or measured_speed is None or not all(
            isfinite(value) for value in (*goal, measured_speed)):
        return Decision(reason="missing_goal_or_odometry")
    distance = hypot(*goal)
    if distance <= tolerance:
        return Decision(reason="reached")
    if goal[0] <= 0:
        return Decision(reason="goal_behind")
    if not 0 <= measured_speed <= speed_limit:
        return Decision(reason="speed_out_of_bounds")
    if any(source is None or not fresh(source.stamp_ns, source.lifetime_ms, now_ns)
           for source in (scan, stereo)):
        return Decision(reason="stale_observation")

    cruise = min(speed_limit, distance / config.horizon_s)
    evaluated = {}
    for speed in (cruise, cruise / 2, cruise / 4):
        # Check the commanded arc and the distance covered before the base slows.
        speeds = (speed, measured_speed) if measured_speed > speed else (speed,)
        for trial_speed in speeds:
            if trial_speed not in evaluated:
                evaluated[trial_speed] = summarize("navigation", 0, now_ns, scan, stereo,
                                                   trial_speed, tracks, config, objects)
        summaries = [evaluated[trial_speed] for trial_speed in speeds]
        lifetime = min(summary["valid_for_ms"] for summary in summaries)
        if lifetime <= 0:
            return Decision(reason="stale_observation")
        candidates = []
        for direction, curvature in (("straight", 0.0), ("left", config.curvature_per_m),
                                     ("right", -config.curvature_per_m)):
            if any(summary["risk"][direction] != "CLEAR" for summary in summaries):
                continue
            if arc_check is not None and not arc_check(max(speeds), curvature, config.horizon_s):
                continue
            end = candidate_pose(speed, curvature, config.horizon_s)
            remaining = hypot(goal[0] - end.x, goal[1] - end.y)
            if remaining < distance:
                candidates.append((remaining, curvature, direction))
        if candidates:
            _, curvature, direction = min(candidates, key=lambda candidate: (candidate[2] != preferred_turn, candidate[0]))
            return Decision(speed, speed * curvature, direction, now_ns + lifetime * 1_000_000,
                            avoiding=direction != "straight" and "straight" not in
                            {candidate[2] for candidate in candidates})
    return Decision(reason="blocked")


def relative_goal(goal, pose: Pose):
    dx, dy = goal[0] - pose.x, goal[1] - pose.y
    return (cos(pose.yaw) * dx + sin(pose.yaw) * dy,
            -sin(pose.yaw) * dx + cos(pose.yaw) * dy)


class LocalNavigator:
    """Keep a bypass turn briefly to avoid steering back toward the obstacle."""

    def __init__(self, speed_limit, tolerance, config=NAV_CONFIG):
        self.speed_limit = speed_limit
        self.tolerance = tolerance
        self.config = config
        self.reset()

    def reset(self):
        self.turn = None
        self.turn_start_yaw = None

    def choose(self, goal, pose, measured_speed, now, scan, stereo, tracks, objects, *,
               intermediate=False, arc_check=None):
        if self.turn is not None:
            change = pose.yaw - self.turn_start_yaw
            if abs(atan2(sin(change), cos(change))) >= 0.42:
                self.reset()
        decision = navigate(relative_goal(goal, pose), measured_speed, now, scan, stereo,
                            tracks, objects, speed_limit=self.speed_limit,
                            tolerance=0.0 if intermediate else self.tolerance,
                            config=self.config, preferred_turn=self.turn, arc_check=arc_check)
        if decision.avoiding and decision.reason != self.turn:
            self.turn = decision.reason
            self.turn_start_yaw = pose.yaw
        return decision
