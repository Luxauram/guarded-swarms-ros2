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
# @file aggregate_layer.py
#
# Aggregate the Group-2 layer-property metrics across many runs. Companion to
# aggregate_metrics.py (which does Group 1). Because the layer metrics are
# measured on the detection chain up to ConfirmedThreat, they are defined even
# for runs that did not complete the human-in-the-loop release -- so every
# recorded run contributes, not only the completed ones.
#
# USAGE
#   source install/setup.bash
#   python3 scripts/metrics/aggregate_layer.py bags/coastal-*/ --json agg_layer.json
# =============================================================================
import argparse
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from metrics_chain import read_bag
    from metrics_layer import compute
except ImportError as e:
    sys.stderr.write(
        "error: could not import metrics modules ({}).\n"
        "Keep aggregate_layer.py next to metrics_chain.py and metrics_layer.py.\n"
        .format(e))
    sys.exit(2)


def mean_std(values):
    """Compute the mean and population standard deviation of a list.

    @param values  List of numeric values.
    @return        Tuple (mean, std). Returns (None, None) for an empty list
                   and (mean, 0.0) for a single value.
    """
    n = len(values)
    if n == 0:
        return None, None
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / n
    return m, math.sqrt(var)


def aggregate(bag_dirs):
    """Collect layer metrics across runs into flat lists per quantity.

    Each bag is read and passed through metrics_layer.compute(); the per-run
    results are accumulated into lists so that summary statistics can be taken
    over the whole set of runs.

    @param bag_dirs  Iterable of rosbag2 directory paths to aggregate.
    @return          Dict with keys n (run count), acc (fusion acceptance per
                     join), obs_src / interp_lab (census counts per source /
                     label), obs_rate / interp_rate, quiesce (gaps), and
                     bounded_true (count of bounded runs).
    """
    acc = {"T3": [], "T5": []}                 # fusion acceptance per join
    obs_src = {}                               # census counts per source
    interp_lab = {}                            # census counts per label
    obs_rate, interp_rate = [], []
    quiesce = []
    bounded_true = 0
    n = 0

    for bag in bag_dirs:
        r = compute(read_bag(bag), bag)
        n += 1
        for join in ("T3", "T5"):
            f = r.fusion.get(join)
            if f and f.get("acceptance") is not None:
                acc[join].append(f["acceptance"])
        for s, c in r.obs_by_source.items():
            obs_src.setdefault(s, []).append(c)
        for lab, c in r.interp_by_label.items():
            interp_lab.setdefault(lab, []).append(c)
        if r.obs_rate_hz is not None:
            obs_rate.append(r.obs_rate_hz)
        if r.interp_rate_hz is not None:
            interp_rate.append(r.interp_rate_hz)
        if r.quiesce_gap_s is not None:
            quiesce.append(r.quiesce_gap_s)
        if r.bounded:
            bounded_true += 1

    return {
        "n": n, "acc": acc, "obs_src": obs_src, "interp_lab": interp_lab,
        "obs_rate": obs_rate, "interp_rate": interp_rate,
        "quiesce": quiesce, "bounded_true": bounded_true,
    }


def print_report(a):
    """Print the aggregated layer metrics as a human-readable report.

    @param a  Aggregate dict produced by aggregate().
    @return   None.
    """
    n = a["n"]
    print()
    print("=" * 70)
    print("  Layer-property metrics, aggregated over {} run(s)".format(n))
    print("=" * 70)
    print("  4. fusion acceptance (mean +/- std)")
    for join in ("T3", "T5"):
        vals = a["acc"][join]
        if vals:
            m, sd = mean_std(vals)
            print("     {}:  {:5.1f}% +/- {:4.1f}%   (min {:5.1f}%, max {:5.1f}%, "
                  "n={})".format(join, m * 100, sd * 100,
                                 min(vals) * 100, max(vals) * 100, len(vals)))
        else:
            print("     {}:  n/a".format(join))
    print()
    print("  5. token census (mean +/- std per run)")
    print("     observations by source:")
    for s in sorted(a["obs_src"]):
        m, sd = mean_std(a["obs_src"][s])
        print("        {:10s} {:7.1f} +/- {:5.1f}".format(s, m, sd))
    print("     interpretations by label:")
    for lab in sorted(a["interp_lab"]):
        m, sd = mean_std(a["interp_lab"][lab])
        print("        {:22s} {:7.1f} +/- {:5.1f}".format(lab, m, sd))
    if a["obs_rate"]:
        m, sd = mean_std(a["obs_rate"])
        print("     obs rate:    {:5.2f} +/- {:4.2f} Hz".format(m, sd))
    if a["interp_rate"]:
        m, sd = mean_std(a["interp_rate"])
        print("     interp rate: {:5.2f} +/- {:4.2f} Hz".format(m, sd))
    print()
    print("  6. bounded execution")
    if a["quiesce"]:
        m, sd = mean_std(a["quiesce"])
        print("     quiesce gap: {:5.2f} +/- {:4.2f} s   (max {:.2f} s)".format(
            m, sd, max(a["quiesce"])))
    print("     bounded in {}/{} runs".format(a["bounded_true"], n))
    print("=" * 70)
    print()


def build_json(a):
    """Convert the aggregate dict into a JSON-serialisable summary.

    Each quantity is reduced to a mean/std/min/max/n record via the local ms()
    helper.

    @param a  Aggregate dict produced by aggregate().
    @return   Dict ready for json.dump, keyed by metric name.
    """
    def ms(vals):
        """Reduce a list to a summary-statistics record.

        @param vals  List of numeric values.
        @return      Dict with mean, std, min, max, and n.
        """
        m, sd = mean_std(vals)
        return {"mean": m, "std": sd,
                "min": (min(vals) if vals else None),
                "max": (max(vals) if vals else None),
                "n": len(vals)}

    return {
        "n_runs": a["n"],
        "fusion_acceptance": {j: ms(a["acc"][j]) for j in ("T3", "T5")},
        "obs_by_source": {s: ms(v) for s, v in a["obs_src"].items()},
        "interp_by_label": {lab: ms(v) for lab, v in a["interp_lab"].items()},
        "obs_rate_hz": ms(a["obs_rate"]),
        "interp_rate_hz": ms(a["interp_rate"]),
        "quiesce_gap_s": ms(a["quiesce"]),
        "bounded_runs": a["bounded_true"],
    }


def main():
    """Parse arguments, aggregate the matching bags, and report.

    Resolves the bag arguments (globs or paths), keeps only directories that
    contain a .db3, deduplicates them, prints the report, and optionally writes
    the aggregate as JSON.

    @return  None.
    """
    ap = argparse.ArgumentParser(
        description="Aggregate Group-2 layer metrics across runs.")
    ap.add_argument("bags", nargs="+", help="bag directories or globs")
    ap.add_argument("--json", help="write the aggregate as JSON")
    args = ap.parse_args()

    resolved = []
    for pat in args.bags:
        matches = sorted(glob.glob(pat)) if any(c in pat for c in "*?[") else [pat]
        for m in matches:
            if glob.glob(os.path.join(m, "*.db3")):
                resolved.append(m)

    seen, bag_dirs = set(), []
    for b in resolved:
        k = os.path.normpath(b)
        if k not in seen:
            seen.add(k)
            bag_dirs.append(b)

    if not bag_dirs:
        sys.stderr.write("error: no bags with a .db3 matched.\n")
        sys.exit(1)

    a = aggregate(bag_dirs)
    print_report(a)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(build_json(a), f, indent=2)
        print("  aggregate written to {}".format(args.json))


if __name__ == "__main__":
    main()