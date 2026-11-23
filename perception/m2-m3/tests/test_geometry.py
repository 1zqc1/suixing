"""End-to-end risk decisions with real free-space evidence."""

import math
import unittest
from dataclasses import replace
from suixing_risk.freespace import build_grid
from suixing_risk.geometry import (Config, Obstacle, Pose, Scan, StereoEvidence,
                                   summarize, track)
from suixing_risk.protocol import decode, encode

STAMP = 1_000_000_000


def scan(distance=3.0, lifetime=100):
    beams = 181
    return Scan(STAMP, lifetime, -1.57, 3.14 / 180, 0.05, 4.0,
                tuple([distance] * beams), Pose())


def stereo(coverage, obstacles=(), lifetime=100, received_ns=None):
    return StereoEvidence(STAMP, lifetime, tuple(obstacles), coverage, received_ns)


def corridor(distance=3.0, spread=0.6):
    """A fan of depth rays wide enough to observe all three sweep corridors."""
    angles = [-spread + index * (2 * spread / 60) for index in range(61)]
    points = [[distance, distance * math.tan(angle), 0.30] for angle in angles]
    return build_grid(points, (0.0, 0.0))


class ClearReachabilityTest(unittest.TestCase):
    def test_real_free_space_reaches_clear(self):
        summary = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.5)
        self.assertEqual(set(summary["risk"].values()), {"CLEAR"})
        self.assertFalse(summary["unknown_region"])
        self.assertIsNone(summary["suggested_speed_limit_mps"])

    def test_no_coverage_stays_unknown(self):
        summary = summarize("s", 1, STAMP, None, stereo(None), speed=0.5)
        self.assertEqual(set(summary["risk"].values()), {"UNKNOWN"})
        self.assertEqual(summary["suggested_speed_limit_mps"], 0.0)

    def test_strict_mode_needs_both_sensors(self):
        strict = Config(require_stereo_coverage=True)
        summary = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.5,
                            config=strict)
        self.assertEqual(set(summary["risk"].values()), {"UNKNOWN"})

    def test_clear_requires_aligned_pair(self):
        limit = Config().sync_ns
        for offset, expected in ((limit, "CLEAR"), (limit + 1, "UNKNOWN")):
            with self.subTest(offset=offset):
                summary = summarize("s", 1, STAMP + offset, scan(),
                                    replace(stereo(corridor()), stamp_ns=STAMP + offset),
                                    speed=0.5)
                self.assertEqual(set(summary["risk"].values()), {expected})

    def test_obstacle_in_corridor_is_danger(self):
        summary = summarize("s", 1, STAMP, scan(),
                            stereo(corridor(), (Obstacle(1.0, 0.0, 0.05),)), speed=0.6)
        self.assertEqual(summary["risk"]["straight"], "DANGER")
        self.assertEqual(summary["suggested_speed_limit_mps"], 0.0)

    def test_caution_caps_speed(self):
        summary = summarize("s", 1, STAMP, scan(),
                            stereo(corridor(), (Obstacle(0.9, 0.0, 0.05),)), speed=0.3)
        self.assertEqual(summary["risk"]["straight"], "CAUTION")
        self.assertEqual(summary["suggested_speed_limit_mps"],
                         Config().caution_speed_limit_mps)


class SemanticEscalationTest(unittest.TestCase):
    def test_semantics_only_add_risk(self):
        base = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.6)
        self.assertEqual(base["risk"]["straight"], "CLEAR")
        objects = [{"label": "person", "confidence": 0.9, "position_m": [1.0, 0.0, 0.9]}]
        boosted = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.6,
                            semantic=objects)
        self.assertIn(boosted["risk"]["straight"], ("CAUTION", "DANGER"))
        self.assertTrue(boosted["semantic_used"])

    def test_low_confidence_is_ignored(self):
        objects = [{"label": "person", "confidence": 0.1, "position_m": [0.8, 0.0, 0.9]}]
        summary = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.6,
                            semantic=objects)
        self.assertFalse(summary["semantic_used"])
        self.assertEqual(summary["risk"]["straight"], "CLEAR")

    def test_malformed_objects_are_ignored(self):
        objects = [
            {"label": "person", "confidence": 0.9, "position_m": [float("nan"), 0.0, 0.9]},
            {"label": "person", "confidence": 0.9, "position_m": [-1.0, 0.0, 0.9]},
            {"label": "person", "confidence": 0.9},
            {"label": 3, "confidence": 0.9, "position_m": [1.0, 0.0, 0.9]},
        ]
        summary = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.6,
                            semantic=objects)
        self.assertFalse(summary["semantic_used"])

    def test_semantics_need_stereo(self):
        objects = [{"label": "person", "confidence": 0.9, "position_m": [0.8, 0.0, 0.9]}]
        summary = summarize("s", 1, STAMP, scan(), None, speed=0.6, semantic=objects)
        self.assertFalse(summary["semantic_used"])


class AgeTest(unittest.TestCase):
    def test_received_age_is_reported(self):
        delayed = stereo(corridor(), received_ns=STAMP + 20_000_000)
        summary = summarize("s", 1, STAMP + 20_000_000, scan(), delayed, speed=0.5)
        self.assertEqual(summary["source_age_ms"], 20.0)
        self.assertEqual(summary["received_age_ms"], 20.0)

    def test_stale_evidence_drops_to_unknown(self):
        summary = summarize("s", 1, STAMP + 500_000_000, scan(), stereo(corridor()), speed=0.5)
        self.assertEqual(set(summary["risk"].values()), {"UNKNOWN"})


class DirectionalTTCTest(unittest.TestCase):
    def test_clear_and_one_obstacle_per_direction(self):
        for direction, obstacle in (
                (None, None),
                ("left", Obstacle(1.2, 0.55, 0.05)),
                ("straight", Obstacle(1.6, 0.0, 0.05)),
                ("right", Obstacle(1.2, -0.55, 0.05))):
            with self.subTest(direction=direction):
                scene = stereo(corridor(), () if obstacle is None else (obstacle,))
                summary = summarize("s", 1, STAMP, scan(), scene, speed=0.6,
                                    include_directional_ttc=True)
                for candidate, interval in summary["ttc_by_direction_s"].items():
                    self.assertEqual(summary["risk"][candidate],
                                     "CAUTION" if candidate == direction else "CLEAR")
                    if candidate == direction:
                        self.assertIsNotNone(interval)
                        self.assertLess(interval[0], interval[1])
                        self.assertLessEqual(interval[1], Config().horizon_s)
                    else:
                        self.assertIsNone(interval)
                self.assertEqual(summary["ttc_s"], summary["ttc_by_direction_s"]["straight"])

    def test_interval_accounts_for_observation_age(self):
        scene = stereo(corridor(), (Obstacle(1.2, 0.55, 0.05),))
        before = summarize("s", 1, STAMP, scan(), scene, speed=0.6,
                           include_directional_ttc=True)
        after = summarize("s", 2, STAMP + 20_000_000, scan(), scene, speed=0.6,
                          include_directional_ttc=True)
        for first, second in zip(before["ttc_by_direction_s"]["left"],
                                 after["ttc_by_direction_s"]["left"]):
            self.assertAlmostEqual(first - second, 0.02)

    def test_crossing_track_corrects_for_ego_motion(self):
        config = Config()
        crossing = (Obstacle(0.95, 0.90, 0.05),)
        previous = (Obstacle(1.01, 0.99, 0.05),)
        tracked = track(crossing, previous, 0.1, Pose(), Pose(-0.06))
        self.assertTrue(tracked[0].velocity_known)
        self.assertAlmostEqual(tracked[0].vx, 0.0)
        self.assertAlmostEqual(tracked[0].vy, -0.9)
        summary = summarize("s", 1, STAMP, scan(), stereo(corridor()), speed=0.6,
                            d6_tracks=tracked, include_directional_ttc=True)
        self.assertEqual(summary["risk"]["straight"], "DANGER")
        lower, upper = summary["ttc_by_direction_s"]["straight"]
        # At first front contact the obstacle centre is within the body width.
        reference = (0.95 - config.front_m - 0.05 - config.margin_m) / 0.6
        self.assertLessEqual(upper, reference)
        self.assertLessEqual(reference - lower, 3 * config.step_s)

    def test_unavailable_speed_and_exact_expiry(self):
        scene = stereo(corridor(), (Obstacle(1.2, 0.55, 0.05),))
        for now, speed in ((STAMP, None), (STAMP + 100_000_000, 0.6)):
            with self.subTest(now=now, speed=speed):
                summary = summarize("s", 1, now, scan(), scene, speed=speed,
                                    include_directional_ttc=True)
                self.assertEqual(set(summary["risk"].values()), {"UNKNOWN"})
                self.assertEqual(summary["ttc_by_direction_s"],
                                 dict.fromkeys(("left", "straight", "right")))

    def test_wire_bytes_do_not_depend_on_optional_json_field(self):
        scene = stereo(corridor(), (Obstacle(1.6, 0.0, 0.05),))
        baseline = summarize("s", 1, STAMP, scan(), scene, speed=0.6)
        optional = summarize("s", 1, STAMP, scan(), scene, speed=0.6,
                             include_directional_ttc=True)
        self.assertNotIn("ttc_by_direction_s", baseline)
        self.assertEqual(encode(baseline, STAMP), encode(optional, STAMP))
        self.assertEqual(decode(encode(optional, STAMP))["ttc_s"], list(baseline["ttc_s"]))


if __name__ == "__main__":
    unittest.main()
