"""Replay normalized, synthetic fixtures on a single monotonic clock."""

import argparse
import json
from pathlib import Path

from .contracts import Direction, Handle, Observation, Obstacle, Source, Zone, finite_nonnegative
from .fusion import Fusion, demo_config
from .supervisor import Supervisor


def _flag(data, field, default=None):
    value = data.get(field, default)
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")
    return value


def replay(lines):
    fusion = Fusion(demo_config())
    supervisor = Supervisor()
    previous = -1.0
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            tick = json.loads(line)
            now = tick["at_s"]
            speed = tick["speed_mps"]
            if not finite_nonnegative(now) or now <= previous:
                raise ValueError("tick time must increase")
            previous = now
            for sample in tick["observations"]:
                observation = Observation(
                    Source(sample["source"]),
                    sample["at_s"],
                    frozenset(Zone(zone) for zone in sample["coverage"]),
                    tuple(Obstacle(*values) for values in sample["obstacles"]),
                    _flag(sample, "valid", True),
                )
                fusion.ingest(observation, now)
            data = tick["handle"]
            handle = Handle(
                data["at_s"], _flag(data, "grip"), Direction(data["intent"]),
                _flag(data, "confirm"), _flag(data, "estop"),
                _flag(data, "link_ok"), _flag(data, "motion_supported"),
            )
            scene = fusion.evaluate(now, speed)
            decision = supervisor.step(now, speed, scene, handle, Direction(tick["suggestion"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"line {line_number}: {error}") from error
        yield {
            "local": {"action": decision.action.value, "feedback": decision.feedback.value},
            "observer": {
                "at_s": now,
                "state": {
                    "BRAKE": "braking_requested", "HOLD": "hold_requested", "SLOW": "slow_requested",
                    "TURN_LEFT": "turn_assist_requested", "TURN_RIGHT": "turn_assist_requested",
                    "COAST": "manual_push",
                }[decision.action.value],
                "hazard": {"forward": scene.forward.value, "left": scene.left.value,
                           "right": scene.right.value},
                "reason": decision.reason,
                "source_age_s": {source.value: age for source, age in scene.source_age_s},
            },
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    try:
        with args.fixture.open(encoding="utf-8") as stream:
            for result in replay(stream):
                print(json.dumps(result, allow_nan=False))
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
