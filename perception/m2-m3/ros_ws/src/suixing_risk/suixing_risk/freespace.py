"""Observed free space from corrected stereo depth, expressed in base_link.

The grid records only cells a depth ray actually travelled through. A cell with
no evidence stays unknown, so a missing return can never be read as free space.
"""

from dataclasses import dataclass
from math import floor, hypot, isfinite
import numpy as np

CELL_M = 0.10
MIN_HEIGHT_M = 0.05
MAX_HEIGHT_M = 1.40
MAX_RAY_POINTS = 3000


@dataclass(frozen=True)
class FreeSpaceGrid:
    """Known-free and known-occupied 0.1 m cells in the base_link plane."""

    free: frozenset
    occupied: frozenset
    resolution: float = CELL_M

    def cell(self, x, y):
        return (int(floor(x / self.resolution)), int(floor(y / self.resolution)))

    def covers(self, x, y, margin):
        """True only when every cell touching the probe square is observed free."""
        if not (isfinite(x) and isfinite(y) and margin >= 0):
            return False
        low_x, low_y = self.cell(x - margin, y - margin)
        high_x, high_y = self.cell(x + margin, y + margin)
        for cell_x in range(low_x, high_x + 1):
            for cell_y in range(low_y, high_y + 1):
                if (cell_x, cell_y) not in self.free:
                    return False
        return True

    def occupied_near(self, x, y, margin):
        low_x, low_y = self.cell(x - margin, y - margin)
        high_x, high_y = self.cell(x + margin, y + margin)
        return any((cell_x, cell_y) in self.occupied
                   for cell_x in range(low_x, high_x + 1)
                   for cell_y in range(low_y, high_y + 1))


def _ray_cells(ax, ay, bx, by, resolution):
    """Cells crossed by the segment, excluding the endpoint cell."""
    distance = hypot(bx - ax, by - ay)
    steps = max(1, int(distance / (resolution * 0.5)))
    cells = []
    last = None
    for index in range(steps):
        ratio = index / steps
        cell = (int(floor((ax + (bx - ax) * ratio) / resolution)),
                int(floor((ay + (by - ay) * ratio) / resolution)))
        if cell != last:
            cells.append(cell)
            last = cell
    return cells


def build_grid(points, origin_xy, resolution=CELL_M, max_points=MAX_RAY_POINTS):
    """Ray-cast bounded depth points into a planar free/occupied grid.

    `points` is an (N, 3) array in base_link. Each ray stops at the first
    occupied cell, so space behind an obstacle is never reported as free.
    """
    array = np.asarray(points, dtype=float)
    if array.size == 0 or array.ndim != 2 or array.shape[1] != 3:
        return FreeSpaceGrid(frozenset(), frozenset(), resolution)
    usable = np.isfinite(array).all(axis=1) & (array[:, 0] > 0)
    usable &= (array[:, 2] >= MIN_HEIGHT_M) & (array[:, 2] <= MAX_HEIGHT_M)
    array = array[usable]
    if len(array) == 0:
        return FreeSpaceGrid(frozenset(), frozenset(), resolution)
    if len(array) > max_points:
        array = array[::max(1, (len(array) + max_points - 1) // max_points)]

    origin = (float(origin_xy[0]), float(origin_xy[1]))
    occupied = {(int(floor(x / resolution)), int(floor(y / resolution)))
                for x, y, _ in array}
    free = set()
    for x, y, _ in array:
        for cell in _ray_cells(origin[0], origin[1], x, y, resolution):
            if cell in occupied:
                break
            free.add(cell)
    free -= occupied
    return FreeSpaceGrid(frozenset(free), frozenset(occupied), resolution)
