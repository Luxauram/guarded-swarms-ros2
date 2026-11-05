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
thesis_receive_axis.py - reproduce Tables 6.1 and 6.2 of the thesis.

Diagnostic, not a metric. It recomputes the chain latencies as differences
between the instants at which the recorder RECEIVED the first message of each
kind (the bag receive time, i.e. the recorder's wall clock), over the same
runs and with the same statistics as the thesis tables (mean, median, sample
standard deviation). If the output matches the thesis, the published figures
were computed on the receive axis rather than in simulated time. The figures
to use from now on are the simulated-time ones from audit_timing.py.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/thesis_receive_axis.py bags/coastal-*

@author Luca D'Aurizio
"""

import argparse
import os
import sys
from typing import Dict, Optional

from audit_timing import AUTHORISE, describe, pick_target, read_bag

# (label as in the thesis results file, from-instant, to-instant)
ROWS = [
    ("end-to-end", "obs", "mission"),
    ("Obs->Cand", "obs", "cand"),
    ("Cand->Conf", "cand", "ct"),
    ("Conf->Miss", "ct", "mission"),
    ("Miss->Task", "mission", "task"),
    ("[sys] Obs->Conf", "obs", "ct"),
    ("[auth] Conf->auth", "ct", "auth"),
    ("[sys] auth->Task", "auth", "task"),
]


def first_rx(msgs: list, pred=lambda m: True) -> Optional[float]:
    """Receive time of the first matching message."""
    times = [rv for rv, m in msgs if pred(m)]
    return min(times) if times else None


def instants(data: Dict[str, list]) -> Dict[str, Optional[float]]:
    """First reception of each message kind for the run's target."""
    target = pick_target(data["obs"])
    if target is None:
        return {}

    def tgt(m) -> bool:
        return m.target_id == target

    return {
        "obs": first_rx(data["obs"], tgt),
        "cand": first_rx(data["interp"], lambda m: tgt(m)
                         and m.label == "CandidateTarget"),
        "ct": first_rx(data["interp"], lambda m: tgt(m)
                       and m.label == "ConfirmedThreat"),
        "mission": first_rx(data["mission"], tgt),
        "task": first_rx(data["task"], tgt),
        "auth": first_rx(data["auth"], lambda m: tgt(m)
                         and m.decision in AUTHORISE),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reproduce thesis Tables 6.1-6.2 on the receive axis.")
    ap.add_argument("bags", nargs="+", help="bag directories")
    args = ap.parse_args()

    runs = []
    for bag in sorted(args.bags):
        if not os.path.isfile(os.path.join(bag, "metadata.yaml")):
            continue
        print(f"[receive-axis] reading {bag} ...", file=sys.stderr)
        runs.append(instants(read_bag(bag)))
    if not runs:
        print("no readable bags", file=sys.stderr)
        return 1

    print(f"THESIS TABLES ON THE RECEIVE AXIS ({len(runs)} runs, "
          f"recorder wall-clock seconds)")
    print(f"{'metric':<20}{'n':>4}{'mean':>9}{'median':>9}{'sd(n-1)':>9}"
          f"{'min':>9}{'max':>9}")
    for label, a, b in ROWS:
        vals = [r[b] - r[a] for r in runs
                if r.get(a) is not None and r.get(b) is not None]
        s = describe(vals)
        if s is None:
            print(f"{label:<20}{0:>4}{'n/a':>9}")
            continue
        print(f"{label:<20}{s['n']:>4}{s['mean']:>9.2f}{s['median']:>9.2f}"
              f"{s['sd']:>9.2f}{s['min']:>9.2f}{s['max']:>9.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())