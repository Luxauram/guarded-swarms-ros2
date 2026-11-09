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
analyze_faults.py - the tables of the faulty-UAV-worker runs of a campaign.

Read-only: it reads the manifest and the bags of a campaign recorded by
scripts/experiments/run_campaign.sh, and writes tables and a CSV file.

The configurations analysed are those of configurations.conf that set
UAV_FAULT or VETO_BY. Each run uses the attempt that analyze_campaign.py
uses: the first valid attempt whose recording passes its checks. A run
without one is left out and listed.

The faulty UAV is the one that received the task (the first UAV task of the
bag). With UAV_FAULT=obstacle it flies into its fault building:
  - impact: its centre comes within CONTACT_M of the footprint of the
    building (horizontal distance, below the roof). The impact speed is the
    horizontal speed of the last position before it. After an impact the
    position from PX4 is not used: the estimate of a crashed vehicle is not
    its position;
  - closest distance to the wall, and distance at the end of the recording
    for a UAV that did not hit;
  - intervention, message by message: first lidar range below the
    proximity threshold of the board (TRIP_M), first unsafe safety_status,
    first hold of the safety gate at PX4;
  - commands let through: setpoints that reached PX4 while the board
    reported unsafe and were not holds.
For the UAVs without a fault (both UAVs of a configuration without
UAV_FAULT, the UAV without the task otherwise): the holds of the gate, and
the unsafe safety_status samples while airborne (above AIRBORNE_M).

Times are in simulated time: the receive time of every message mapped onto
the recorded /clock, as in audit_recordings.py (the lidar range and the
safety status carry no usable stamp). A setpoint at PX4 is a hold when its
position matches none of the setpoints the worker proposed within
PAIR_WINDOW_S of it, since the gate forwards a setpoint unchanged.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/analyze_faults.py bags/campaigns/<campaign> \\
        [--out results/<campaign>]

Output, in --out (default results/<campaign>):
    faults.md    the tables, also printed
    faults.csv   one line per run

@author Luca D'Aurizio
"""

import argparse
import bisect
import csv
import math
import os
import sys
from dataclasses import dataclass, fields
from typing import Dict, List, Optional, Tuple

from analyze_campaign import (Attempt, analyze_run, bag_of, md_table,
                              rate_cell, read_env, read_manifest)
from audit_timing import ClockMap, describe, storage_id


# =============================================================================
# The scenario, as in coastal_pipeline.launch.py and coastal.sdf
# =============================================================================
@dataclass(frozen=True)
class Building:
    """A building of the world: centre and yaw (world ENU), size, height."""
    name: str
    x: float
    y: float
    yaw: float
    size_x: float
    size_y: float
    height: float


# System id of a UAV: its namespace, spawn point (world ENU) and the fault
# building of its worker (UAV0_FAULT_TARGET, UAV1_FAULT_TARGET).
UAVS: Dict[int, Tuple[str, Tuple[float, float], Building]] = {
    1: ("", (-24.0, -24.0),
        Building("building_0_5", 17.88, -47.34, 0.042, 16.0, 16.0, 18.0)),
    2: ("/px4_1", (24.0, -24.0),
        Building("building_0_4", -22.53, -47.07, -0.017, 22.0, 18.0, 34.0)),
}
TRIP_M = 10.0          # proximity threshold of the UAV boards
CONTACT_M = 0.5        # centre this close to a wall: impact (x500 ~0.35 m)
STATUS_UNSAFE = 0.5    # safety_status below this: unsafe
AIRBORNE_M = 3.0       # above this altitude a UAV is airborne
PAIR_WINDOW_S = 0.5    # a forwarded setpoint has a proposed twin this close
SAME_M = 1e-3          # positions this close are the same setpoint

POSITION = "fmu/out/vehicle_local_position_v1"
PROXIMITY = "drone/proximity"
STATUS = "safety_status"
PROPOSED = "trajectory_setpoint_proposed"
TO_PX4 = "fmu/in/trajectory_setpoint"


# =============================================================================
# Bag reading
# =============================================================================
def read_bag(bag_dir: str) -> Dict[str, list]:
    """Read /clock, the tasks and the safety layer of the two UAVs.

    @return {topic: [(rx_s, msg), ...]}, rx_s relative to the first message.
    """
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as e:
        sys.exit("Cannot import the ROS 2 Python modules ({}).\n"
                 "Run `source /opt/ros/humble/setup.bash && "
                 "source install/setup.bash` first.".format(e))
    want = {"/clock", "/vehicle_tasks"} | {
        ns + "/" + t for ns, _, _ in UAVS.values()
        for t in (POSITION, PROXIMITY, STATUS, PROPOSED, TO_PX4)}
    out: Dict[str, list] = {t: [] for t in want}
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=storage_id(bag_dir)),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                    output_serialization_format="cdr"))
    classes = {}
    for topic in reader.get_all_topics_and_types():
        if topic.name in want:
            classes[topic.name] = get_message(topic.type)
    if not classes:
        return out
    reader.set_filter(rosbag2_py.StorageFilter(topics=list(classes)))
    base_ns = None
    while reader.has_next():
        topic, data, recv_ns = reader.read_next()
        if topic not in classes:
            continue
        if base_ns is None:
            base_ns = recv_ns
        out[topic].append(((recv_ns - base_ns) * 1e-9,
                           deserialize_message(data, classes[topic])))
    return out


# =============================================================================
# One run
# =============================================================================
def wall_m(x: float, y: float, b: Building) -> float:
    """Horizontal distance from (x, y) to the footprint of b, 0 inside."""
    c, s = math.cos(-b.yaw), math.sin(-b.yaw)
    u = c * (x - b.x) - s * (y - b.y)
    v = s * (x - b.x) + c * (y - b.y)
    return math.hypot(max(abs(u) - b.size_x / 2, 0.0),
                      max(abs(v) - b.size_y / 2, 0.0))


def last_before(times: List[float], values: list, t: float):
    """Value of the last sample at or before t, or None."""
    i = bisect.bisect_right(times, t) - 1
    return values[i] if i >= 0 else None


@dataclass
class FaultRun:
    """One run. Times in seconds of simulated time, from the task."""
    configuration: str = ""
    run: int = 0
    seed: int = 0
    attempt: int = 0
    campaign: str = ""
    clean: bool = False
    problems: str = ""
    veto_by: str = "worker"
    fault: str = "none"
    uav: Optional[int] = None          # system id of the UAV with the task
    impact: Optional[bool] = None
    impact_s: Optional[float] = None
    impact_speed_mps: Optional[float] = None
    closest_wall_m: Optional[float] = None
    end_wall_m: Optional[float] = None
    top_speed_mps: Optional[float] = None
    lidar_trip_s: Optional[float] = None
    unsafe_s: Optional[float] = None
    hold_s: Optional[float] = None
    lidar_to_unsafe_ms: Optional[float] = None
    unsafe_to_hold_ms: Optional[float] = None
    lidar_to_hold_ms: Optional[float] = None
    let_through: Optional[int] = None
    held_to_end: Optional[bool] = None
    healthy_holds: int = 0
    healthy_unsafe_airborne: int = 0


class UavTrack:
    """The safety layer of one UAV in simulated time."""

    def __init__(self, data: Dict[str, list], clk: ClockMap, sid: int):
        ns, spawn, self.building = UAVS[sid]

        def mapped(topic: str, value) -> Tuple[List[float], list]:
            pairs = [(clk(rx), value(m)) for rx, m in data[ns + "/" + topic]
                     if clk.inside(rx)]
            pairs = [p for p in pairs if p[1] is not None]
            return [p[0] for p in pairs], [p[1] for p in pairs]

        # World ENU from PX4's local NED, which starts at the spawn point.
        self.pos = mapped(POSITION, lambda m: (
            spawn[0] + m.y, spawn[1] + m.x, -m.z, math.hypot(m.vx, m.vy)))
        self.lidar = mapped(PROXIMITY, lambda m: m.range if (
            math.isfinite(m.range) and m.range < m.max_range) else None)
        self.status = mapped(STATUS, lambda m: m.data)
        self.proposed = mapped(PROPOSED, lambda m: tuple(m.position))
        to_px4 = mapped(TO_PX4, lambda m: tuple(m.position))
        # Each setpoint at PX4 with whether it is a hold of the gate.
        self.px4 = [(t, self.is_hold(t, p)) for t, p in zip(*to_px4)]

    def is_hold(self, t: float, p: tuple) -> bool:
        times, values = self.proposed
        lo = bisect.bisect_left(times, t - PAIR_WINDOW_S)
        hi = bisect.bisect_right(times, t + PAIR_WINDOW_S)
        return not any(all(abs(a - b) <= SAME_M for a, b in zip(p, q))
                       for q in values[lo:hi])

    def first(self, series: Tuple[List[float], list], t0: float, test,
              t1: float = math.inf) -> Optional[float]:
        """Time of the first sample in [t0, t1) that passes the test."""
        for t, v in zip(*series):
            if t0 <= t < t1 and test(v):
                return t
        return None

    def unsafe_airborne(self, t1: float = math.inf) -> int:
        """Unsafe status samples before t1 while the UAV is airborne."""
        n = 0
        for t, v in zip(*self.status):
            if t >= t1 or v >= STATUS_UNSAFE:
                continue
            p = last_before(self.pos[0], self.pos[1], t)
            if p is not None and p[2] > AIRBORNE_M:
                n += 1
        return n


def first_task(data: Dict[str, list], clk: ClockMap
               ) -> Tuple[Optional[int], Optional[float]]:
    """System id and simulated time of the first UAV task of the run."""
    for rx, m in data["/vehicle_tasks"]:
        if m.assigned_system in UAVS and clk.inside(rx):
            return m.assigned_system, clk(rx)
    return None, None


def ms(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b is None else 1000.0 * (b - a)


def analyze_faults(a: Attempt, r: FaultRun) -> None:
    """Fill r from the bag of attempt a."""
    data = read_bag(bag_of(a))
    clk = ClockMap(data["/clock"])
    if not clk.ok():
        r.clean, r.problems = False, "no /clock: no simulated time"
        return
    sid, t_task = first_task(data, clk)
    if sid is None:
        r.clean, r.problems = False, "no UAV task in the run"
        return
    r.uav = sid
    tracks = {s: UavTrack(data, clk, s) for s in UAVS}
    faulty = tracks[sid] if r.fault != "none" else None

    for s, tr in tracks.items():
        if tr is faulty:
            continue
        r.healthy_holds += sum(1 for _, hold in tr.px4 if hold)
        r.healthy_unsafe_airborne += tr.unsafe_airborne()
    if faulty is None:
        return

    tr, b = faulty, faulty.building
    flight = [(t, p) for t, p in zip(*tr.pos) if t >= t_task]
    if not flight:
        r.clean, r.problems = False, "no position of the faulty UAV"
        return
    t_impact = next((t for t, p in flight
                     if wall_m(p[0], p[1], b) <= CONTACT_M
                     and p[2] < b.height), None)
    r.impact = t_impact is not None
    before = [(t, p) for t, p in flight if t_impact is None or t < t_impact]
    t_end = t_impact if r.impact else math.inf
    if r.impact:
        r.impact_s = t_impact - t_task
        r.impact_speed_mps = before[-1][1][3] if before else None
        r.closest_wall_m = 0.0
    else:
        r.closest_wall_m = min(wall_m(p[0], p[1], b) for _, p in before)
        r.end_wall_m = wall_m(before[-1][1][0], before[-1][1][1], b)
    if before:
        r.top_speed_mps = max(p[3] for _, p in before)

    t_lidar = tr.first(tr.lidar, t_task, lambda v: v < TRIP_M, t_end)
    t_unsafe = tr.first(tr.status, t_task, lambda v: v < STATUS_UNSAFE, t_end)
    holds = [t for t, hold in tr.px4 if hold and t >= t_task]
    t_hold = holds[0] if holds and holds[0] < t_end else None
    r.lidar_trip_s = None if t_lidar is None else t_lidar - t_task
    r.unsafe_s = None if t_unsafe is None else t_unsafe - t_task
    r.hold_s = None if t_hold is None else t_hold - t_task
    r.lidar_to_unsafe_ms = ms(t_lidar, t_unsafe)
    r.unsafe_to_hold_ms = ms(t_unsafe, t_hold)
    r.lidar_to_hold_ms = ms(t_lidar, t_hold)

    r.let_through = 0
    for t, hold in tr.px4:
        if t < t_task or t >= t_end or hold:
            continue
        st = last_before(tr.status[0], tr.status[1], t)
        if st is not None and st < STATUS_UNSAFE:
            r.let_through += 1
    if t_hold is not None:
        r.held_to_end = all(hold for t, hold in tr.px4 if t >= t_hold)


# =============================================================================
# Campaign
# =============================================================================
def configuration_vars(path: str) -> Dict[str, Dict[str, str]]:
    """Variables of each configuration of configurations.conf."""
    out: Dict[str, Dict[str, str]] = {}
    with open(path) as f:
        for line in f:
            tokens = line.split("#", 1)[0].split()
            if tokens:
                out[tokens[0]] = dict(t.split("=", 1) for t in tokens[1:]
                                      if "=" in t)
    return out


def select_runs(attempts: List[Attempt], order: List[str],
                envs: Dict[str, Dict[str, str]]
                ) -> Tuple[List[Tuple[FaultRun, Attempt]], List[str]]:
    """The attempt of each run, as analyze_campaign.py chooses it."""
    groups: Dict[Tuple[str, int], List[Attempt]] = {}
    for a in attempts:
        if a.configuration in order:
            groups.setdefault((a.configuration, a.seed), []).append(a)
    runs: List[Tuple[FaultRun, Attempt]] = []
    missing: List[str] = []
    for (c, seed), tries in sorted(groups.items(), key=lambda kv: (
            order.index(kv[0][0]), kv[1][0].run)):
        valid = [a for a in tries if a.valid]
        if not valid:
            missing.append("{} run {} (seed {}): no valid attempt".format(
                c, tries[0].run, seed))
            continue
        used = None
        for a in valid:
            res = analyze_run(a, envs[a.campaign_dir].get("COMMIT", ""))
            used = (a, res)
            if res.clean:
                break
        a, res = used
        runs.append((FaultRun(configuration=c, run=tries[0].run, seed=seed,
                              attempt=a.attempt, campaign=a.campaign,
                              clean=res.clean,
                              problems="; ".join(res.problems)), a))
    return runs, missing


# =============================================================================
# Report
# =============================================================================
def mean_sd(values: list, prec: int = 2) -> str:
    s = describe(values)
    if s is None:
        return "—"
    return "{:.{p}f} ± {:.{p}f} ({})".format(s["mean"], s["sd"], s["n"],
                                              p=prec)


def span(values: list, prec: int = 2) -> str:
    s = describe(values)
    if s is None:
        return "—"
    return "{:.{p}f}–{:.{p}f}".format(s["min"], s["max"], p=prec)


def cell(v, prec: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return "{:.{p}f}".format(v, p=prec)
    return str(v)


def report(name: str, runs: List[FaultRun], order: List[str],
           missing: List[str]) -> List[str]:
    out = ["# Faulty UAV worker: {}".format(name), ""]
    by_conf = {c: [r for r in runs if r.configuration == c] for c in order}
    clean = {c: [r for r in rs if r.clean] for c, rs in by_conf.items()}

    faulty = [c for c in order if any(r.fault != "none" for r in by_conf[c])]
    if faulty:
        out += ["## Faulty worker", ""]
        rows = []
        for c in faulty:
            rs = clean[c]
            hit = [r for r in rs if r.impact]
            miss = [r for r in rs if r.impact is False]
            held = [r for r in rs if r.held_to_end is not None]
            rows.append([
                c, rs[0].veto_by if rs else "—",
                "{}/{}".format(len(rs), len(by_conf[c])),
                rate_cell(len(hit),
                          len([r for r in rs if r.impact is not None])),
                mean_sd([r.impact_speed_mps for r in hit]),
                mean_sd([r.closest_wall_m for r in miss]),
                span([r.closest_wall_m for r in miss]),
                mean_sd([r.end_wall_m for r in miss]),
                mean_sd([float(r.let_through) for r in rs
                         if r.let_through is not None], 1),
                "{}/{}".format(sum(1 for r in held if r.held_to_end),
                               len(held)) if held else "—"])
        out += md_table(["Configuration", "Veto by", "Clean runs",
                         "Impact [95% CI, %]", "Impact speed (m/s)",
                         "Closest to the wall, no impact (m)",
                         "Closest, range (m)", "Distance at the end (m)",
                         "Commands let through while unsafe",
                         "Held to the end"], rows)

        out += ["## Intervention (ms, simulated time)", ""]
        rows = []
        for c in faulty:
            rs = clean[c]
            rows.append([c] + [
                "{} [{}]".format(mean_sd(vals, 0), span(vals, 0))
                if describe(vals) else "—"
                for vals in ([r.lidar_to_unsafe_ms for r in rs],
                             [r.unsafe_to_hold_ms for r in rs],
                             [r.lidar_to_hold_ms for r in rs])])
        lidar = "Lidar below {:.0f} m".format(TRIP_M)
        out += md_table(["Configuration", lidar + " → unsafe status",
                         "Unsafe status → first hold at PX4",
                         lidar + " → first hold at PX4"], rows)

    out += ["## UAVs without a fault", "",
            "Both UAVs in a configuration without a fault; the UAV without "
            "the task otherwise.", ""]
    rows = []
    for c in order:
        rs = clean[c]
        rows.append([c, rs[0].veto_by if rs else "—",
                     "{}/{}".format(len(rs), len(by_conf[c])),
                     "{}/{}".format(sum(1 for r in rs if r.healthy_holds),
                                    len(rs)),
                     str(sum(r.healthy_holds for r in rs)),
                     "{}/{}".format(sum(1 for r in rs
                                        if r.healthy_unsafe_airborne),
                                    len(rs))])
    out += md_table(["Configuration", "Veto by", "Clean runs",
                     "Runs with gate holds", "Gate holds",
                     "Runs with an unsafe status in flight"], rows)

    out += ["## Runs", ""]
    rows = [[r.configuration, str(r.run), str(r.seed),
             "UAV{}".format(r.uav - 1) if r.uav else "—", cell(r.clean),
             cell(r.impact), cell(r.impact_speed_mps),
             cell(r.closest_wall_m), cell(r.lidar_to_unsafe_ms, 0),
             cell(r.unsafe_to_hold_ms, 0), cell(r.let_through),
             cell(r.held_to_end), str(r.healthy_holds)]
            for r in runs]
    out += md_table(["Configuration", "Run", "Seed", "UAV with the task",
                     "Clean", "Impact", "Impact speed (m/s)", "Closest (m)",
                     "Lidar → unsafe (ms)", "Unsafe → hold (ms)",
                     "Let through", "Held to the end",
                     "Holds, UAVs without a fault"], rows)

    left = [r for r in runs if not r.clean]
    if left or missing:
        out += ["## Runs left out", ""]
        out += ["- {} run {} (seed {}, attempt {} in `{}`): {}".format(
            r.configuration, r.run, r.seed, r.attempt, r.campaign,
            r.problems) for r in left]
        out += ["- " + m for m in missing]
        out.append("")
    return out


def write_csv(path: str, runs: List[FaultRun]) -> None:
    names = [f.name for f in fields(FaultRun)]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in runs:
            w.writerow(["" if getattr(r, n) is None else getattr(r, n)
                        for n in names])


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description="Tables of the faulty-UAV-worker runs of a campaign "
                    "(read-only).")
    ap.add_argument("campaign", help="campaign folder, e.g. "
                                     "bags/campaigns/faults")
    ap.add_argument("--out", default=None,
                    help="output folder (default: results/<campaign>)")
    ap.add_argument("--configurations", default=os.path.join(
        here, "..", "experiments", "configurations.conf"),
        help="configurations.conf, for the variables of each configuration")
    args = ap.parse_args()

    d = os.path.normpath(args.campaign)
    name = os.path.basename(d)
    manifest = os.path.join(d, "manifest.csv")
    if not os.path.isfile(manifest):
        print("no manifest.csv in {}".format(d), file=sys.stderr)
        return 2
    attempts = read_manifest(manifest, d)
    envs = {d: read_env(os.path.join(d, "campaign.env"))}
    conf_vars = configuration_vars(args.configurations)
    present = []
    for a in attempts:
        if a.configuration not in present:
            present.append(a.configuration)
    order = [c for c in conf_vars if c in present and (
        "UAV_FAULT" in conf_vars[c] or "VETO_BY" in conf_vars[c])]
    if not order:
        print("{}: no configuration sets UAV_FAULT or VETO_BY".format(d),
              file=sys.stderr)
        return 1

    print("[faults] {}: {} ...".format(name, ", ".join(order)),
          file=sys.stderr)
    selected, missing = select_runs(attempts, order, envs)
    runs = []
    for r, a in selected:
        v = conf_vars[r.configuration]
        r.veto_by = v.get("VETO_BY", "worker")
        r.fault = v.get("UAV_FAULT", "none")
        if r.clean:
            analyze_faults(a, r)
        runs.append(r)

    text = "\n".join(report(name, runs, order, missing))
    print(text)
    out_dir = args.out or os.path.join("results", name)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "faults.md"), "w") as f:
        f.write(text + "\n")
    write_csv(os.path.join(out_dir, "faults.csv"), runs)
    print("[faults] faults.md and faults.csv written to {}".format(out_dir),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())