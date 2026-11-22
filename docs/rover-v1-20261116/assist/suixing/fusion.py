from dataclasses import dataclass

from .contracts import Hazard, Observation, Scene, Source, Zone, finite_nonnegative


@dataclass(frozen=True)
class RiskConfig:
    lidar_max_age_s: float
    stereo_max_age_s: float
    reaction_s: float
    braking_mps2: float
    warning_extra_s: float
    front_extent_m: float
    rear_extent_m: float
    half_width_m: float
    turn_extra_m: float
    uncertainty_mps: float

    def __post_init__(self):
        if not all(finite_nonnegative(value) for value in vars(self).values()):
            raise ValueError("risk configuration must contain finite nonnegative values")
        if min(self.braking_mps2, self.lidar_max_age_s, self.stereo_max_age_s,
               self.front_extent_m, self.half_width_m) <= 0:
            raise ValueError("braking, freshness limits and envelope dimensions must be positive")


def demo_config() -> RiskConfig:
    """Synthetic replay thresholds only. Requires measurement before any deployment."""
    return RiskConfig(0.3, 0.3, 0.2, 1.0, 0.5, 0.35, 0.55, 0.45, 0.25, 0.15)


class Fusion:
    def __init__(self, config: RiskConfig):
        self.config = config
        self._latest: dict[Source, Observation] = {}

    def ingest(self, sample: Observation, received_s: float) -> bool:
        if not finite_nonnegative(sample.at_s) or not finite_nonnegative(received_s):
            return False
        previous = self._latest.get(sample.source)
        if sample.at_s > received_s or (previous and sample.at_s <= previous.at_s):
            return False
        self._latest[sample.source] = sample
        return True

    def evaluate(self, now_s: float, speed_mps: float) -> Scene:
        if not finite_nonnegative(now_s) or not finite_nonnegative(speed_mps):
            raise ValueError("time and rolling speed must be finite and nonnegative")
        limits = {Source.D6: self.config.lidar_max_age_s, Source.STEREO: self.config.stereo_max_age_s}
        fresh = []
        ages = []
        for source, limit in limits.items():
            sample = self._latest.get(source)
            age = now_s - sample.at_s if sample else None
            ages.append((source, age))
            if sample and sample.valid and 0 <= age <= limit:
                fresh.append((sample, age))
        risks = [self._zone_risk(zone, fresh, speed_mps) for zone in Zone]
        return Scene(now_s, *risks, tuple(ages))

    def _zone_risk(self, zone: Zone, samples, speed_mps: float) -> Hazard:
        config = self.config
        stopping_s = config.reaction_s + speed_mps / config.braking_mps2
        warning_s = stopping_s + config.warning_extra_s
        xmin = -config.rear_extent_m
        xmax = config.front_extent_m
        ymin = -config.half_width_m - (config.turn_extra_m if zone is Zone.RIGHT else 0)
        ymax = config.half_width_m + (config.turn_extra_m if zone is Zone.LEFT else 0)
        caution = False
        for sample, age in samples:
            for obstacle in sample.obstacles:
                x = obstacle.x_m + obstacle.vx_mps * age
                y = obstacle.y_m + obstacle.vy_mps * age
                margin = obstacle.radius_m + config.uncertainty_mps * (age + warning_s)
                entry_s = _first_entry(
                    ((x, obstacle.vx_mps, xmin - margin, xmax + margin),
                     (y, obstacle.vy_mps, ymin - margin, ymax + margin)),
                    warning_s,
                )
                if entry_s is not None:
                    if entry_s <= stopping_s:
                        return Hazard.STOP
                    caution = True
        # Positive evidence can stop the system even when another source is missing.
        if len(samples) != len(Source) or any(zone not in sample.coverage for sample, _ in samples):
            return Hazard.UNKNOWN
        return Hazard.CAUTION if caution else Hazard.CLEAR


def _first_entry(axes, horizon_s: float) -> float | None:
    enter, leave = 0.0, horizon_s
    for position, velocity, low, high in axes:
        if velocity == 0:
            if not low <= position <= high:
                return None
            continue
        start, end = sorted(((low - position) / velocity, (high - position) / velocity))
        enter, leave = max(enter, start), min(leave, end)
        if enter > leave:
            return None
    return enter
