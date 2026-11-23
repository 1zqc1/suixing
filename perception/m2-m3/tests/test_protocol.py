"""RiskSummary wire frame: layout, validation and round trip."""

import struct
import unittest

from suixing_risk.protocol import (FRAME_SIZE, Q_ALIGNED, Q_SCAN, Q_SEMANTIC,
                                   Q_STEREO, REASON_DANGER, decode, encode)

SUMMARY = {
    "session_id": "0123456789abcdef",
    "seq": 7,
    "sample_ns": 1_000_000_000,
    "risk": {"left": "CLEAR", "straight": "CAUTION", "right": "DANGER"},
    "ttc_s": [1.25, 1.75],
    "unknown_region": False,
    "valid_for_ms": 80,
    "source_age_ms": 12.5,
    "suggested_speed_limit_mps": 0.3,
    "semantic_used": True,
    "scan_valid": True,
    "stereo_valid": True,
    "aligned": True,
    "received_age_ms": 5.0,
}


class FrameLayoutTest(unittest.TestCase):
    def test_size_is_fixed(self):
        self.assertEqual(len(encode(SUMMARY, 1_000_010_000)), FRAME_SIZE)

    def test_round_trip(self):
        decoded = decode(encode(SUMMARY, 1_000_010_000))
        self.assertEqual(decoded["session_id"], 0x01234567)
        self.assertEqual(decoded["seq"], 7)
        self.assertEqual(decoded["sample_ns"], 1_000_000_000)
        self.assertEqual(decoded["generated_ns"], 1_000_010_000)
        self.assertEqual(decoded["risk"], SUMMARY["risk"])
        self.assertEqual(decoded["valid_for_ms"], 80)
        self.assertEqual(decoded["source_age_ms"], 12)
        self.assertEqual(decoded["ttc_s"], [1.25, 1.75])
        self.assertEqual(decoded["suggested_speed_limit_mps"], 0.3)
        self.assertTrue(decoded["semantic_used"])
        self.assertEqual(decoded["reason"], REASON_DANGER)

    def test_json_session_projects_to_first_eight_hex_characters(self):
        first = encode(dict(SUMMARY, session_id="01234567aaaaaaaa"), 1)
        second = encode(dict(SUMMARY, session_id="01234567bbbbbbbb"), 1)
        self.assertEqual(first[8:12], bytes.fromhex("67452301"))
        self.assertEqual(first, second)

    def test_reserved_tail_is_zero_on_send_and_ignored_on_receive(self):
        original = encode(SUMMARY, 1_000_010_000)
        self.assertEqual(original[50:], bytes(14))
        changed = original[:50] + bytes(range(1, 15))
        self.assertEqual(decode(changed), decode(original))

    def test_quality_bits_survive(self):
        frame = encode(SUMMARY, 1)
        quality = frame[6]
        self.assertEqual(quality & (Q_SCAN | Q_STEREO | Q_ALIGNED | Q_SEMANTIC),
                         Q_SCAN | Q_STEREO | Q_ALIGNED | Q_SEMANTIC)

    def test_nulls_use_sentinel(self):
        summary = dict(SUMMARY, ttc_s=None, valid_for_ms=None, source_age_ms=None,
                       suggested_speed_limit_mps=None, semantic_used=False)
        decoded = decode(encode(summary, 1))
        self.assertIsNone(decoded["ttc_s"])
        self.assertIsNone(decoded["valid_for_ms"])
        self.assertIsNone(decoded["source_age_ms"])
        self.assertIsNone(decoded["suggested_speed_limit_mps"])
        self.assertFalse(decoded["semantic_used"])

    def test_encode_is_deterministic(self):
        self.assertEqual(encode(SUMMARY, 42), encode(SUMMARY, 42))

    def test_known_bytes(self):
        frame = encode(SUMMARY, 1_000_010_000)
        magic, version, msg_type = struct.unpack_from("<4sBB", frame)
        self.assertEqual(magic, b"SXR1")
        self.assertEqual((version, msg_type), (1, 1))
        self.assertEqual(frame[40], 1)  # left CLEAR
        self.assertEqual(frame[41], 2)  # straight CAUTION
        self.assertEqual(frame[42], 3)  # right DANGER
        self.assertEqual(struct.unpack_from("<H", frame, 44)[0], 30)


class FrameValidationTest(unittest.TestCase):
    def test_length_is_enforced(self):
        with self.assertRaises(ValueError):
            decode(b"\x00" * (FRAME_SIZE - 1))
        with self.assertRaises(ValueError):
            decode(b"\x00" * (FRAME_SIZE + 1))

    def test_bad_magic(self):
        frame = bytearray(encode(SUMMARY, 1))
        frame[0:4] = b"XXXX"
        with self.assertRaisesRegex(ValueError, "magic"):
            decode(bytes(frame))

    def test_bad_version(self):
        frame = bytearray(encode(SUMMARY, 1))
        frame[4] = 9
        with self.assertRaisesRegex(ValueError, "version"):
            decode(bytes(frame))

    def test_crc_corruption(self):
        frame = bytearray(encode(SUMMARY, 1))
        frame[20] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "CRC"):
            decode(bytes(frame))

    def test_non_bytes_input(self):
        with self.assertRaises(ValueError):
            decode("not bytes")

    def test_seq_must_fit(self):
        with self.assertRaises(ValueError):
            encode(dict(SUMMARY, seq=2 ** 32), 1)

    def test_risk_must_be_known(self):
        with self.assertRaises(ValueError):
            encode(dict(SUMMARY, risk={"left": "MAYBE", "straight": "CLEAR",
                                       "right": "CLEAR"}), 1)


if __name__ == "__main__":
    unittest.main()
