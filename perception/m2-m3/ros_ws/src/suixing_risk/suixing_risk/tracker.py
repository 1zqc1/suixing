"""Deterministic IoU tracker so every detection carries a stable track id."""

from dataclasses import dataclass


def iou(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    width = min(ax2, bx2) - max(ax1, bx1)
    height = min(ay2, by2) - max(ay1, by1)
    if width <= 0 or height <= 0:
        return 0.0
    intersection = width * height
    union = ((ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection)
    return intersection / union if union > 0 else 0.0


@dataclass
class _Track:
    box: tuple
    age: int = 0


class IouTracker:
    """Greedy one-to-one matching with a short coast window."""

    def __init__(self, iou_threshold=0.3, max_age=5):
        if not 0.0 <= iou_threshold <= 1.0 or not 1 <= max_age <= 100:
            raise ValueError("iou_threshold must be in [0, 1] and max_age in [1, 100]")
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.tracks = {}
        self.next_id = 1

    def update(self, boxes):
        """Match boxes to tracks and return track ids in the input order."""
        candidates = sorted(
            ((iou(box, track.box), index, track_id)
             for index, box in enumerate(boxes)
             for track_id, track in self.tracks.items()),
            key=lambda item: (-item[0], item[1], item[2]),
        )
        assigned, used = {}, set()
        for score, index, track_id in candidates:
            if score < self.iou_threshold or index in assigned or track_id in used:
                continue
            assigned[index] = track_id
            used.add(track_id)

        ids = []
        seen = set(used)
        for index, box in enumerate(boxes):
            track_id = assigned.get(index)
            if track_id is None:
                track_id = self.next_id
                self.next_id += 1
                self.tracks[track_id] = _Track(tuple(box))
                seen.add(track_id)
            else:
                self.tracks[track_id] = _Track(tuple(box), self.tracks[track_id].age + 1)
            ids.append(track_id)

        for track_id in list(self.tracks):
            if track_id in seen:
                continue
            self.tracks[track_id].age += 1
            if self.tracks[track_id].age > self.max_age:
                del self.tracks[track_id]
        return ids
