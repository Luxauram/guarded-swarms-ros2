#!/usr/bin/env python3
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""
analyze_clock.py - the tables of a clock-denial bench.

Read-only: it reads the bags recorded by
scripts/experiments/run_clock_bench.sh and writes tables and CSV. The sensors
are healthy in every run; the arms differ only in the clock. For each run, over
a steady window (after start-up), it measures how much of the time the board
denies the command - clamps actuator_cmd_safe to zero - and how much of the
time it reports unsafe, and whether its simulated clock advanced at all.

Outcome per arm, with its 95% Wilson interval:
  clock-ok    the board clears the command: the vehicle operates (no denial)
  clock-dos   the board's clock is denied, so it fails safe and vetoes every
              command although the sensors are healthy: the vehicle is blocked.
              This is the denial-of-service effect the measurement reports.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/analyze_clock.py bags/clock-bench/<campaign> \\
        [--out results/clock-bench/<campaign>] [--settle 10]
"""

import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

SAFE_THRESHOLD = 0.5       # safety_status >= this is "safe"
DENIED_EPS = 1e-6          # actuator_cmd_safe at/below this is a denied command
BLOCKED_FRAC = 0.5         # denied for at least this fraction of the window
Z95 = 1.959963984540054

STATUS_TOPIC = "/safety_status"
SAFE_TOPIC = "/actuator_cmd_safe"
RAW_TOPIC = "/actuator_cmd_raw"
CLOCK_TOPIC = "/clock"


@dataclass
class RunResult:
    arm: str = ""
    run: int = 0
    denied_frac: float = 0.0       # share of the window with the command at 0
    unsafe_frac: float = 0.0       # share of the window reporting unsafe
    clock_advanced: bool = False   # the simulated clock moved past zero
    samples: int = 0               # command samples in the window
    blocked: bool = False          # denied for most of the window (DoS)
    as_expected: bool = False


def analyze_run(arm: str, run: int, status: List[Tuple[float, float]],
                safe: List[Tuple[float, float]],
                clock: List[Tuple[float, float]], settle: float) -> RunResult:
    """Core logic, on receive-time lists [(rx_s, value), ...].

    status/safe are the float payloads; clock values are simulated seconds.
    """
    r = RunResult(arm=arm, run=run)

    sw = [v for rx, v in safe if rx >= settle]
    uw = [v for rx, v in status if rx >= settle]
    r.samples = len(sw)
    if sw:
        r.denied_frac = sum(1 for v in sw if abs(v) <= DENIED_EPS) / len(sw)
    if uw:
        r.unsafe_frac = sum(1 for v in uw if v < SAFE_THRESHOLD) / len(uw)
    r.clock_advanced = bool(clock) and max(v for _, v in clock) >= 1.0

    r.blocked = r.denied_frac >= BLOCKED_FRAC
    if arm == "clock-dos":
        r.as_expected = r.blocked            # must be blocked (DoS)
    else:
        r.as_expected = not r.blocked        # must operate
    return r


def wilson(k: int, n: int) -> Tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + Z95 * Z95 / n
    c = (p + Z95 * Z95 / (2 * n)) / d
    h = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / d
    return (p * 100, max(0.0, c - h) * 100, min(1.0, c + h) * 100)


def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# =============================================================================
# Bag reading
# =============================================================================
def storage_id(bag_dir: str) -> str:
    for f in os.listdir(bag_dir):
        if f.endswith(".mcap"):
            return "mcap"
    return "sqlite3"


def read_bag(bag_dir: str):
    """Return the receive-time series the analysis needs."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=storage_id(bag_dir)),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                    output_serialization_format="cdr"))
    typ = {t.name: t.type for t in reader.get_all_topics_and_types()}
    msg_cls, t0 = {}, None
    status, safe, clock = [], [], []
    while reader.has_next():
        name, data, stamp = reader.read_next()
        if name not in (STATUS_TOPIC, SAFE_TOPIC, CLOCK_TOPIC):
            continue
        if name not in msg_cls:
            msg_cls[name] = get_message(typ[name])
        m = deserialize_message(data, msg_cls[name])
        t0 = stamp if t0 is None else min(t0, stamp)
        rx = stamp / 1e9
        if name == STATUS_TOPIC:
            status.append((rx, float(m.data)))
        elif name == SAFE_TOPIC:
            safe.append((rx, float(m.data)))
        elif name == CLOCK_TOPIC:
            clock.append((rx, m.clock.sec + m.clock.nanosec / 1e9))
    base = (t0 or 0) / 1e9
    norm = lambda s: sorted(((rx - base, v) for rx, v in s), key=lambda p: p[0])
    return norm(status), norm(safe), norm(clock)


# =============================================================================
# Campaign
# =============================================================================
def read_manifest(path: str) -> List[Tuple[str, int, str]]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append((row["arm"], int(row["run"]), row["folder"]))
    return out


EXPECT = {
    "clock-ok": "the vehicle operates (command cleared)",
    "clock-dos": "the vehicle is blocked (command denied): DoS",
}


def main():
    p = argparse.ArgumentParser(description="Tables of a clock-denial bench.")
    p.add_argument("campaign_dir")
    p.add_argument("--out", default=None)
    p.add_argument("--settle", type=float, default=10.0,
                   help="ignore the first this-many seconds (start-up)")
    args = p.parse_args()

    manifest = os.path.join(args.campaign_dir, "manifest.csv")
    if not os.path.isfile(manifest):
        sys.exit("no manifest.csv in {}".format(args.campaign_dir))
    out_dir = args.out or os.path.join(
        "results", "clock-bench", os.path.basename(args.campaign_dir.rstrip("/")))
    os.makedirs(out_dir, exist_ok=True)

    results: List[RunResult] = []
    for arm, run, folder in read_manifest(manifest):
        bag = os.path.join(folder, "bag")
        if not os.path.isdir(bag):
            print("[analyze_clock] missing bag: {}".format(bag))
            continue
        status, safe, clock = read_bag(bag)
        results.append(analyze_run(arm, run, status, safe, clock, args.settle))

    lines = ["# Clock-denial bench `{}`".format(
        os.path.basename(args.campaign_dir.rstrip("/"))), ""]
    lines.append("| Arm | Runs | Expected | As expected | "
                 "Command denied | Time unsafe | Clock advanced |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    by_arm: Dict[str, List[RunResult]] = {}
    for r in results:
        by_arm.setdefault(r.arm, []).append(r)
    for arm in ("clock-ok", "clock-dos"):
        rs = by_arm.get(arm, [])
        if not rs:
            continue
        n = len(rs)
        k = sum(1 for r in rs if r.as_expected)
        pct, lo, hi = wilson(k, n)
        denied = mean([r.denied_frac for r in rs]) * 100
        unsafe = mean([r.unsafe_frac for r in rs]) * 100
        adv = sum(1 for r in rs if r.clock_advanced)
        lines.append("| `{}` | {} | {} | {}/{} [{:.1f}–{:.1f}] | {:.0f}% | "
                     "{:.0f}% | {}/{} |".format(arm, n, EXPECT[arm], k, n, lo,
                                                hi, denied, unsafe, adv, n))
    report = "\n".join(lines) + "\n"
    print(report)
    with open(os.path.join(out_dir, "clock.md"), "w") as f:
        f.write(report)
    with open(os.path.join(out_dir, "clock.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "run", "denied_frac", "unsafe_frac",
                    "clock_advanced", "samples", "blocked", "as_expected"])
        for r in results:
            w.writerow([r.arm, r.run, round(r.denied_frac, 4),
                        round(r.unsafe_frac, 4), r.clock_advanced, r.samples,
                        r.blocked, r.as_expected])
    print("[analyze_clock] wrote clock.md and clock.csv to {}".format(out_dir))


if __name__ == "__main__":
    main()