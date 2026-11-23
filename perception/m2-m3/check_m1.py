"""M1 handoff acceptance. Run with the project package on PYTHONPATH."""

import argparse
import json
from math import isclose
from pathlib import Path
import subprocess
import sys

from suixing_risk.geometry import Config, fresh, summarize
from suixing_risk.protocol import FRAME_SIZE, decode, encode
from suixing_risk.replay import replay
from suixing_risk.simulate import scenarios


def verify(bundle):
    subprocess.run([sys.executable, str(bundle / "verify.py")], check=True)
    sample_rows = list(replay(bundle))
    assert [(r["sample_seq"], r["scan_age_ms"], r["scan_accepted"]) for r in sample_rows] == [
        (1, 20, True), (2, 30, True), (3, 200, False)
    ]
    assert sample_rows[1]["missing_beam_indices"] == [1, 3]
    assert all(isclose(got, expected) for got, expected in
               zip(sample_rows[1]["missing_beam_angles_rad"], (-0.3, 0.3)))
    for row in sample_rows[:2]:
        assert row["stereo"]["median_disparity_px"] == 4.0
        assert isclose(row["stereo"]["median_depth_m"], 1.2)
        assert row["summary"]["ttc_s"] is None
    assert sample_rows[2]["stereo"] is None
    assert set(sample_rows[2]["summary"]["risk"].values()) == {"UNKNOWN"}
    assert sample_rows[2]["summary"]["valid_for_ms"] is None
    assert [row["summary"]["valid_for_ms"] for row in sample_rows[:2]] == [80, 70]

    simulation = list(scenarios())
    results = {row["scenario"]: row["summary"] for row in simulation}
    assert set(results["clear"]["risk"].values()) == {"CLEAR"}
    assert results["crossing"]["risk"]["straight"] == "DANGER"
    ttc = results["crossing"]["ttc_s"]
    assert 0 < ttc[0] < ttc[1] <= Config().danger_s
    assert results["dropout"]["ttc_s"] is None
    assert set(results["dropout"]["risk"].values()) == {"UNKNOWN"}
    assert results["low-obstacle"]["risk"]["straight"] == "DANGER"
    # Semantics may only add risk, never clear a direction.
    assert results["clear"]["semantic_used"] is False
    assert results["clear"]["suggested_speed_limit_mps"] is None
    assert results["semantic-boost"]["semantic_used"] is True
    assert results["semantic-boost"]["risk"]["straight"] == "DANGER"
    assert results["semantic-boost"]["suggested_speed_limit_mps"] == 0.0

    # The wire frame must survive pack/unpack without losing a decision field.
    frame = encode(results["crossing"], 1_000_050_000)
    assert len(frame) == FRAME_SIZE
    decoded = decode(frame)
    assert decoded["risk"] == results["crossing"]["risk"]
    assert decoded["valid_for_ms"] == results["crossing"]["valid_for_ms"]
    assert decoded["suggested_speed_limit_mps"] == results["crossing"]["suggested_speed_limit_mps"]
    assert not fresh(100, 100, 99)
    assert fresh(100, 100, 100_000_099)
    assert not fresh(100, 100, 100_000_100)
    assert summarize("empty", 1, 5, speed=float("nan"))["risk"]["straight"] == "UNKNOWN"
    summary = results["crossing"]
    deadline = summary["valid_for_ms"]
    summary_cases = [
        {"id": label, "generated_monotonic_ms": 1000, "receive_monotonic_ms": 1000 + age,
         "summary": dict(summary, seq=seq), "expected": verdict}
        for seq, (label, age, verdict) in enumerate(
            (("fresh", 20, "ACCEPT_FRESH"), ("expired-at-boundary", deadline, "REJECT_EXPIRED")),
            start=1)
    ]
    return {"bundle_rows": sample_rows, "simulations": simulation, "risk_summary_cases": summary_cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.bundle)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("PASS original handoff, all bag topics, 3 sensor cases, 2 disparities, "
          "5 geometry simulations, 64-byte risk frame")


if __name__ == "__main__":
    main()
