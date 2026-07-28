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
# @file aggregate_metrics.py
#
# Aggregate chain-latency metrics across MANY recorded runs.
#
# A single run is one sample; a thesis result is a distribution. This script
# runs metrics_chain.compute() on every bag it is given and reports, for each
# metric, the mean, standard deviation, min, max and the number of runs that
# contributed a value. That is what turns "the chain took 39.6 s once" into
# "the chain takes 39.6 +/- 2.1 s over 20 runs", which is what belongs in the
# evaluation chapter and in front of Leonardo.
#
# It reuses metrics_chain.py rather than re-deriving anything: the per-run
# maths lives in one place.
#
# USAGE
#   source install/setup.bash
#   # aggregate every coastal bag:
#   python3 scripts/metrics/aggregate_metrics.py bags/coastal-*/
#   # or an explicit list, and write JSON:
#   python3 scripts/metrics/aggregate_metrics.py bags/run1/ bags/run2/ --json agg.json
#
# Runs whose chain did not complete (no mission formed) still contribute the
# metrics they do have (e.g. obs->candidate); a metric is averaged only over
# the runs where it is defined, and the contributing-run count is shown so a
# partial run never silently biases a mean.
# =============================================================================

import argparse
import glob
import json
import math
import os
import sys

# Reuse the single-run machinery. This file sits next to metrics_chain.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from metrics_chain import read_bag, compute, resolve_bag
except ImportError as e:
    sys.stderr.write(
        "error: could not import metrics_chain ({}).\n"
        "Keep aggregate_metrics.py next to metrics_chain.py.\n".format(e))
    sys.exit(2)


# The latency fields we aggregate, in report order, with human labels.
METRICS = [
    ("end_to_end_s",                  "end-to-end: ObsToken -> Mission"),
    ("obs_to_candidate_s",            "ObsToken -> CandidateTarget"),
    ("candidate_to_confirmed_s",      "CandidateTarget -> ConfirmedThreat"),
    ("confirmed_to_mission_s",        "ConfirmedThreat -> Mission"),
    ("mission_to_task_s",             "Mission -> VehicleTask"),
    ("system_obs_to_confirmed_s",     "[system] Obs -> ConfirmedThreat"),
    ("human_wait_confirmed_to_auth_s","[human]  Confirmed -> authorisation"),
    ("post_auth_to_task_s",           "[system] authorisation -> Task"),
]


def mean_std(values):
    """
    Sample mean and (population) standard deviation of a list of floats.

    @param values  Non-empty list of numbers.
    @return        (mean, std). std is 0.0 for a single sample.
    """
    n = len(values)
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / n
    return m, math.sqrt(var)


def aggregate(bag_dirs):
    """
    Compute per-run metrics for every bag and collect them per metric.

    @param bag_dirs  List of resolved bag directories.
    @return          (per_metric_values, per_run_results)
                     per_metric_values: field -> list of values (only where
                     the metric was defined in that run).
                     per_run_results: list of ChainMetrics (for reference).
    """
    per_metric = {field: [] for field, _ in METRICS}
    per_run = []
    for bag in bag_dirs:
        data = read_bag(bag)
        r = compute(data, bag)
        per_run.append(r)
        for field, _ in METRICS:
            v = getattr(r, field)
            if v is not None:
                per_metric[field].append(v)
    return per_metric, per_run


def print_report(per_metric, per_run, n_bags):
    """Print the aggregate table."""
    print()
    print("=" * 74)
    print("  Chain-latency metrics, aggregated over {} run(s)   "
          "[sim time, seconds]".format(n_bags))
    print("=" * 74)

    # How many runs actually formed a mission (completed the chain).
    completed = sum(1 for r in per_run if r.t_first_mission is not None)
    print("  runs that completed the chain (mission formed): {}/{}".format(
        completed, n_bags))
    print("-" * 74)
    print("  {:38s} {:>8s} {:>8s} {:>7s} {:>7s} {:>4s}".format(
        "metric", "mean", "std", "min", "max", "n"))
    print("-" * 74)
    for field, label in METRICS:
        vals = per_metric[field]
        if not vals:
            print("  {:38s} {:>8s} {:>8s} {:>7s} {:>7s} {:>4d}".format(
                label, "n/a", "n/a", "n/a", "n/a", 0))
            continue
        m, sd = mean_std(vals)
        print("  {:38s} {:8.3f} {:8.3f} {:7.3f} {:7.3f} {:4d}".format(
            label, m, sd, min(vals), max(vals), len(vals)))
    print("=" * 74)
    print("  'n' is how many runs contributed a value for that metric; a metric")
    print("  averaged over fewer runs than the total had incomplete runs.")
    print("=" * 74)
    print()


def build_json(per_metric, per_run, n_bags):
    """Assemble a JSON-serialisable summary for the dashboard / archiving."""
    completed = sum(1 for r in per_run if r.t_first_mission is not None)
    out = {
        "n_runs": n_bags,
        "n_completed": completed,
        "metrics": {},
        "runs": [r.bag for r in per_run],
    }
    for field, label in METRICS:
        vals = per_metric[field]
        if vals:
            m, sd = mean_std(vals)
            out["metrics"][field] = {
                "label": label,
                "mean": m, "std": sd,
                "min": min(vals), "max": max(vals),
                "n": len(vals),
            }
        else:
            out["metrics"][field] = {
                "label": label, "mean": None, "std": None,
                "min": None, "max": None, "n": 0,
            }
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Aggregate chain-latency metrics across many runs.")
    ap.add_argument("bags", nargs="+",
                    help="bag directories or globs (e.g. bags/coastal-*/)")
    ap.add_argument("--json", help="write the aggregate summary as JSON")
    args = ap.parse_args()

    # Expand globs and resolve each to a concrete bag directory.
    resolved = []
    for pat in args.bags:
        matches = sorted(glob.glob(pat)) if any(c in pat for c in "*?[") else [pat]
        for m in matches:
            if glob.glob(os.path.join(m, "*.db3")):
                resolved.append(m)
    # De-duplicate while preserving order.
    seen = set()
    bag_dirs = []
    for b in resolved:
        key = os.path.normpath(b)
        if key not in seen:
            seen.add(key)
            bag_dirs.append(b)

    if not bag_dirs:
        sys.stderr.write("error: no bags with a .db3 matched the arguments.\n")
        sys.exit(1)

    per_metric, per_run = aggregate(bag_dirs)
    print_report(per_metric, per_run, len(bag_dirs))

    if args.json:
        with open(args.json, "w") as f:
            json.dump(build_json(per_metric, per_run, len(bag_dirs)), f, indent=2)
        print("  aggregate written to {}".format(args.json))


if __name__ == "__main__":
    main()
