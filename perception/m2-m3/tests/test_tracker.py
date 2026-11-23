"""IoU tracker behaviour."""

import unittest

from suixing_risk.tracker import IouTracker, iou


class IouTest(unittest.TestCase):
    def test_identical_boxes(self):
        self.assertEqual(iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)

    def test_disjoint_boxes(self):
        self.assertEqual(iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)

    def test_partial_overlap(self):
        self.assertAlmostEqual(iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3)


class TrackerTest(unittest.TestCase):
    def test_id_is_stable_across_frames(self):
        tracker = IouTracker()
        first = tracker.update([(0, 0, 10, 10)])
        second = tracker.update([(1, 1, 11, 11)])
        self.assertEqual(first, second)

    def test_far_box_gets_new_id(self):
        tracker = IouTracker()
        first = tracker.update([(0, 0, 10, 10)])
        second = tracker.update([(50, 50, 60, 60)])
        self.assertNotEqual(first, second)

    def test_coasting_then_expiry(self):
        tracker = IouTracker(max_age=2)
        track_id = tracker.update([(0, 0, 10, 10)])[0]
        tracker.update([])
        tracker.update([])
        self.assertIn(track_id, tracker.tracks)
        tracker.update([])
        self.assertNotIn(track_id, tracker.tracks)

    def test_two_boxes_keep_separate_ids(self):
        tracker = IouTracker()
        left, right = tracker.update([(0, 0, 10, 10), (100, 0, 110, 10)])
        again = tracker.update([(1, 0, 11, 10), (101, 0, 111, 10)])
        self.assertEqual([left, right], again)

    def test_invalid_settings(self):
        with self.assertRaises(ValueError):
            IouTracker(iou_threshold=1.5)
        with self.assertRaises(ValueError):
            IouTracker(max_age=0)


if __name__ == "__main__":
    unittest.main()
