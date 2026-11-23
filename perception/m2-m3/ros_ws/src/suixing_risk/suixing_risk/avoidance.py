"""Select a locally clear direction for a simulation or advisory display."""

from collections.abc import Mapping
from math import isfinite


DIRECTIONS = ("straight", "left", "right")
STOP = "stop"


def select_direction(summary, preference=DIRECTIONS, *, min_valid_ms=0):
    """Select from a freshly evaluated summary, with enough lifetime for the consumer."""
    lifetime_ms = summary.get("valid_for_ms")
    if (isinstance(lifetime_ms, bool) or not isinstance(lifetime_ms, (int, float))
            or not isfinite(lifetime_ms) or lifetime_ms <= 0 or lifetime_ms < min_valid_ms):
        return STOP

    risk = summary.get("risk")
    if not isinstance(risk, Mapping):
        return STOP

    for direction in preference:
        if direction in DIRECTIONS and risk.get(direction) == "CLEAR":
            return direction
    return STOP
