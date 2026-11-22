"""Verify the extracted M1 bundle on Windows or Linux without ROS."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def rows(name):
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines()]


def expect(condition, case):
    if not condition:
        raise SystemExit(f"FAIL {case}")


def main():
    for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        expect(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name)

    d6_by_stamp = {}
    actual = []
    for scan in rows("sensors/d6-scan.mock.jsonl"):
        stamp = int(scan["stamp_ns"])
        age = (int(scan["received_ros_ns"]) - stamp) // 1_000_000
        actual.append((scan["seq"], scan["quality"], age, scan["payload"]["ranges_m"].count(None)))
        d6_by_stamp[stamp] = scan["quality"]
    expect(actual == [(1, "valid", 20, 0), (2, "unknown", 30, 2), (3, "invalid", 200, 0)],
           "D6 valid, missing ranges, expired")

    stereo_pairs = {}
    for row in rows("sensors/stereo.mock.jsonl"):
        stamp = int(row["stamp_ns"])
        payload = row["payload"]
        pgm = (ROOT / payload["path"]).read_bytes()
        header = f"P5\n{payload['width']} {payload['height']}\n255\n".encode("ascii")
        expect(pgm.startswith(header) and len(pgm) == len(header) + payload["width"] * payload["height"],
               payload["path"])
        stereo_pairs.setdefault(stamp, []).append(row["source"])
    expect(
        set(stereo_pairs) == {stamp for stamp, quality in d6_by_stamp.items() if quality != "invalid"}
        and all(sorted(pair) == ["stereo_left", "stereo_right"] for pair in stereo_pairs.values()),
        "two stereo pairs aligned with D6",
    )

    for name, state, request, feedback, d6 in (
        ("normal", "READY", False, "RELEASED", "ONLINE"),
        ("sensor-offline", "FAULT_SAFE", True, "UNKNOWN", "OFFLINE"),
        ("brake-latched", "BRAKE_LATCHED", True, "APPLIED", "ONLINE"),
    ):
        status = load(f"vehicle-status/{name}.json")
        expect(status["source"] == "mock" and status["system_state"] == state
               and status["brake_requested"] is request and status["brake_feedback"] == feedback
               and status["sensors"]["d6"] == d6 and status["motion_permitted"] is False, name)

    risk_cases = load("risk-summary.mock.json")["cases"]
    observed = []
    for case in risk_cases:
        age = case["receive_monotonic_ms"] - case["generated_monotonic_ms"]
        verdict = "ACCEPT_FRESH" if 0 <= age < case["summary"]["valid_for_ms"] else "REJECT_EXPIRED"
        expect(verdict == case["expected"], case["id"])
        observed.append((age, verdict))
    expect(observed == [(20, "ACCEPT_FRESH"), (100, "REJECT_EXPIRED")], "risk message expiry cases")
    print("PASS SHA-256, 3 D6 rows, 2 stereo pairs, 3 vehicle statuses, 2 risk cases")


if __name__ == "__main__":
    main()
