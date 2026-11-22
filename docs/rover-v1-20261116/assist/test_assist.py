import json
from pathlib import Path
import unittest

from suixing.contracts import (
    Direction, Handle, Hazard, Observation, Obstacle, Source, Zone,
)
from suixing.fusion import Fusion, demo_config
from suixing.replay import replay
from suixing.supervisor import Action, Feedback, Supervisor


def evidence(at, source, *obstacles, coverage=frozenset(Zone)):
    return Observation(source, at, coverage, obstacles)


class AssistTests(unittest.TestCase):
    def setUp(self):
        self.fusion = Fusion(demo_config())
        self.supervisor = Supervisor()

    def scene(self, at, speed, *obstacles, stereo=True):
        self.fusion.ingest(evidence(at, Source.D6, *obstacles), at)
        if stereo:
            self.fusion.ingest(evidence(at, Source.STEREO), at)
        return self.fusion.evaluate(at, speed)

    def step(self, at, speed=0.0, confirm=False, requested=Direction.NONE,
             pushed=Direction.NONE, grip=True, obstacles=(), stereo=True, **signals):
        scene = self.scene(at, speed, *obstacles, stereo=stereo)
        handle = Handle(at, grip, pushed, confirm, **signals)
        return self.supervisor.step(at, speed, scene, handle, requested)

    def ready(self):
        self.step(0)
        return self.step(0.05, confirm=True)

    def test_held_confirmation_at_boot_does_not_arm(self):
        self.assertEqual(self.step(0, confirm=True).action, Action.HOLD)
        self.assertEqual(self.step(0.1, confirm=True).action, Action.HOLD)
        self.assertEqual(self.step(0.2).action, Action.HOLD)
        self.assertEqual(self.step(0.3, confirm=True).action, Action.COAST)

    def test_moving_crossing_triggers_brake_and_vibration(self):
        self.ready()
        result = self.step(0.1, speed=0.5, obstacles=(Obstacle(0.9, 1.2, -1, -3, 0.1),))
        self.assertEqual((result.action, result.feedback), (Action.BRAKE, Feedback.EMERGENCY))

    def test_parallel_target_does_not_enter_corridor(self):
        scene = self.scene(0, 0.5, Obstacle(0.9, 1.2, -1, 0, 0.1))
        self.assertEqual(scene.forward, Hazard.CLEAR)

    def test_stereo_can_raise_hazard_without_lidar_agreement(self):
        self.fusion.ingest(evidence(0, Source.D6), 0)
        self.fusion.ingest(evidence(0, Source.STEREO, Obstacle(0.9, 1.2, -1, -3, 0.1)), 0)
        self.assertEqual(self.fusion.evaluate(0, 0.5).forward, Hazard.STOP)

    def test_stale_stereo_is_unknown_and_old_messages_cannot_revive_it(self):
        self.scene(0.25, 0)
        self.assertFalse(self.fusion.ingest(evidence(0.20, Source.STEREO), 0.31))
        self.assertFalse(self.fusion.ingest(evidence(0.75, Source.STEREO), 0.31))
        self.assertEqual(self.scene(0.65, 0.5, stereo=False).forward, Hazard.UNKNOWN)

    def test_partial_coverage_does_not_clear_turn(self):
        self.fusion.ingest(evidence(0, Source.D6), 0)
        self.fusion.ingest(evidence(0, Source.STEREO, coverage=frozenset({Zone.FORWARD})), 0)
        self.assertEqual(self.fusion.evaluate(0, 0).left, Hazard.UNKNOWN)

    def test_turn_requires_motion_grip_and_same_direction(self):
        self.ready()
        self.assertEqual(self.step(0.1, requested=Direction.LEFT, pushed=Direction.LEFT).action, Action.COAST)
        suggestion = self.step(0.2, speed=0.3, requested=Direction.LEFT, pushed=Direction.RIGHT)
        self.assertEqual((suggestion.action, suggestion.feedback), (Action.COAST, Feedback.LEFT))
        self.assertEqual(self.step(0.3, speed=0.3, requested=Direction.LEFT, pushed=Direction.LEFT).action, Action.TURN_LEFT)
        self.assertEqual(self.step(0.4, speed=0.3, requested=Direction.LEFT, pushed=Direction.LEFT, grip=False).action, Action.BRAKE)

    def test_brake_is_latched_until_fresh_local_confirmation_when_stopped(self):
        self.ready()
        self.step(0.1, 0.3, confirm=True, obstacles=(Obstacle(0.1, 0, 0, 0, 0.05),))
        self.assertEqual(self.step(0.2, confirm=True).action, Action.HOLD)
        self.assertEqual(self.step(0.3).action, Action.HOLD)
        self.assertEqual(self.step(0.4, speed=0.3, confirm=True).action, Action.BRAKE)
        self.assertEqual(self.step(0.5).action, Action.HOLD)
        self.assertEqual(self.step(0.6, confirm=True).action, Action.COAST)

    def test_estop_and_stale_handle_override_turn(self):
        self.ready()
        scene = self.scene(0.8, 0.3)
        result = self.supervisor.step(0.8, 0.3, scene, Handle(0, True, Direction.LEFT, False), Direction.LEFT)
        self.assertEqual(result.action, Action.BRAKE)
        result = self.step(0.9, speed=0.3, estop=True)
        self.assertEqual((result.action, result.feedback), (Action.BRAKE, Feedback.EMERGENCY))

    def test_replay_exposes_read_only_status(self):
        path = Path(__file__).parent / 'examples' / 'crossing.jsonl'
        with path.open(encoding='utf-8') as stream:
            results = list(replay(stream))
        self.assertIn('BRAKE', [row['local']['action'] for row in results])
        self.assertEqual(results[-1]['local']['action'], 'COAST')
        for row in results:
            self.assertEqual(set(row['observer']), {'at_s', 'state', 'hazard', 'reason', 'source_age_s'})
            json.dumps(row, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
