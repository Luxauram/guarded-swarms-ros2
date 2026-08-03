#!/usr/bin/env python3
# =============================================================================
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
# =============================================================================

# =============================================================================
# @file metrics_layer.py
#
# Offline layer-property metrics (Group 2) for the Guarded Swarms coastal
# pipeline. Where metrics_chain.py measures how FAST the chain runs, this
# measures PROPERTIES the TB-CSPN layer claims to have.
#
# Reuses metrics_chain.read_bag so the bag reading lives in one place.
#
# WHAT IT COMPUTES (Group 2)
#   4. Fusion acceptance: how many of the interpretation tokens entering a join
#      (T3, T5) found a partner and fused, versus how many expired unmatched.
#      This quantifies the time-windowed synchronisation the paper's rule
#      abs((t0'+ttl') - (t0+ttl)) <= ths actually performs.
#   5. Token census + TTL turnover: counts per source and per label, and the
#      rate at which tokens are produced. Shows the working volume of the chain.
#   6. Bounded execution: after the last observation arrives, does token
#      production stop within a bounded time, or does the net keep firing with
#      no new input? The paper claims bounded execution; this checks the chain
#      quiesces when the stimulus ends.
#
# USAGE
#   source install/setup.bash
#   python3 scripts/metrics/metrics_layer.py bags/coastal-YYYYMMDD-HHMMSS/
#   python3 scripts/metrics/metrics_layer.py bags/coastal-*/ --json layer.json
# =============================================================================
import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from metrics_chain import read_bag, resolve_bag, stamp_to_s
except ImportError as e:
    sys.stderr.write(
        "error: could not import metrics_chain ({}).\n"
        "Keep metrics_layer.py next to metrics_chain.py, and source the "
        "workspace first.\n".format(e))
    sys.exit(2)

# The chain's structure, so the fusion metric knows each join's inputs/output.
# T3: PossibleUAV + LikelyDroneLink -> CandidateTarget
# T5: CandidateTarget + ConfirmedAerialObject -> ConfirmedThreat
JOINS = [
    ("T3", "PossibleUAV", "LikelyDroneLink", "CandidateTarget"),
    ("T5", "CandidateTarget", "ConfirmedAerialObject", "ConfirmedThreat"),
]

# First-level interpretations, for the census (which raw source feeds which).
FIRST_LEVEL = {
    "PossibleUAV": "radar",
    "LikelyDroneLink": "rf",
    "ConfirmedAerialObject": "eo",
}

# Bounded-execution sanity bound: the chain must stop producing within a few
# TTLs of the last observation. ~15 s = threat TTL 10 s plus margin. This is a
# sanity bound, not a formal proof; state it as such in the thesis.
QUIESCE_BOUND_S = 15.0


@dataclass
class LayerMetrics:
    """All Group-2 layer-property figures for one run."""
    bag: str = ""
    target_id: str = ""
    # 4. Fusion acceptance, per join.
    fusion: dict = field(default_factory=dict)
    # 5. Census.
    obs_by_source: dict = field(default_factory=dict)
    interp_by_label: dict = field(default_factory=dict)
    obs_rate_hz: Optional[float] = None
    interp_rate_hz: Optional[float] = None
    # 6. Bounded execution.
    last_obs_t: Optional[float] = None
    last_interp_t: Optional[float] = None
    quiesce_gap_s: Optional[float] = None   # last_interp - last_obs
    bounded: Optional[bool] = None
    notes: list = field(default_factory=list)


def pick_target(data: dict) -> Optional[str]:
    """Choose the busiest target_id among the observations.

    @param data  The read_bag() output.
    @return      A target_id string, or None if there are no observations.
    """
    counts = {}
    for _, m in data.get("/obs_tokens", []):
        tid = getattr(m, "target_id", "")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
    return max(counts, key=counts.get) if counts else None


def compute(data: dict, bag_dir: str) -> LayerMetrics:
    """Compute all Group-2 layer-property metrics from a read bag.

    @param data     read_bag() output.
    @param bag_dir  bag path, stored in the result for reference.
    @return         A populated LayerMetrics.
    """
    r = LayerMetrics(bag=os.path.basename(os.path.normpath(bag_dir)))
    obs = data.get("/obs_tokens", [])
    interp = data.get("/interp_tokens", [])
    target = pick_target(data)
    if target is None:
        r.notes.append("no observations with a target_id; nothing to measure")
        return r
    r.target_id = target

    obs_t = [(stamp_to_s(m.t), m) for _, m in obs if m.target_id == target]
    interp_t = [(stamp_to_s(m.t), m) for _, m in interp if m.target_id == target]

    # --- 5. census ---
    for _, m in obs_t:
        s = getattr(m, "source", "?")
        r.obs_by_source[s] = r.obs_by_source.get(s, 0) + 1
    for _, m in interp_t:
        lab = getattr(m, "label", "?")
        r.interp_by_label[lab] = r.interp_by_label.get(lab, 0) + 1

    # Production rates over the active span (first to last token, sim time).
    if len(obs_t) >= 2:
        span = max(t for t, _ in obs_t) - min(t for t, _ in obs_t)
        r.obs_rate_hz = (len(obs_t) - 1) / span if span > 0 else None
    if len(interp_t) >= 2:
        span = max(t for t, _ in interp_t) - min(t for t, _ in interp_t)
        r.interp_rate_hz = (len(interp_t) - 1) / span if span > 0 else None

    # --- 4. fusion acceptance, per join ---
    # For a join A + B -> C: every emitted C consumed one A and one B. The A/B
    # tokens that were produced but never became a C expired unmatched. So:
    #   fusions      = count(C)
    #   inputs_A     = count(A),  inputs_B = count(B)
    #   consumed_A   = fusions,   consumed_B = fusions
    #   acceptance   = fusions / min(inputs_A, inputs_B)   (the limiting side)
    # min() is used because a fusion needs one of each: the scarcer input caps
    # how many fusions are even possible, so it is the honest denominator.
    for name, la, lb, lc in JOINS:
        na = r.interp_by_label.get(la, 0)
        nb = r.interp_by_label.get(lb, 0)
        nc = r.interp_by_label.get(lc, 0)
        limiting = min(na, nb)
        acc = (nc / limiting) if limiting > 0 else None
        r.fusion[name] = {
            "input_a": la, "input_b": lb, "output": lc,
            "count_a": na, "count_b": nb, "fusions": nc,
            "limiting_input": limiting,
            "acceptance": acc,
        }

    # --- 6. bounded execution ---
    # After the last observation, higher-level tokens may still fire for a short
    # while (the last buffered tokens fusing), but production must then stop:
    # the gap between the last interp token and the last obs token should be
    # bounded, on the order of the chain's TTLs, not unbounded. A very large or
    # ever-growing gap would mean the net keeps firing without input.
    if obs_t:
        r.last_obs_t = max(t for t, _ in obs_t)
    if interp_t:
        r.last_interp_t = max(t for t, _ in interp_t)
    if r.last_obs_t is not None and r.last_interp_t is not None:
        r.quiesce_gap_s = r.last_interp_t - r.last_obs_t
        r.bounded = r.quiesce_gap_s <= QUIESCE_BOUND_S
        if not r.bounded:
            r.notes.append(
                "interp production continued {:.1f}s after the last "
                "observation (> {:.0f}s): inspect whether a token kept "
                "re-firing".format(r.quiesce_gap_s, QUIESCE_BOUND_S))
    return r


def fmt_pct(v: Optional[float]) -> str:
    """Format a fraction as a percentage, or n/a when None.

    @param v  Fraction in [0, 1], or None.
    @return   "{:5.1f}%" string, or an "n/a" placeholder.
    """
    return "   n/a" if v is None else "{:5.1f}%".format(v * 100.0)


def fmt_f(v: Optional[float], unit="") -> str:
    """Format a float with an optional unit, or n/a when None.

    @param v     Value, or None.
    @param unit  Unit suffix appended after the number.
    @return      "{:.2f}<unit>" string, or "n/a".
    """
    return "n/a" if v is None else "{:.2f}{}".format(v, unit)


def print_report(r: LayerMetrics):
    """Print a human-readable table of the layer metrics for one run.

    @param r  Populated LayerMetrics from compute().
    @return   None.
    """
    print()
    print("=" * 66)
    print("  Layer-property metrics (Group 2)")
    print("  bag:    {}".format(r.bag))
    print("  target: {}".format(r.target_id or "(none)"))
    print("=" * 66)
    print("  4. fusion acceptance (time-windowed join)")
    for name, f in r.fusion.items():
        print("     {}: {} + {} -> {}".format(
            name, f["input_a"], f["input_b"], f["output"]))
        print("        inputs: {}={}, {}={}  fusions(out)={}  "
              "acceptance={}".format(
                  f["input_a"], f["count_a"], f["input_b"], f["count_b"],
                  f["fusions"], fmt_pct(f["acceptance"])))
    print()
    print("  5. token census")
    print("     observations by source:")
    for s, c in sorted(r.obs_by_source.items()):
        print("        {:10s} {}".format(s, c))
    print("     interpretations by label:")
    for lab, c in sorted(r.interp_by_label.items()):
        print("        {:22s} {}".format(lab, c))
    print("     production rate:  obs {}   interp {}".format(
        fmt_f(r.obs_rate_hz, " Hz"), fmt_f(r.interp_rate_hz, " Hz")))
    print()
    print("  6. bounded execution")
    print("     last observation (sim t):   {}".format(fmt_f(r.last_obs_t, " s")))
    print("     last interpretation (sim t):{}".format(fmt_f(r.last_interp_t, " s")))
    print("     quiesce gap (interp - obs): {}".format(
        fmt_f(r.quiesce_gap_s, " s")))
    print("     bounded:                    {}".format(
        "yes" if r.bounded else ("no" if r.bounded is not None else "n/a")))
    if r.notes:
        print("-" * 66)
        print("  notes:")
        for n in r.notes:
            print("    - {}".format(n))
    print("=" * 66)
    print()


def main():
    """Parse arguments, compute the layer metrics for one bag, and report.

    @return  None.
    """
    ap = argparse.ArgumentParser(
        description="Offline layer-property metrics (Group 2).")
    ap.add_argument("bag", help="bag directory or glob (bags/coastal-*/)")
    ap.add_argument("--json", help="also write the metrics as JSON")
    args = ap.parse_args()
    bag_dir = resolve_bag(args.bag)
    data = read_bag(bag_dir)
    result = compute(data, bag_dir)
    print_report(result)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(asdict(result), f, indent=2)
        print("  metrics written to {}".format(args.json))


if __name__ == "__main__":
    main()