import unittest
from math import atan

from suixing_risk.drive import (DifferentialDriveGate, DifferentialWheelOdometry, DriveGate,
                               Feedback, WheelOdometry, parse_feedback)


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.gate = DriveGate(0.5, 0.25, 0.5, 100_000_000)
        self.now = 1_000_000_000
        self.steady = 2_000_000_000
        self.normal = Feedback(self.now, 0.0, 0.0, True, False, False, True)
        self.gate.update_feedback(self.normal, self.now, self.steady)
        self.candidate = (self.now, 0.2, 0.2)
        self.status = (self.now, self.now + 30_000_000)

    def emit(self, offset=0):
        return self.gate.output(self.now + offset, self.steady + offset,
                                self.candidate, self.status)

    def test_disarmed_start_and_vehicle_units(self):
        self.assertEqual(self.emit(), (0, 0, True))
        self.assertTrue(self.gate.arm(True, self.now, self.steady))
        speed, angle, brake = self.emit()
        self.assertAlmostEqual(speed, 0.2)
        self.assertAlmostEqual(angle, atan(0.5))
        self.assertFalse(brake)

    def test_expiry_and_mismatched_stamp(self):
        self.gate.arm(True, self.now, self.steady)
        self.assertTrue(self.emit(30_000_000)[2])
        self.status = self.now - 1, self.now + 30_000_000
        self.assertTrue(self.emit()[2])

    def test_estop_requires_explicit_rearm(self):
        self.gate.arm(True, self.now, self.steady)
        self.gate.update_feedback(Feedback(self.now + 1, 0, 0, True, True, False, True),
                                  self.now + 1, self.steady + 1)
        self.assertTrue(self.emit(1)[2])
        self.assertFalse(self.gate.arm(True, self.now + 1, self.steady + 1))
        self.gate.update_feedback(Feedback(self.now + 2, 0, 0, True, False, False, True),
                                  self.now + 2, self.steady + 2)
        self.assertTrue(self.emit(2)[2])
        self.assertTrue(self.gate.arm(True, self.now + 2, self.steady + 2))
        self.assertTrue(self.emit(2)[2])  # pre-arm command cannot resume

    def test_frozen_ros_time_and_feedback_dropout(self):
        self.gate.arm(True, self.now, self.steady)
        self.assertTrue(self.gate.output(self.now, self.steady + 100_000_000,
                                         self.candidate, self.status)[2])
        self.assertFalse(self.gate.armed)

    def test_unsupported_speed_and_curvature_brake(self):
        self.gate.arm(True, self.now, self.steady)
        self.candidate = self.now, 0.4, 0.0
        self.assertTrue(self.emit()[2])
        self.candidate = self.now, 0.2, 1.0
        self.assertTrue(self.emit()[2])

    def test_feedback_odometry_uses_measurement(self):
        odom = WheelOdometry(0.5, 100_000_000)
        start = Feedback(self.now, 0.2, 0, True, False, False, False)
        self.assertEqual(odom.update(start).x, 0)
        frame = Feedback(self.now + 50_000_000, 0.2, 0, True, False, False, False)
        self.assertAlmostEqual(odom.update(frame).x, 0.01)
        self.assertIsNone(odom.update(Feedback(self.now + 200_000_000, 0.2, 0,
                                               True, False, False, False)))

    def test_feedback_requires_real_boolean_flags(self):
        with self.assertRaises(ValueError):
            parse_feedback(dict(stamp_ns=1, speed_mps=0, steering_rad=0,
                                motion_permitted=1, estop_active=False, fault=False,
                                brake_applied=True))


class DifferentialDriveTests(unittest.TestCase):
    def setUp(self):
        self.gate = DifferentialDriveGate(0.5, 0.25, 0.40, 100_000_000)
        self.now = 1_000_000_000
        self.steady = 2_000_000_000
        self.status = self.now, self.now + 30_000_000

    def feedback(self, left=0.0, right=0.0, **overrides):
        fields = dict(stamp_ns=self.now, left_wheel_mps=left, right_wheel_mps=right,
                      motion_permitted=True, estop_active=False, fault=False, brake_applied=True)
        fields.update(overrides)
        return parse_feedback(fields, differential=True)

    def test_wheel_targets_and_limits(self):
        self.assertTrue(self.gate.update_feedback(self.feedback(), self.now, self.steady))
        self.assertTrue(self.gate.arm(True, self.now, self.steady))
        candidate = self.now, 0.2, 0.2
        left, right, brake = self.gate.output(self.now, self.steady, candidate, self.status)
        self.assertAlmostEqual(left, 0.15)
        self.assertAlmostEqual(right, 0.25)
        self.assertFalse(brake)
        for yaw in (1.0, -1.0, float("inf")):
            self.assertEqual(self.gate.output(self.now, self.steady, (self.now, 0.2, yaw),
                                              self.status), (0.0, 0.0, True))
        self.assertTrue(self.gate.output(self.status[1], self.steady, candidate, self.status)[2])
        self.gate.update_feedback(self.feedback(motion_permitted=False), self.now, self.steady)
        self.assertFalse(self.gate.armed)

    def test_stationary_check_uses_both_wheels(self):
        self.gate.update_feedback(self.feedback(-0.1, 0.1), self.now, self.steady)
        self.assertFalse(self.gate.arm(True, self.now, self.steady))
        with self.assertRaises(ValueError):
            self.feedback(left=float("nan"))

    def test_odometry_integrates_measured_wheel_speeds_including_rotation(self):
        odom = DifferentialWheelOdometry(0.5, 100_000_000)
        f = self.feedback(-0.2, 0.2)
        odom.update(f)
        pose = odom.update(self.feedback(-0.2, 0.2, stamp_ns=self.now + 50_000_000))
        self.assertAlmostEqual(pose.yaw, 0.04)
        self.assertEqual((pose.x, pose.y), (0, 0))
        self.assertAlmostEqual(odom.yaw_rate(f), 0.8)
        self.assertIsNone(odom.update(self.feedback(stamp_ns=self.now + 200_000_000)))
