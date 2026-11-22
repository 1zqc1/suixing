from dataclasses import dataclass
from enum import Enum

from .contracts import Direction, Handle, Hazard, Scene, finite_nonnegative


class Action(Enum):
    COAST = "COAST"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    SLOW = "SLOW"
    BRAKE = "BRAKE"
    HOLD = "HOLD"


class Feedback(Enum):
    NONE = "NONE"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CAUTION = "CAUTION"
    EMERGENCY = "EMERGENCY"
    FAULT = "FAULT"


@dataclass(frozen=True)
class Decision:
    action: Action
    feedback: Feedback
    reason: str


class Supervisor:
    """Outputs a local intent only. No direct motor or remote-control interface."""

    def __init__(self, max_handle_age_s: float = 0.2, max_scene_age_s: float = 0.1):
        self._max_handle_age_s = max_handle_age_s
        self._max_scene_age_s = max_scene_age_s
        self._latched = True
        self._confirm_previous = True
        self._previous_tick_s = -1.0

    def _stop(self, rolling: bool, feedback: Feedback, reason: str) -> Decision:
        self._latched = True
        return Decision(Action.BRAKE if rolling else Action.HOLD, feedback, reason)

    def step(self, now_s: float, speed_mps: float, scene: Scene,
             handle: Handle, suggested: Direction) -> Decision:
        if not finite_nonnegative(now_s) or now_s <= self._previous_tick_s:
            self._confirm_previous = True
            return self._stop(True, Feedback.FAULT, "invalid_tick")
        self._previous_tick_s = now_s
        if not finite_nonnegative(speed_mps):
            self._confirm_previous = True
            return self._stop(True, Feedback.FAULT, "invalid_speed")
        rolling = speed_mps > 0
        handle_fresh = finite_nonnegative(handle.at_s) and 0 <= now_s - handle.at_s <= self._max_handle_age_s
        confirm_edge = handle_fresh and handle.confirm and not self._confirm_previous
        self._confirm_previous = handle.confirm if handle_fresh else True
        if handle.estop:
            return self._stop(rolling, Feedback.EMERGENCY, "hardware_estop")
        if not handle_fresh or not handle.link_ok or not handle.motion_supported:
            return self._stop(rolling, Feedback.FAULT, "local_control_unavailable")
        if not finite_nonnegative(scene.at_s) or not 0 <= now_s - scene.at_s <= self._max_scene_age_s:
            return self._stop(rolling, Feedback.FAULT, "stale_scene")
        turning = handle.intent
        turn_risk = {Direction.NONE: scene.forward, Direction.LEFT: scene.left,
                     Direction.RIGHT: scene.right}[turning]
        if Hazard.STOP in (scene.forward, turn_risk):
            return self._stop(rolling, Feedback.EMERGENCY, "predicted_intrusion")
        if Hazard.UNKNOWN in (scene.forward, turn_risk):
            return self._stop(rolling, Feedback.FAULT, "missing_coverage")
        if not handle.grip:
            return self._stop(rolling, Feedback.NONE, "grip_released")
        if self._latched:
            if (rolling or not confirm_edge or Hazard.CAUTION in (scene.forward, turn_risk)
                    or turning is not Direction.NONE):
                return self._stop(rolling, Feedback.NONE, "await_local_confirmation")
            self._latched = False
            return Decision(Action.COAST, Feedback.NONE, "local_confirmation")
        if Hazard.CAUTION in (scene.forward, turn_risk):
            return Decision(Action.SLOW if rolling else Action.COAST, Feedback.CAUTION, "approaching_risk")
        if suggested is Direction.NONE:
            return Decision(Action.COAST, Feedback.NONE, "manual_push")
        suggested_risk = scene.left if suggested is Direction.LEFT else scene.right
        if suggested_risk is not Hazard.CLEAR:
            return Decision(Action.COAST, Feedback.NONE, "turn_not_verified")
        pulse = Feedback.LEFT if suggested is Direction.LEFT else Feedback.RIGHT
        if not rolling or turning is not suggested:
            return Decision(Action.COAST, pulse, "turn_suggestion")
        action = Action.TURN_LEFT if suggested is Direction.LEFT else Action.TURN_RIGHT
        return Decision(action, pulse, "local_turn_intent")
