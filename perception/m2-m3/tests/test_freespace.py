"""Free-space evidence from stereo depth."""

import unittest
from math import nan

from suixing_risk.freespace import build_grid


class FreeSpaceGridTest(unittest.TestCase):
    def test_ray_proves_free_space(self):
        grid = build_grid([[2.0, 0.0, 0.3]], (0.0, 0.0))
        self.assertTrue(grid.covers(1.0, 0.0, 0.0))
        self.assertFalse(grid.covers(2.5, 0.0, 0.0))
        self.assertFalse(grid.covers(0.0, 1.0, 0.0))

    def test_occupied_cell_is_never_free(self):
        grid = build_grid([[1.0, 0.0, 0.3]], (0.0, 0.0))
        self.assertFalse(grid.covers(1.0, 0.0, 0.0))
        self.assertTrue(grid.occupied_near(1.0, 0.0, 0.0))

    def test_ray_stops_at_first_obstacle(self):
        grid = build_grid([[1.0, 0.0, 0.3], [2.5, 0.0, 0.3]], (0.0, 0.0))
        self.assertFalse(grid.covers(1.8, 0.0, 0.0))
        self.assertFalse(grid.covers(1.0, 0.0, 0.0))

    def test_margin_requires_neighbouring_cells(self):
        grid = build_grid([[2.0, 0.0, 0.3]], (0.0, 0.0))
        self.assertFalse(grid.covers(1.0, 0.0, 0.2))

    def test_invalid_points_are_dropped(self):
        grid = build_grid([[3.0, 0.0, 2.0], [nan, 0.0, 0.3], [-1.0, 0.0, 0.3]],
                          (0.0, 0.0))
        self.assertEqual(len(grid.free), 0)
        self.assertEqual(len(grid.occupied), 0)

    def test_empty_input(self):
        grid = build_grid([], (0.0, 0.0))
        self.assertEqual(len(grid.free), 0)
        self.assertFalse(grid.covers(0.5, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
