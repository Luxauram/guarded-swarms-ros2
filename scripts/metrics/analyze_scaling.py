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
analyze_scaling.py - the tables of the fleet-size runs of a campaign.

Read-only: it reads the manifest and the bags of a campaign recorded by
scripts/experiments/run_campaign.sh, and writes tables and a CSV file.

It covers the configurations of configurations.conf that set N_UAVS: the
whole chain with N_UAVS UAVs and the UGV. Each run uses the attempt that
analyze_campaign.py uses, the first valid attempt whose recording passes its
checks, with one more check: T7 logged at start-up a fleet of N_UAVS UAVs
(logs/gs_tbcspn.log). A run without such an attempt is left out and listed.

For each run:
  - the times of the chain in simulated time, from the token stamps, as
    analyze_campaign.py computes them: first observation -> CandidateTarget
    -> ConfirmedThreat -> supervisor decision -> mission -> first task. The
    end-to-end time, from the first observation to the first task, is also
    given in real time (recorder receive time): what an operator waits;
  - the real-time factor of the recording;
  - the messages of the mission: those the recorder received from the first
    observation to the first task, in three groups:
      chain         the tokens of the coordination layer: /obs_tokens,
                    /interp_tokens, /mission_tokens, /vehicle_tasks and
                    /supervisor_auth;
      T7 input      the local position of every UAV, which the dispatch
                    transition (T7) reads to send the nearest;
      safety layer  safety_status, actuator_cmd_safe and drone/proximity of
                    every vehicle, and the setpoints of every UAV before and
                    after its safety gate.
    The position of the UGV, the intruder ground truth and /clock are
    recorded but not counted, and the topics PX4 publishes that the recorder
    does not take are not counted either.
    Most topics are published on simulated time, but those of the WALL_TIMED
    list come from timers on the real clock (create_wall_timer), at a fixed
    rate per real second. When the simulation runs slower than real time,
    they deliver more messages per simulated second than the system would
    send in real time. The counts are therefore given twice: as recorded,
    and at real-time rates, where a wall-timed topic counts its messages
    times the real-time factor of the window. Both are also given per second
    of simulated time;
  - the interceptor, the UAV of the first UAV task: from the task to its
    first horizontal speed above MOVING_MPS, and its peak horizontal speed
    after the task. Both come from the velocity in the local position of
    PX4, which is in simulated time;
  - the vehicles never safe: those whose safety_status never reported safe
    in the recording, so their Safety Board vetoed every command.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/analyze_scaling.py bags/campaigns/<campaign> \\
        [--out results/<campaign>]

Output, in --out (default results/<campaign>):
    scaling.md    the tables, also printed
    scaling.csv   one line per run

@author Luca D'Aurizio
"""

import argparse
import csv
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, fields
from typing import Dict, List, Optional, Tuple

from analyze_campaign import (ANSI_CODE, T3_LOG, Attempt, RunResult,
                              analyze_run, bag_of, configuration_order,
                              configuration_vars, md_table, rate_cell,
                              read_env, read_manifest, time_cell)
from audit_timing import ClockMap, describe, storage_id

# =============================================================================
# The scenario, as in config/coastal_fleet.yaml of guarded_swarms_bringup
# =============================================================================
UGV_INSTANCE = 2               # the UGV; every other PX4 instance is a UAV
MOVING_MPS = 1.0               # a UAV faster than this has started to move
STATUS_SAFE = 0.5              # safety_status at or above this: safe

CHAIN = ("/obs_tokens", "/interp_tokens", "/mission_tokens",
         "/vehicle_tasks", "/supervisor_auth")
POSITION = "fmu/out/vehicle_local_position_v1"
STATUS = "safety_status"
SAFETY = (STATUS, "actuator_cmd_safe", "drone/proximity",
          "trajectory_setpoint_proposed", "fmu/in/trajectory_setpoint")
GROUPS = ("chain", "t7", "safety")
# Topics published on the real clock: the setpoints of uav_worker_node and
# the commands of ugv_worker_node come from a create_wall_timer, the safety
# gate forwards each setpoint as it comes, and safety_board_node publishes its
# status from a create_wall_timer and its verdict in reply to each command.
WALL_TIMED = ("safety_status", "actuator_cmd_safe",
              "trajectory_setpoint_proposed", "fmu/in/trajectory_setpoint")
# The fleet T7 logs at start-up, from tbcspn.launch.py.
FLEET_LINE = re.compile(r"T7 fleet:\s*([0-9]+) UAVs")


def split_topic(topic: str) -> Tuple[int, str]:
    """PX4 instance and namespace-relative name of a topic: /px4_<i>/... is
    instance i, any other topic instance 0 (the root namespace)."""
    parts = topic.split("/")
    if len(parts) > 2 and re.fullmatch(r"px4_[0-9]+", parts[1]):
        return int(parts[1][4:]), "/".join(parts[2:])
    return 0, topic.lstrip("/")


def vehicle_name(instance: int) -> str:
    """UAV0, UAV1, UGV, then UAV2 for instance 3 and so on."""
    if instance == UGV_INSTANCE:
        return "UGV"
    return "UAV{}".format(instance if instance < UGV_INSTANCE
                          else instance - 1)


def group_of(topic: str) -> Optional[str]:
    """The group a topic counts in (see the module docstring), or None."""
    if topic in CHAIN:
        return "chain"
    instance, name = split_topic(topic)
    if name == POSITION:
        return None if instance == UGV_INSTANCE else "t7"
    if name in SAFETY:
        return "safety"
    return None


# =============================================================================
# Bag reading
# =============================================================================
def read_bag(bag_dir: str) -> Tuple[Dict[str, list], Dict[str, List[float]]]:
    """Read a bag: the messages needed in full (/clock, the tasks, the local
    positions and the safety status of every vehicle), and the receive time
    of every message of the counted topics.

    @return ({topic: [(rx_s, msg), ...]}, {topic: [rx_s, ...]}), rx_s
            relative to the first message of the bag.
    """
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as e:
        sys.exit("Cannot import the ROS 2 Python modules ({}).\n"
                 "Run `source /opt/ros/humble/setup.bash && "
                 "source install/setup.bash` first.".format(e))
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=storage_id(bag_dir)),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                    output_serialization_format="cdr"))
    full: Dict[str, list] = {}
    times: Dict[str, List[float]] = {}
    classes = {}
    for topic in reader.get_all_topics_and_types():
        name = split_topic(topic.name)[1]
        if topic.name in ("/clock", "/vehicle_tasks") or \
                name in (POSITION, STATUS):
            try:
                classes[topic.name] = get_message(topic.type)
            except (AttributeError, ModuleNotFoundError, ValueError):
                pass
            full[topic.name] = []
        if group_of(topic.name):
            times[topic.name] = []
    base_ns = None
    while reader.has_next():
        topic, data, recv_ns = reader.read_next()
        if base_ns is None:
            base_ns = recv_ns
        rx = (recv_ns - base_ns) * 1e-9
        if topic in times:
            times[topic].append(rx)
        if topic in classes:
            full[topic].append((rx, deserialize_message(data,
                                                        classes[topic])))
    return full, times


# =============================================================================
# One run
# =============================================================================
@dataclass
class ScalingRun:
    """One run. Times in seconds."""
    configuration: str = ""
    n_uavs: int = 0
    run: int = 0
    seed: int = 0
    attempt: int = 0
    campaign: str = ""
    clean: bool = False
    problems: str = ""
    t7_fleet: Optional[int] = None       # as T7 logged it
    rtf: Optional[float] = None
    mission: Optional[bool] = None
    obs_to_candidate: Optional[float] = None
    candidate_to_threat: Optional[float] = None
    threat_to_decision: Optional[float] = None
    decision_to_mission: Optional[float] = None
    mission_to_task: Optional[float] = None
    obs_to_task: Optional[float] = None       # simulated time, token stamps
    obs_to_task_real: Optional[float] = None  # real time, receive times
    window_sim: Optional[float] = None        # the counting window, sim s
    msgs_chain: Optional[int] = None       # as recorded
    msgs_t7: Optional[int] = None
    msgs_safety: Optional[int] = None
    msgs_total: Optional[int] = None
    rtf_window: Optional[float] = None     # real-time factor of the window
    rt_chain: Optional[float] = None       # at real-time rates
    rt_t7: Optional[float] = None
    rt_safety: Optional[float] = None
    rt_total: Optional[float] = None
    interceptor: str = ""
    task_to_moving: Optional[float] = None
    peak_speed_mps: Optional[float] = None
    never_safe: str = ""


def t7_fleet_of(log_path: str) -> Optional[int]:
    """The number of UAVs T7 logged at start-up, or None if not found."""
    try:
        with open(log_path, errors="replace") as f:
            for line in f:
                m = FLEET_LINE.search(ANSI_CODE.sub("", line))
                if m:
                    return int(m.group(1))
    except OSError:
        pass
    return None


def plus(*values: Optional[float]) -> Optional[float]:
    return None if any(v is None for v in values) else sum(values)


def analyze_scaling(a: Attempt, res: RunResult, r: ScalingRun) -> None:
    """Fill r from the audit res and the bag of attempt a."""
    au = res.audit
    r.rtf = au.rtf
    r.mission = au.missions > 0
    r.obs_to_candidate = au.obs_to_candidate
    r.candidate_to_threat = au.candidate_to_threat
    r.threat_to_decision = res.threat_to_decision
    r.decision_to_mission = res.decision_to_mission
    r.mission_to_task = res.mission_to_task
    r.obs_to_task = plus(au.obs_to_mission, res.mission_to_task)

    full, times = read_bag(bag_of(a))

    # --- the vehicles never safe --------------------------------------------
    never = []
    for topic, msgs in full.items():
        instance, name = split_topic(topic)
        if name == STATUS and msgs and not any(m.data >= STATUS_SAFE
                                               for _, m in msgs):
            never.append((instance, vehicle_name(instance)))
    r.never_safe = " ".join(v for _, v in sorted(never))

    clk = ClockMap(full.get("/clock", []))
    obs = times.get("/obs_tokens", [])
    uav_tasks = [(rx, m) for rx, m in full.get("/vehicle_tasks", [])
                 if m.assigned_system != UGV_INSTANCE + 1]
    if not clk.ok() or not obs or not uav_tasks:
        return
    t0 = obs[0]
    t_task, task = uav_tasks[0]
    r.obs_to_task_real = t_task - t0
    r.window_sim = clk(t_task) - clk(t0)
    if r.obs_to_task_real > 0:
        r.rtf_window = r.window_sim / r.obs_to_task_real

    # --- the messages of the mission --------------------------------------
    # As recorded, and at real-time rates: a wall-timed topic sends its
    # messages per real second, so in real time it would send its recorded
    # count times the real-time factor of the window.
    counts = Counter()
    at_rt: Counter = Counter()
    for topic, rxs in times.items():
        n = sum(1 for rx in rxs if t0 <= rx <= t_task)
        counts[group_of(topic)] += n
        wall = split_topic(topic)[1] in WALL_TIMED
        if wall and r.rtf_window is not None:
            at_rt[group_of(topic)] += n * r.rtf_window
        elif not wall:
            at_rt[group_of(topic)] += n
    r.msgs_chain, r.msgs_t7, r.msgs_safety = (counts[g] for g in GROUPS)
    r.msgs_total = sum(counts[g] for g in GROUPS)
    if r.rtf_window is not None:
        r.rt_chain, r.rt_t7, r.rt_safety = (at_rt[g] for g in GROUPS)
        r.rt_total = sum(at_rt[g] for g in GROUPS)

    # --- the interceptor ----------------------------------------------------
    instance = task.assigned_system - 1
    r.interceptor = vehicle_name(instance)
    topic = ("/" if instance == 0 else "/px4_{}/".format(instance)) + POSITION
    ts = clk(t_task)
    after = [(clk(rx), math.hypot(m.vx, m.vy))
             for rx, m in full.get(topic, [])
             if clk.inside(rx) and clk(rx) >= ts]
    if after:
        r.peak_speed_mps = max(v for _, v in after)
        moving = [t for t, v in after if v > MOVING_MPS]
        if moving:
            r.task_to_moving = moving[0] - ts


# =============================================================================
# Campaign
# =============================================================================
def select_runs(attempts: List[Attempt], order: List[str],
                n_uavs: Dict[str, int], envs: Dict[str, Dict[str, str]]
                ) -> Tuple[List[Tuple[ScalingRun, Attempt, RunResult]],
                           List[str]]:
    """The attempt of each run, as analyze_campaign.py chooses it, with the
    check of the fleet T7 logged."""
    groups: Dict[Tuple[str, int], List[Attempt]] = {}
    for a in attempts:
        if a.configuration in order:
            groups.setdefault((a.configuration, a.seed), []).append(a)
    runs: List[Tuple[ScalingRun, Attempt, RunResult]] = []
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
            fleet = t7_fleet_of(os.path.join(os.path.dirname(bag_of(a)),
                                             "logs", T3_LOG))
            if fleet is None:
                res.problems.append("no T7 fleet in logs/{}: the N_UAVS of "
                                    "the run cannot be checked".format(T3_LOG))
            elif fleet != n_uavs[c]:
                res.problems.append("T7 ran with {} UAVs, the configuration "
                                    "sets {}".format(fleet, n_uavs[c]))
            res.clean = not res.problems
            used = (a, res, fleet)
            if res.clean:
                break
        a, res, fleet = used
        runs.append((ScalingRun(configuration=c, n_uavs=n_uavs[c],
                                run=tries[0].run, seed=seed,
                                attempt=a.attempt, campaign=a.campaign,
                                clean=res.clean, t7_fleet=fleet,
                                problems="; ".join(res.problems)), a, res))
    return runs, missing


# =============================================================================
# Report
# =============================================================================
def mean_sd(values: list, prec: int = 2) -> str:
    """mean ± sample sd, or a dash."""
    s = describe(values)
    if s is None:
        return "—"
    return "{:.{p}f} ± {:.{p}f}".format(s["mean"], s["sd"], p=prec)


def mean_min(values: list) -> str:
    """mean (min), or a dash."""
    s = describe(values)
    if s is None:
        return "—"
    return "{:.3f} ({:.3f})".format(s["mean"], s["min"])


def per_second(runs: List[ScalingRun], attr: str) -> list:
    return [getattr(r, attr) / r.window_sim for r in runs
            if getattr(r, attr) is not None and r.window_sim]


def cell(v, prec: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return "{:.{p}f}".format(v, p=prec)
    return str(v)


def report(name: str, runs: List[ScalingRun], order: List[str],
           missing: List[str]) -> List[str]:
    out = ["# Fleet size: {}".format(name), "",
           "The whole chain with N UAVs and the UGV. All times are in "
           "simulated time unless marked real time.", ""]
    by_conf = {c: [r for r in runs if r.configuration == c] for c in order}
    clean = {c: [r for r in rs if r.clean] for c, rs in by_conf.items()}

    out += ["## Overview", ""]
    rows = []
    for c in order:
        rs = clean[c]
        took = Counter(r.interceptor for r in rs if r.interceptor)
        rows.append([
            c, str(by_conf[c][0].n_uavs) if by_conf[c] else "—",
            "{}/{}".format(len(rs), len(by_conf[c])),
            mean_min([r.rtf for r in rs]),
            rate_cell(sum(1 for r in rs if r.mission), len(rs)),
            time_cell([r.obs_to_task for r in rs]),
            time_cell([r.obs_to_task_real for r in rs]),
            ", ".join("{} {}".format(v, k) for k, v in sorted(took.items()))
            or "—"])
    out += md_table(["Configuration", "UAVs", "Clean runs",
                     "Real-time factor, mean (min)", "Mission [95% CI, %]",
                     "First obs → first task (s)",
                     "First obs → first task, real time (s)",
                     "Interceptor"], rows)

    out += ["## Chain", ""]
    rows = [[c] + [time_cell([getattr(r, k) for r in clean[c]]) for k in (
        "obs_to_candidate", "candidate_to_threat", "threat_to_decision",
        "decision_to_mission", "mission_to_task")] for c in order]
    out += md_table(["Configuration", "First obs → CandidateTarget",
                     "CandidateTarget → ConfirmedThreat",
                     "ConfirmedThreat → decision", "decision → mission",
                     "mission → first task"], rows)

    out += ["## Messages of a mission", "",
            "Messages from the first observation to the first task. Chain: "
            "the tokens of the coordination layer. T7 input: the local "
            "position of every UAV. Safety layer: status, verdict and lidar "
            "range of every vehicle, and the setpoints of every UAV before "
            "and after its safety gate. At real-time rates: the topics "
            "published on the real clock ({}) count their recorded messages "
            "times the real-time factor of the window, as the system would "
            "send them in real time; the other topics are on simulated "
            "time. Per s: per second of simulated time.".format(
                ", ".join("`{}`".format(w) for w in WALL_TIMED)), ""]
    keys = ("rt_chain", "rt_t7", "rt_safety", "rt_total")
    rows = []
    for c in order:
        rs = clean[c]
        rows.append([c] + [mean_sd([getattr(r, k) for r in rs], 0)
                           for k in keys]
                    + [mean_sd(per_second(rs, k), 1) for k in keys])
    out += md_table(["Configuration", "Chain", "T7 input", "Safety layer",
                     "Total", "Chain per s", "T7 input per s",
                     "Safety layer per s", "Total per s"], rows)
    out += ["As recorded:", ""]
    rows = []
    for c in order:
        rs = clean[c]
        rows.append([c, mean_sd([r.rtf_window for r in rs], 3)]
                    + [mean_sd([float(getattr(r, k)) for r in rs
                                if getattr(r, k) is not None], 0)
                       for k in ("msgs_safety", "msgs_total")]
                    + [mean_sd(per_second(rs, k), 1)
                       for k in ("msgs_safety", "msgs_total")])
    out += md_table(["Configuration", "Real-time factor of the window",
                     "Safety layer", "Total", "Safety layer per s",
                     "Total per s"], rows)

    out += ["## Interceptor and vehicles", "",
            "The interceptor is the UAV of the first UAV task. A vehicle "
            "never safe is one whose Safety Board never reported safe in the "
            "recording, so it vetoed every command of the vehicle.", ""]
    rows = []
    for c in order:
        rs = clean[c]
        rows.append([c, mean_sd([r.task_to_moving for r in rs]),
                     mean_sd([r.peak_speed_mps for r in rs]),
                     "{}/{}".format(sum(1 for r in rs if r.never_safe),
                                    len(rs))])
    out += md_table(["Configuration",
                     "Task → interceptor moving (s)",
                     "Interceptor peak speed (m/s)",
                     "Runs with a vehicle never safe"], rows)

    out += ["## Runs", ""]
    rows = [[r.configuration, str(r.run), str(r.seed), str(r.attempt),
             cell(r.clean), cell(r.t7_fleet), cell(r.rtf, 3),
             cell(r.mission), cell(r.obs_to_task), cell(r.obs_to_task_real),
             cell(r.msgs_chain), cell(r.msgs_t7), cell(r.msgs_safety),
             cell(r.rt_safety, 0), r.interceptor or "—", cell(r.task_to_moving),
             cell(r.peak_speed_mps), r.never_safe or "—"] for r in runs]
    out += md_table(["Configuration", "Run", "Seed", "Attempt", "Clean",
                     "T7 fleet", "RTF", "Mission", "Obs → task (s)",
                     "Obs → task, real (s)", "Chain msgs", "T7 input msgs",
                     "Safety msgs", "Safety msgs, real-time rates",
                     "Interceptor", "Task → moving (s)",
                     "Peak speed (m/s)", "Never safe"], rows)

    left = [r for r in runs if not r.clean]
    if left or missing:
        out += ["## Runs left out", ""]
        out += ["- {} run {} (seed {}, attempt {} in `{}`): {}".format(
            r.configuration, r.run, r.seed, r.attempt, r.campaign,
            r.problems) for r in left]
        out += ["- " + m for m in missing]
        out.append("")
    return out


def write_csv(path: str, runs: List[ScalingRun]) -> None:
    names = [f.name for f in fields(ScalingRun)]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in runs:
            w.writerow(["" if getattr(r, n) is None else getattr(r, n)
                        for n in names])


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description="Tables of the fleet-size runs of a campaign "
                    "(read-only).")
    ap.add_argument("campaign", help="campaign folder, e.g. "
                                     "bags/campaigns/scaling")
    ap.add_argument("--out", default=None,
                    help="output folder (default: results/<campaign>)")
    ap.add_argument("--configurations", default=os.path.join(
        here, "..", "experiments", "configurations.conf"),
        help="configurations.conf, for the N_UAVS of each configuration")
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
    present = {a.configuration for a in attempts}
    order = [c for c in configuration_order(args.configurations)
             if c in present and "N_UAVS" in conf_vars.get(c, {})]
    if not order:
        print("{}: no configuration sets N_UAVS".format(d), file=sys.stderr)
        return 1
    n_uavs = {c: int(conf_vars[c]["N_UAVS"]) for c in order}

    print("[scaling] {}: {} ...".format(name, ", ".join(order)),
          file=sys.stderr)
    selected, missing = select_runs(attempts, order, n_uavs, envs)
    runs = []
    for r, a, res in selected:
        if r.clean:
            analyze_scaling(a, res, r)
        runs.append(r)

    text = "\n".join(report(name, runs, order, missing))
    print(text)
    out_dir = args.out or os.path.join("results", name)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scaling.md"), "w") as f:
        f.write(text + "\n")
    write_csv(os.path.join(out_dir, "scaling.csv"), runs)
    print("[scaling] scaling.md and scaling.csv written to {}".format(
        out_dir), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())