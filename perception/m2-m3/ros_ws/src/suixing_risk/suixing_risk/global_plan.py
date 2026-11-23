"""Occupancy-grid A* and map checks for forward local navigation."""

from heapq import heappop, heappush
from math import ceil, floor, hypot, inf, isfinite, sqrt

import numpy as np

from .geometry import candidate_pose
from .navigation import relative_goal


class Grid:
    def __init__(self, width, height, resolution, origin, data, radius, occupied=65):
        import cv2

        if (min(width, height) <= 0 or width * height > 4_000_000
                or not all(isfinite(n) for n in (resolution, origin.x, origin.y, origin.yaw, radius))
                or resolution <= 0 or radius <= 0 or not 1 <= occupied <= 100):
            raise ValueError("invalid map geometry")
        values = np.asarray(data).reshape(height, width)
        free = ((values >= 0) & (values < occupied)).astype(np.uint8)
        # A blocked border models unknown space outside the published map.
        padded = np.pad(free, 1)
        centers = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        # Account for both the occupied square and any position inside the queried cell.
        self.free = centers > radius / resolution + sqrt(2)
        self.origin = origin
        self.resolution = resolution

    def grid_point(self, xy):
        return tuple(value / self.resolution for value in relative_goal(xy, self.origin))

    def cell(self, xy):
        return tuple(floor(value) for value in self.grid_point(xy))

    def center(self, cell):
        return self.origin.apply(*((value + 0.5) * self.resolution for value in cell))

    def open(self, x, y):
        return (0 <= y < self.free.shape[0] and 0 <= x < self.free.shape[1]
                and bool(self.free[y, x]))

    def visible(self, start, end):
        """Visit all cells intersected by a segment, including diagonal corner neighbors."""
        x0, y0 = self.grid_point(start)
        x1, y1 = self.grid_point(end)
        x, y = floor(x0), floor(y0)
        tx, ty = floor(x1), floor(y1)
        dx, dy = x1 - x0, y1 - y0
        sx = 1 if dx > 0 else -1
        sy = 1 if dy > 0 else -1
        delta_x = 1 / abs(dx) if dx else inf
        delta_y = 1 / abs(dy) if dy else inf
        cross_x = abs((x + (sx > 0)) - x0) * delta_x if dx else inf
        cross_y = abs((y + (sy > 0)) - y0) * delta_y if dy else inf
        while self.open(x, y):
            if (x, y) == (tx, ty):
                return True
            next_x = cross_x if x != tx else inf
            next_y = cross_y if y != ty else inf
            if abs(next_x - next_y) <= 1e-9:
                if not self.open(x + sx, y) or not self.open(x, y + sy):
                    return False
                x, y = x + sx, y + sy
                cross_x, cross_y = cross_x + delta_x, cross_y + delta_y
            elif next_x < next_y:
                x, cross_x = x + sx, cross_x + delta_x
            else:
                y, cross_y = y + sy, cross_y + delta_y
        return False

    def arc_clear(self, pose, speed, curvature, seconds):
        count = max(1, ceil(speed * seconds / (self.resolution * 0.5)))
        previous = pose.x, pose.y
        for index in range(1, count + 1):
            point = candidate_pose(speed, curvature, index * seconds / count)
            xy = pose.apply(point.x, point.y)
            if not self.visible(previous, xy):
                return False
            previous = xy
        return True

    def plan(self, start, goal):
        source, target = self.cell(start), self.cell(goal)
        if not self.open(*source) or not self.open(*target):
            return ()
        if self.visible(start, goal):
            return start, goal
        frontier = [(0.0, 0.0, source)]
        costs = {source: 0.0}
        parent = {}
        while frontier:
            _, cost, current = heappop(frontier)
            if cost != costs[current]:
                continue
            if current == target:
                break
            x, y = current
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                neighbor = x + dx, y + dy
                if not self.open(*neighbor) or (dx and dy and not
                        (self.open(x + dx, y) and self.open(x, y + dy))):
                    continue
                new_cost = cost + (sqrt(2) if dx and dy else 1.0)
                if new_cost < costs.get(neighbor, inf):
                    costs[neighbor] = new_cost
                    parent[neighbor] = current
                    estimate = new_cost + hypot(neighbor[0] - target[0], neighbor[1] - target[1])
                    heappush(frontier, (estimate, new_cost, neighbor))
        else:
            return ()

        cells = [target]
        while cells[-1] != source:
            cells.append(parent[cells[-1]])
        points = [start, *(self.center(cell) for cell in reversed(cells)), goal]
        # Simplify only with map-checked lines, keeping the exact goal.
        route = [start]
        anchor = 0
        while anchor < len(points) - 1:
            end = anchor + 1
            while end + 1 < len(points) and self.visible(points[anchor], points[end + 1]):
                end += 1
            route.append(points[end])
            anchor = end
        return tuple(route)


def tracking_target(grid, route, index, pose, lookahead):
    """Advance a monotone segment cursor and look through visible route bends."""
    position = pose.x, pose.y
    while index < len(route) - 1:
        end = route[index]
        start = route[index - 1]
        dx, dy = end[0] - start[0], end[1] - start[1]
        passed = (pose.x - end[0]) * dx + (pose.y - end[1]) * dy >= 0
        if not (passed or hypot(pose.x - end[0], pose.y - end[1]) <= lookahead * 0.75):
            break
        if not grid.visible(position, route[index + 1]):
            break
        index += 1
    if not grid.visible(position, route[index]):
        return index, None
    return index, route[index]
