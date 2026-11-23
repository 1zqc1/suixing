import unittest
from math import hypot, pi

import numpy as np

from suixing_risk.geometry import Pose, StereoEvidence, candidate_pose, cluster
from suixing_risk.global_plan import Grid, tracking_target
from suixing_risk.navigation import LocalNavigator
from suixing_risk.simulate_avoidance import Scenario, simulated_scan


class GlobalPlanningTests(unittest.TestCase):
    def make_grid(self, wall_height, value=100):
        data = np.zeros((60, 95), dtype=np.int8)
        data[30-wall_height:30+wall_height, 40:42] = value
        return Grid(95, 60, 0.1, Pose(-2, -3), data, 0.70)

    def test_detours_and_keeps_exact_goal(self):
        grid = self.make_grid(4)
        start, goal = (0., 0.), (5., 0.)
        self.assertFalse(grid.visible(start, goal))
        route = grid.plan(start, goal)
        self.assertGreater(len(route), 2)
        self.assertEqual(route[0], start)
        self.assertEqual(route[-1], goal)
        self.assertTrue(all(grid.visible(a, b) for a, b in zip(route, route[1:])))

    def test_full_unknown_wall_and_blocked_goal(self):
        grid = self.make_grid(30, -1)
        self.assertEqual(grid.plan((0., 0.), (5., 0.)), ())
        self.assertEqual(grid.plan((0., 0.), (2.1, 0.)), ())
        self.assertEqual(grid.plan((0., 0.), (-3., 0.)), ())

    def test_rotated_origin_and_boundary(self):
        grid = Grid(20, 20, 0.1, Pose(4, 1, pi / 2), [0] * 400, 0.12)
        start, goal = grid.center((5, 5)), grid.center((12, 12))
        self.assertEqual(grid.cell(start), (5, 5))
        self.assertEqual(grid.plan(start, goal), (start, goal))
        self.assertFalse(grid.visible(start, grid.center((0, 0))))

    def test_reject_map_collision_and_allow_clear_arc(self):
        grid = self.make_grid(4)
        self.assertTrue(grid.arc_clear(Pose(), 0.25, 0.0, 3.5))
        self.assertFalse(grid.arc_clear(Pose(1.1), 0.25, 0.0, 3.5))

    def test_closed_loop_follows_global_detour(self):
        grid = self.make_grid(4)
        goal, pose = (5., 0.), Pose()
        route = grid.plan((0., 0.), goal)
        world = Scenario("map", goal, (-2.0, 7.5, -3.0, 3.0))
        navigator = LocalNavigator(0.25, 0.15)
        speed, index = 0.0, 1
        max_offset = 0.0
        for step in range(330):
            now = 1_000_000_000 + step * 100_000_000
            scan = simulated_scan(now, pose, Pose(), world)
            rays = simulated_scan(now, pose, Pose(0.03), world, stereo=True)
            stereo = StereoEvidence(now, rays.lifetime_ms, cluster(rays), coverage=rays)
            index, target = tracking_target(grid, route, index, pose, 1.2)
            self.assertIsNotNone(target)
            decision = navigator.choose(
                target, pose, speed, now, scan, stereo, None, (),
                intermediate=index < len(route) - 1,
                arc_check=lambda v, k, dt: grid.arc_clear(pose, v, k, dt))
            if decision.reason == "reached":
                break
            speed = decision.speed
            if speed:
                local = candidate_pose(speed, decision.yaw_rate / speed, 0.1)
                end = pose.apply(local.x, local.y)
                self.assertTrue(grid.visible((pose.x, pose.y), end))
                pose = Pose(*end, pose.yaw + local.yaw)
                max_offset = max(max_offset, abs(pose.y))
        self.assertGreater(max_offset, 1.0)
        self.assertLessEqual(hypot(pose.x - goal[0], pose.y - goal[1]), 0.15)
