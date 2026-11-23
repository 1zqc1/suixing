import unittest
from math import hypot

from suixing_risk.geometry import Obstacle, Pose, StereoEvidence, candidate_pose, cluster
from suixing_risk.navigation import LocalNavigator, navigate
from suixing_risk.simulate_avoidance import Scenario, measured_clearance, simulated_scan


class NavigationTests(unittest.TestCase):
    room = (-2.0, 5.0, -2.0, 2.0)

    def observe(self, now, pose=Pose(), obstacles=()):
        world = Scenario("navigation", (2.0, 0.0), self.room, obstacles)
        scan = simulated_scan(now, pose, Pose(), world)
        rays = simulated_scan(now, pose, Pose(0.03, 0.0), world, stereo=True)
        return world, scan, StereoEvidence(now, rays.lifetime_ms, cluster(rays), coverage=rays)

    def command(self, goal, now, scan, stereo, objects=(), speed=0.0):
        return navigate(goal, speed, now, scan, stereo, None, objects,
                        speed_limit=0.25, tolerance=0.15)

    def test_goal_reached(self):
        now = 1_000_000_000
        _, scan, stereo = self.observe(now)
        result = self.command((0.09, 0.05), now, scan, stereo)
        self.assertEqual((result.speed, result.reason), (0.0, "reached"))

    def test_stale_stereo_and_missing_odometry_stop(self):
        now = 1_000_000_000
        _, _, old_stereo = self.observe(now)
        later = now + 200_000_000
        _, scan, stereo = self.observe(later)
        self.assertEqual(self.command((2, 0), later, scan, old_stereo).speed, 0)
        self.assertEqual(self.command((2, 0), later, scan, stereo, speed=None).speed, 0)

    def test_semantic_person_escalates_clear_path(self):
        now = 1_000_000_000
        _, scan, stereo = self.observe(now)
        person = {"label": "person", "position_m": [0.70, 0.0, 0.4], "confidence": 0.9}
        self.assertEqual(self.command((2, 0), now, scan, stereo).reason, "straight")
        self.assertEqual(self.command((2, 0), now, scan, stereo, [person]).reason, "blocked")

    def test_no_safe_arc_stops(self):
        now = 1_000_000_000
        _, scan, stereo = self.observe(now, obstacles=(Obstacle(0.7, 0, 0.15),))
        self.assertEqual(self.command((2, 0), now, scan, stereo).reason, "blocked")

    def test_closed_loop_bypasses_offset_obstacle(self):
        target = (2.1, 0.0)
        obstacles = (Obstacle(1.15, 0.39, 0.12),)
        pose = Pose()
        speed = 0.0
        turned = False
        navigator = LocalNavigator(0.25, 0.15)
        for step in range(400):
            now = 1_000_000_000 + step * 50_000_000
            world, scan, stereo = self.observe(now, pose, obstacles)
            result = navigator.choose(target, pose, speed, now, scan, stereo, None, ())
            if result.reason == "reached":
                break
            if not result.speed:
                speed = 0.0
                continue
            self.assertGreaterEqual(result.valid_until_ns - now, 50_000_000)
            turned |= result.yaw_rate != 0
            speed = result.speed
            delta = candidate_pose(speed, result.yaw_rate / speed, 0.05)
            pose = Pose(*pose.apply(delta.x, delta.y), pose.yaw + delta.yaw)
            self.assertGreater(measured_clearance(pose, world), 0.0)
        self.assertTrue(turned)
        self.assertLessEqual(hypot(pose.x-target[0], pose.y-target[1]), 0.15)

    def test_turn_matches_approved_arc(self):
        now = 1_000_000_000
        _, scan, stereo = self.observe(now)
        result = self.command((2, 1), now, scan, stereo)
        self.assertEqual(result.reason, "left")
        self.assertAlmostEqual(result.yaw_rate / result.speed, 1.15)
