from dataclasses import dataclass
from enum import Enum
from math import isfinite


class Source(Enum):
    D6 = "coin_d6"
    STEREO = "stereo_60mm"


class Zone(Enum):
    FORWARD = "forward"
    LEFT = "left"
    RIGHT = "right"


class Direction(Enum):
    NONE = "none"
    LEFT = "left"
    RIGHT = "right"


class Hazard(Enum):
    CLEAR = "clear"
    CAUTION = "caution"
    UNKNOWN = "unknown"
    STOP = "stop"


def finite_nonnegative(value: float) -> bool:
    return type(value) in (float, int) and isfinite(value) and value >= 0


@dataclass(frozen=True)
class Obstacle:
    """Planar occupied area. Position and relative velocity use forward/left axes."""
    x_m: float
    y_m: float
    vx_mps: float
    vy_mps: float
    radius_m: float

    def __post_init__(self):
        values = (self.x_m, self.y_m, self.vx_mps, self.vy_mps, self.radius_m)
        if not all(type(value) in (float, int) and isfinite(value) for value in values):
            raise ValueError("obstacle geometry must be finite")
        if self.radius_m < 0:
            raise ValueError("obstacle radius must be nonnegative")


@dataclass(frozen=True)
class Observation:
    source: Source
    at_s: float
    coverage: frozenset[Zone]
    obstacles: tuple[Obstacle, ...]
    valid: bool = True


@dataclass(frozen=True)
class Handle:
    at_s: float
    grip: bool
    intent: Direction
    confirm: bool
    estop: bool = False
    link_ok: bool = True
    motion_supported: bool = True


@dataclass(frozen=True)
class Scene:
    at_s: float
    forward: Hazard
    left: Hazard
    right: Hazard
    source_age_s: tuple[tuple[Source, float | None], ...]
