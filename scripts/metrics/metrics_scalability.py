#!/usr/bin/env python3
# Copyright 2026 Luca D'Aurizio
# Licensed under the Apache License, Version 2.0 (the "License").
"""Group 5 metrics: coordination overhead vs swarm size.

The IET paper states TB-CSPN has "sub-linear coordination overhead as swarm
size increases", from "hierarchical token routing and localised concurrency
windows", validated analytically and in the PoC. This measures it on the
digital twin, from the bags produced by bench_coordination.sh.

For each fleet size N, the dispatch transition (T7) was run in isolation and a
fixed number M of missions injected. This module counts, per N:

  - missions injected (M, the input),
  - vehicle tasks emitted (the coordination traffic the dispatch produced),
  - tasks per mission.

The headline: the dispatch emits exactly two tasks per mission (intercept to
the nearest UAV, observe to the UGV) regardless of N, so the coordination
message overhead is CONSTANT in the fleet size -- flat, not growing. Compared
with a naive peer-to-peer scheme that would cost O(N^2) messages, this is
strongly sub-linear, confirming the paper's claim on the twin.

This is deliberately separate from bench_vehicles.sh, which measures the
simulator's physics cost (RTF drop under PX4/Gazebo lockstep). Coordination
overhead and simulation cost are different axes.

Usage:
    python3 scripts/metrics/metrics_scalability.py bags/coord
"""
import os
import sys
import re
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics_chain import read_bag  # noqa: E402


def analyse_dir(coord_dir):
    # find all coord-N* bags
    bags = sorted(glob.glob(os.path.join(coord_dir, "coord-N*")))
    if not bags:
        print(f"  no coord-N* bags in {coord_dir}")
        return

    rows = []
    for bag in bags:
        m = re.search(r"coord-N(\d+)", os.path.basename(bag))
        if not m:
            continue
        n = int(m.group(1))
        d = read_bag(bag)
        n_missions = len(d.get("/mission_tokens", []))
        n_tasks = len(d.get("/vehicle_tasks", []))
        per = (n_tasks / n_missions) if n_missions else 0.0
        rows.append((n, n_missions, n_tasks, per))

    rows.sort(key=lambda r: r[0])

    print("=" * 66)
    print("  Group 5 - coordination overhead vs swarm size")
    print("=" * 66)
    print(f"  {'fleet N':>8}  {'missions':>9}  {'tasks':>7}  {'tasks/mission':>14}")
    print("  " + "-" * 46)
    for n, miss, tasks, per in rows:
        print(f"  {n:>8}  {miss:>9}  {tasks:>7}  {per:>14.2f}")
    print("  " + "-" * 46)

    # verdict: is the per-mission task count constant in N?
    pers = [per for _, _, _, per in rows if per > 0]
    if pers:
        lo, hi = min(pers), max(pers)
        flat = (hi - lo) < 0.05  # essentially constant
        tasks_list = [t for _, _, t, _ in rows]
        tlo, thi = min(tasks_list), max(tasks_list)
        task_flat = (thi - tlo) <= 1  # allow a 1-task jitter from queue timing
        print(f"  tasks/mission range: [{lo:.2f}, {hi:.2f}]")
        print(f"  total tasks range:   [{tlo}, {thi}] across fleet sizes "
              f"{rows[0][0]}..{rows[-1][0]}")
        print("-" * 66)
        if flat and task_flat:
            print("  coordination overhead is CONSTANT in fleet size (flat).")
            print("  -> strongly sub-linear vs an O(N^2) peer-to-peer scheme.")
            print("  -> confirms the paper's sub-linear-overhead claim on the twin.")
        else:
            print("  coordination overhead varies with N; inspect the runs.")
    print("=" * 66)


def main():
    ap = argparse.ArgumentParser(description="Group 5 scalability metrics")
    ap.add_argument("coord_dir", nargs="?", default="bags/coord",
                    help="directory containing coord-N* bags")
    args = ap.parse_args()
    analyse_dir(args.coord_dir)


if __name__ == "__main__":
    main()
