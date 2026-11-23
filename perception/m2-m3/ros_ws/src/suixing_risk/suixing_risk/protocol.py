"""Fixed-length RiskSummary frame for the Linux -> CPU3 RPMsg channel.

The ROS topic carries this exact byte string; nothing else may cross the core
boundary. Layout is 64 bytes, little-endian, CRC-16/CCITT-FALSE over bytes 0..47.
"""

from math import isfinite
import struct
import zlib

MAGIC = b"SXR1"
VERSION = 1
MSG_TYPE_RISK = 1
FRAME_SIZE = 64
NULL_U16 = 0xFFFF

RISK_CODES = {"UNKNOWN": 0, "CLEAR": 1, "CAUTION": 2, "DANGER": 3}
RISK_NAMES = {code: name for name, code in RISK_CODES.items()}

# quality bits (byte 6)
Q_SCAN = 0x01
Q_STEREO = 0x02
Q_ALIGNED = 0x04
Q_SEMANTIC = 0x08
Q_RECEIVED_TIME = 0x10

# flags (byte 43)
F_UNKNOWN_REGION = 0x01
F_TTC_VALID = 0x02
F_SPEED_LIMIT_VALID = 0x04

REASON_NONE = 0
REASON_NO_OBSERVATION = 1
REASON_STALE = 2
REASON_UNALIGNED = 3
REASON_NO_COVERAGE = 4
REASON_DANGER = 5
REASON_SEMANTIC = 6

_FRAME = struct.Struct("<4sBBBBIIQQHHHHBBBBHHH14s")
assert _FRAME.size == FRAME_SIZE


def crc16_ccitt(data):
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def _unsigned(value, bits, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not 0 <= value < (1 << bits):
        raise ValueError(f"{name} does not fit in {bits} bits")
    return value


def _millis(value, name):
    if value is None:
        return NULL_U16
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or None")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return min(NULL_U16 - 1, int(round(value)))


def _centi(value, name):
    if value is None:
        return NULL_U16
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or None")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return min(NULL_U16 - 1, int(round(value * 100)))


def _risk_code(summary, direction):
    risk = summary.get("risk")
    if not isinstance(risk, dict) or risk.get(direction) not in RISK_CODES:
        raise ValueError(f"missing or invalid risk for {direction}")
    return RISK_CODES[risk[direction]]


def _session_id(value):
    """Wire sessions are 32-bit. Accept an int, or the first 8 hex chars of an id."""
    if isinstance(value, bool):
        raise ValueError("session_id must be an integer or hex string")
    if isinstance(value, int):
        return _unsigned(value, 32, "session_id")
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 8:
            try:
                return int(text[:8], 16)
            except ValueError:
                pass
        # Human-readable session labels still get a stable 32-bit wire id.
        return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF
    raise ValueError("session_id must be an integer or string")


def _quality(summary):
    bits = 0
    if summary.get("scan_valid"):
        bits |= Q_SCAN
    if summary.get("stereo_valid"):
        bits |= Q_STEREO
    if summary.get("aligned"):
        bits |= Q_ALIGNED
    if summary.get("semantic_used"):
        bits |= Q_SEMANTIC
    if summary.get("received_age_ms") is not None:
        bits |= Q_RECEIVED_TIME
    return bits


def _reason(summary):
    if not summary.get("scan_valid") and not summary.get("stereo_valid"):
        return REASON_NO_OBSERVATION
    if summary.get("valid_for_ms") is None:
        return REASON_STALE
    if not summary.get("aligned"):
        return REASON_UNALIGNED
    if "DANGER" in summary.get("risk", {}).values():
        return REASON_DANGER
    if summary.get("unknown_region"):
        return REASON_NO_COVERAGE
    if summary.get("semantic_used"):
        return REASON_SEMANTIC
    return REASON_NONE


def encode(summary, generated_ns):
    """Pack a RiskSummary dictionary into the 64-byte wire frame."""
    ttc = summary.get("ttc_s")
    if ttc is not None:
        if (not isinstance(ttc, (list, tuple)) or len(ttc) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in ttc)):
            raise ValueError("ttc_s must be [earliest, latest] seconds or None")
        ttc_min = _millis(ttc[0] * 1000.0, "ttc earliest")
        ttc_max = _millis(ttc[1] * 1000.0, "ttc latest")
    else:
        ttc_min = ttc_max = NULL_U16
    speed = summary.get("suggested_speed_limit_mps")
    flags = 0
    if summary.get("unknown_region"):
        flags |= F_UNKNOWN_REGION
    if ttc is not None:
        flags |= F_TTC_VALID
    if speed is not None:
        flags |= F_SPEED_LIMIT_VALID

    sample_ns = summary.get("sample_ns")
    if sample_ns is None:
        if (any(summary.get(key) for key in ("scan_valid", "stereo_valid", "aligned", "semantic_used"))
                or summary.get("valid_for_ms") is not None
                or any(_risk_code(summary, name) != RISK_CODES["UNKNOWN"]
                       for name in ("left", "straight", "right"))):
            raise ValueError("missing sample timestamp for an observed risk frame")
        sample_ns = 0

    body = _FRAME.pack(
        MAGIC,
        VERSION,
        MSG_TYPE_RISK,
        _quality(summary),
        _reason(summary),
        _unsigned(summary["session_id"], 32, "session_id")
        if isinstance(summary.get("session_id"), int) else _session_id(summary.get("session_id")),
        _unsigned(summary.get("seq", 0), 32, "seq"),
        _unsigned(sample_ns, 64, "sample_ns"),
        _unsigned(generated_ns, 64, "generated_ns"),
        _millis(summary.get("valid_for_ms"), "valid_for_ms"),
        _millis(summary.get("source_age_ms"), "source_age_ms"),
        ttc_min,
        ttc_max,
        _risk_code(summary, "left"),
        _risk_code(summary, "straight"),
        _risk_code(summary, "right"),
        flags,
        _centi(speed, "suggested_speed_limit_mps"),
        0,
        0,
        b"\x00" * 14,
    )
    crc = crc16_ccitt(body[:48])
    return body[:48] + struct.pack("<H", crc) + body[50:]


def decode(frame):
    """Validate and unpack a wire frame. Raises ValueError on any fault."""
    if not isinstance(frame, (bytes, bytearray, memoryview)):
        raise ValueError("frame must be bytes-like")
    data = bytes(frame)
    if len(data) != FRAME_SIZE:
        raise ValueError(f"frame must be {FRAME_SIZE} bytes, got {len(data)}")
    (magic, version, msg_type, quality, reason, session_id, seq, sample_ns,
     generated_ns, valid_ms, source_age_ms, ttc_min, ttc_max, left, straight,
     right, flags, speed_centi, _reserved, crc, _tail) = _FRAME.unpack(data)
    if magic != MAGIC:
        raise ValueError("bad magic")
    if version != VERSION:
        raise ValueError(f"unsupported version {version}")
    if msg_type != MSG_TYPE_RISK:
        raise ValueError(f"unsupported message type {msg_type}")
    if crc != crc16_ccitt(data[:48]):
        raise ValueError("CRC mismatch")
    for code in (left, straight, right):
        if code not in RISK_NAMES:
            raise ValueError(f"invalid risk code {code}")
    ttc = None
    if flags & F_TTC_VALID:
        ttc = [None if ttc_min == NULL_U16 else ttc_min / 1000.0,
               None if ttc_max == NULL_U16 else ttc_max / 1000.0]
    return {
        "session_id": session_id,
        "seq": seq,
        "sample_ns": sample_ns or None,
        "generated_ns": generated_ns,
        "risk": {"left": RISK_NAMES[left], "straight": RISK_NAMES[straight],
                 "right": RISK_NAMES[right]},
        "ttc_s": ttc,
        "unknown_region": bool(flags & F_UNKNOWN_REGION),
        "valid_for_ms": None if valid_ms == NULL_U16 else valid_ms,
        "source_age_ms": None if source_age_ms == NULL_U16 else source_age_ms,
        "suggested_speed_limit_mps": (None if speed_centi == NULL_U16
                                      else speed_centi / 100.0),
        "semantic_used": bool(quality & Q_SEMANTIC),
        "scan_valid": bool(quality & Q_SCAN),
        "stereo_valid": bool(quality & Q_STEREO),
        "aligned": bool(quality & Q_ALIGNED),
        "received_age_known": bool(quality & Q_RECEIVED_TIME),
        "reason": reason,
    }


C_STRUCT = """\
struct sx_risk_frame {          /* 64 bytes, little-endian, packed */
  char     magic[4];            /* "SXR1" */
  uint8_t  version;             /* 1 */
  uint8_t  msg_type;            /* 1 = risk */
  uint8_t  quality;             /* bit flags */
  uint8_t  reason;
  uint32_t session_id;
  uint32_t seq;
  uint64_t sample_ns;
  uint64_t generated_ns;
  uint16_t valid_ms;            /* remaining lifetime, 0xFFFF unknown */
  uint16_t source_age_ms;       /* sampling age, 0xFFFF unknown */
  uint16_t ttc_min_ms;
  uint16_t ttc_max_ms;
  uint8_t  risk_left;           /* 0 unknown 1 clear 2 caution 3 danger */
  uint8_t  risk_straight;
  uint8_t  risk_right;
  uint8_t  flags;
  uint16_t speed_limit_centi;   /* m/s * 100, 0xFFFF unknown */
  uint16_t reserved0;
  uint16_t crc16;               /* CCITT-FALSE over bytes 0..47 */
  uint8_t  reserved1[14];
};
"""
