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
audit_timing.py - timing audit of the nominal-chain bags.

Read-only analysis of data that is already recorded; no new runs.

A run is "clean" when the intruder ground truth comes from a single source.
Two consecutive ground-truth samples farther apart than GT_JUMP_M mean that a
second intruder process (an orphan left over from a previous run) was
publishing on the same topic, so the sensors saw two targets. Such runs are
listed but kept out of the clean summaries.

[A] Chain latencies from the token stamps, over all complete runs and over
    clean complete runs.

[B] Authorisation path. Every token carries a simulated-time stamp `t`, except
    the SupervisorAuth published by the test harness, whose stamp is left at
    zero. A CONSTANT offset (the median of t - receive time over all
    ObsTokens and InterpTokens) would place it on the sim axis with a bias:
    those tokens carry the observation instant, not their publication
    instant, and a constant offset ignores the drift of the real-time factor.
    The report shows that projection for comparison; everywhere else a receive
    time is mapped to sim time by interpolating the /clock messages recorded
    in the same bag.

    The harness publishes the authorisation from a short-lived command-line
    process. The recorder and T6 each receive it only once their own
    discovery of that process completes, so either can be the first to get
    it. The publication instant is therefore estimated as the earliest of
    the two receptions available in the bag: the recorder's (/clock-mapped)
    and T6's, which equals the mission stamp because T6 releases the mission
    in the same callback in which a valid threat meets the authorisation.

[C] First observation -> CandidateTarget. Each modality's first observation
    and the candidate are placed relative to the instant the intruder starts
    moving (/intruder/active), together with the intruder position at each of
    those instants, to separate geometry from processing.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/audit_timing.py bags/coastal-* \
        --csv results/audit_timing.csv

@author Luca D'Aurizio
"""

import argparse
import bisect
import csv
import math
import os
import statistics
import sys
from dataclasses import dataclass, fields
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import yaml

# Message types this audit needs, matched by type rather than by topic name.
TYPES = {
    "obs": "guarded_swarms_msgs/msg/ObsToken",
    "interp": "guarded_swarms_msgs/msg/InterpToken",
    "mission": "guarded_swarms_msgs/msg/MissionToken",
    "task": "guarded_swarms_msgs/msg/VehicleTask",
    "auth": "guarded_swarms_msgs/msg/SupervisorAuth",
    "clock": "rosgraph_msgs/msg/Clock",
}
GT_TYPE = "geometry_msgs/msg/PoseStamped"   # topic name contains "intruder"
BOOL_TYPE = "std_msgs/msg/Bool"             # /intruder/active
KINDS = list(TYPES) + ["gt", "active"]

SOURCES = ("radar", "rf", "acoustic", "eo")
AUTHORISE = ("authorise", "authorize")
GT_JUMP_M = 5.0   # consecutive ground-truth samples farther apart = 2 sources


# =============================================================================
# Bag reading
# =============================================================================
def stamp_s(stamp) -> float:
    """builtin_interfaces/Time -> seconds."""
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def storage_id(bag_dir: str) -> str:
    """Storage plugin of a bag, from its metadata.yaml (sqlite3 by default)."""
    try:
        with open(os.path.join(bag_dir, "metadata.yaml")) as f:
            info = yaml.safe_load(f)["rosbag2_bagfile_information"]
        return info.get("storage_identifier", "sqlite3")
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return "sqlite3"


def read_bag(bag_dir: str) -> Dict[str, list]:
    """Read the topics this audit needs.

    @param bag_dir  Bag directory (the one holding metadata.yaml).
    @return         {kind: [(recv_s, msg), ...]} where recv_s is the receive
                    time in seconds relative to the first message read.
    """
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as e:
        sys.exit("Cannot import the ROS 2 Python modules ({}).\n"
                 "Run `source /opt/ros/humble/setup.bash && "
                 "source install/setup.bash` first.".format(e))

    out: Dict[str, list] = {k: [] for k in KINDS}
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=storage_id(bag_dir)),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                    output_serialization_format="cdr"),
    )

    kind_of: Dict[str, str] = {}
    classes = {}
    for topic in reader.get_all_topics_and_types():
        kind = next((k for k, ty in TYPES.items() if ty == topic.type), None)
        if topic.type == GT_TYPE and "intruder" in topic.name:
            kind = "gt"
        if (topic.type == BOOL_TYPE and "intruder" in topic.name
                and "active" in topic.name):
            kind = "active"
        if kind is None:
            continue
        try:
            classes[topic.name] = get_message(topic.type)
        except (AttributeError, ModuleNotFoundError, ValueError):
            continue
        kind_of[topic.name] = kind
    if not kind_of:
        return out

    reader.set_filter(rosbag2_py.StorageFilter(topics=list(kind_of)))
    base_ns = None
    while reader.has_next():
        topic, data, recv_ns = reader.read_next()
        if topic not in kind_of:
            continue
        if base_ns is None:
            base_ns = recv_ns
        try:
            msg = deserialize_message(data, classes[topic])
        except Exception:  # a single corrupt message must not stop the audit
            continue
        out[kind_of[topic]].append(((recv_ns - base_ns) * 1e-9, msg))
    return out


# =============================================================================
# Time-axis helpers
# =============================================================================
class ClockMap:
    """Receive time -> sim time, by interpolating the recorded /clock."""

    def __init__(self, clock_msgs: list):
        xs: List[float] = []
        ys: List[float] = []
        for recv, msg in sorted(clock_msgs, key=lambda p: p[0]):
            sim = stamp_s(msg.clock)
            if sim <= 0.0 or (xs and recv <= xs[-1]):
                continue
            xs.append(recv)
            ys.append(sim)
        self.x = np.array(xs)
        self.y = np.array(ys)

    def ok(self) -> bool:
        return len(self.x) >= 2

    def inside(self, recv: float) -> bool:
        return self.ok() and self.x[0] <= recv <= self.x[-1]

    def __call__(self, recv: float) -> float:
        return float(np.interp(recv, self.x, self.y))

    def rtf(self) -> Optional[float]:
        """Real-time factor over the whole recording."""
        if not self.ok() or self.x[-1] <= self.x[0]:
            return None
        return float((self.y[-1] - self.y[0]) / (self.x[-1] - self.x[0]))


class GroundTruth:
    """Intruder position against sim time.

    The sample time is the /clock-mapped receive time: the ground-truth stamp
    is not used, because it is not guaranteed to be on the sim clock.
    """

    def __init__(self, gt_msgs: list, clk: ClockMap):
        pts: List[Tuple[float, float, float, float]] = []
        for recv, msg in gt_msgs:
            if clk.ok():
                t = clk(recv)
            else:
                t = stamp_s(msg.header.stamp)
                if t <= 0.0:
                    continue
            p = msg.pose.position
            pts.append((t, p.x, p.y, p.z))
        pts.sort()
        self.t = [p[0] for p in pts]
        self.p = pts

    def y(self, t: Optional[float]) -> Optional[float]:
        """Intruder y (world ENU) at the sample nearest to sim time t."""
        if t is None or not self.t:
            return None
        i = bisect.bisect_left(self.t, t)
        cands = [j for j in (i - 1, i) if 0 <= j < len(self.t)]
        j = min(cands, key=lambda k: abs(self.t[k] - t))
        return self.p[j][2]

    def rate_hz(self) -> Optional[float]:
        if len(self.t) < 2 or self.t[-1] <= self.t[0]:
            return None
        return (len(self.t) - 1) / (self.t[-1] - self.t[0])

    def jumps(self) -> int:
        """Consecutive samples farther apart than GT_JUMP_M (2 publishers?)."""
        n = 0
        for a, b in zip(self.p, self.p[1:]):
            if math.dist(a[1:], b[1:]) > GT_JUMP_M:
                n += 1
        return n


def earliest(msgs: list, pred: Callable = lambda m: True):
    """Earliest message by its own stamp `t`.

    @return (t, recv_s, msg) or None. Messages with an unset stamp are skipped.
    """
    best = None
    for recv, msg in msgs:
        if not pred(msg):
            continue
        t = stamp_s(msg.t)
        if t <= 0.0:
            continue
        if best is None or t < best[0]:
            best = (t, recv, msg)
    return best


def diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """b - a, or None if either is missing."""
    return None if a is None or b is None else b - a


# =============================================================================
# Per-run audit
# =============================================================================
@dataclass
class RunAudit:
    """Every instant and interval of one run, in sim seconds."""
    bag: str = ""
    target_id: str = ""
    complete: bool = False            # a mission was formed for the target
    clean: bool = True                # one intruder ground-truth source only
    # --- instants ---
    t_motion_start: Optional[float] = None
    t_first_obs: Optional[float] = None
    first_obs_source: str = ""
    t_first_radar: Optional[float] = None
    t_first_rf: Optional[float] = None
    t_first_acoustic: Optional[float] = None
    t_first_eo: Optional[float] = None
    t_first_possible_uav: Optional[float] = None
    t_first_drone_link: Optional[float] = None
    t_first_aerial_object: Optional[float] = None
    t_first_candidate: Optional[float] = None
    t_first_confirmed: Optional[float] = None
    t_last_confirmed: Optional[float] = None
    n_confirmed: int = 0
    n_auth: int = 0
    t_auth_offset: Optional[float] = None    # constant-offset projection
    t_auth_clock: Optional[float] = None     # recorder reception, /clock
    t_auth_publish: Optional[float] = None   # earliest reception (estimate)
    auth_stamp_set: bool = False
    n_missions: int = 0
    t_first_mission: Optional[float] = None  # stamp set by T6
    t_mission_rx: Optional[float] = None     # received by the recorder
    t_consumed_threat: Optional[float] = None
    t_first_task: Optional[float] = None
    # --- [A] chain latencies ---
    end_to_end: Optional[float] = None
    obs_to_candidate: Optional[float] = None
    candidate_to_confirmed: Optional[float] = None
    confirmed_to_mission: Optional[float] = None
    mission_to_task: Optional[float] = None
    # --- [B] authorisation path ---
    confirmed_to_auth_offset: Optional[float] = None
    confirmed_to_auth_clock: Optional[float] = None
    confirmed_to_publish: Optional[float] = None
    publish_to_mission: Optional[float] = None
    mission_stamp_lag: Optional[float] = None
    consumed_threat_minus_publish: Optional[float] = None
    gap_last_threat_before_publish: Optional[float] = None
    threat_alive_at_publish: Optional[bool] = None
    clock_residual: Optional[float] = None
    rtf_run: Optional[float] = None
    # --- [C] geometry ---
    motion_to_first_acoustic: Optional[float] = None
    motion_to_first_rf: Optional[float] = None
    motion_to_first_radar: Optional[float] = None
    motion_to_candidate: Optional[float] = None
    first_obs_to_rf: Optional[float] = None
    rf_to_drone_link: Optional[float] = None
    evidence_to_candidate: Optional[float] = None
    last_required_evidence: str = ""
    y_first_acoustic: Optional[float] = None
    y_first_rf: Optional[float] = None
    y_first_radar: Optional[float] = None
    y_candidate: Optional[float] = None
    gt_rate_hz: Optional[float] = None
    gt_jumps: Optional[int] = None
    notes: str = ""


def pick_target(obs: list) -> Optional[str]:
    """The target_id with the most observations (one intruder per run)."""
    counts: Dict[str, int] = {}
    for _, m in obs:
        if m.target_id:
            counts[m.target_id] = counts.get(m.target_id, 0) + 1
    return max(counts, key=counts.get) if counts else None


def audit(data: Dict[str, list], name: str) -> RunAudit:
    """Compute the audit of one run from its read_bag() output."""
    r = RunAudit(bag=name)
    notes: List[str] = []
    clk = ClockMap(data["clock"])
    if not clk.ok():
        notes.append("no /clock in bag: /clock figures unavailable")

    target = pick_target(data["obs"])
    if target is None:
        r.notes = "no observations with a target_id"
        return r
    r.target_id = target
    obs = [(rv, m) for rv, m in data["obs"] if m.target_id == target]
    interp = [(rv, m) for rv, m in data["interp"] if m.target_id == target]

    # --- ground truth: one source or more? ------------------------------------
    gt = GroundTruth(data["gt"], clk)
    r.gt_rate_hz = gt.rate_hz()
    r.gt_jumps = gt.jumps() if gt.t else None
    if r.gt_jumps:
        r.clean = False
        notes.append("intruder ground truth from more than one source "
                     "({} jumps > {:.0f} m): excluded from the clean "
                     "summaries".format(r.gt_jumps, GT_JUMP_M))
    if not data["gt"]:
        notes.append("no intruder ground truth in bag")

    # --- instants -------------------------------------------------------------
    active = [rv for rv, m in data["active"] if bool(m.data)]
    if active and clk.ok():
        r.t_motion_start = clk(min(active))
    else:
        notes.append("no /intruder/active=true in bag")

    first = earliest(obs)
    if first:
        r.t_first_obs, r.first_obs_source = first[0], first[2].source
    for src in SOURCES:
        e = earliest(obs, lambda m, s=src: m.source == s)
        setattr(r, "t_first_" + src, e[0] if e else None)

    labels = {
        "t_first_possible_uav": "PossibleUAV",
        "t_first_drone_link": "LikelyDroneLink",
        "t_first_aerial_object": "ConfirmedAerialObject",
        "t_first_candidate": "CandidateTarget",
    }
    for attr, label in labels.items():
        e = earliest(interp, lambda m, lb=label: m.label == lb)
        setattr(r, attr, e[0] if e else None)

    # Every ConfirmedThreat of the target, ordered by stamp: (t, recv, msg).
    cts = sorted(((stamp_s(m.t), rv, m) for rv, m in interp
                  if m.label == "ConfirmedThreat" and stamp_s(m.t) > 0.0),
                 key=lambda c: c[0])
    r.n_confirmed = len(cts)
    if cts:
        r.t_first_confirmed, r.t_last_confirmed = cts[0][0], cts[-1][0]

    missions = [(rv, m) for rv, m in data["mission"] if m.target_id == target]
    r.n_missions = len(missions)
    mission = earliest(missions)
    if mission:
        r.complete = True
        r.t_first_mission = mission[0]
        if clk.ok():
            r.t_mission_rx = clk(mission[1])
        # The consumed threat: the last justification entry that is the id of
        # a ConfirmedThreat recorded in this bag.
        ct_t_by_id = {c[2].id: c[0] for c in cts}
        for jid in reversed(list(mission[2].justification)):
            if jid in ct_t_by_id:
                r.t_consumed_threat = ct_t_by_id[jid]
                break
    task = earliest([(rv, m) for rv, m in data["task"]
                     if m.target_id == target])
    r.t_first_task = task[0] if task else None

    # --- authorisation ------------------------------------------------------------
    auths = [(rv, m) for rv, m in data["auth"]
             if m.target_id == target and m.decision in AUTHORISE]
    r.n_auth = len(auths)
    if auths:
        r_auth, m_auth = min(auths, key=lambda p: p[0])
        r.auth_stamp_set = stamp_s(m_auth.t) > 0.0
        # Constant-offset projection, for comparison: the median of
        # (t - recv) over ALL ObsTokens and InterpTokens of the bag.
        offsets = [stamp_s(m.t) - rv for rv, m in data["obs"] + data["interp"]
                   if stamp_s(m.t) > 0.0]
        if offsets:
            r.t_auth_offset = r_auth + statistics.median(offsets)
        if clk.ok():
            r.t_auth_clock = clk(r_auth)
            if not clk.inside(r_auth):
                notes.append("auth outside the /clock range (extrapolated)")
    else:
        notes.append("no authorise decision for the target in the bag")
    # Publication estimate: the earliest reception of the authorisation, by
    # the recorder or by T6 (= the mission stamp).
    received = [t for t in (r.t_auth_clock, r.t_first_mission) if t is not None]
    if received and (auths or mission):
        r.t_auth_publish = min(received)

    # --- [A] chain latencies ----------------------------------------------------
    r.end_to_end = diff(r.t_first_obs, r.t_first_mission)
    r.obs_to_candidate = diff(r.t_first_obs, r.t_first_candidate)
    r.candidate_to_confirmed = diff(r.t_first_candidate, r.t_first_confirmed)
    r.confirmed_to_mission = diff(r.t_first_confirmed, r.t_first_mission)
    r.mission_to_task = diff(r.t_first_mission, r.t_first_task)

    # --- [B] authorisation path -----------------------------------------------
    r.confirmed_to_auth_offset = diff(r.t_first_confirmed, r.t_auth_offset)
    r.confirmed_to_auth_clock = diff(r.t_first_confirmed, r.t_auth_clock)
    r.confirmed_to_publish = diff(r.t_first_confirmed, r.t_auth_publish)
    r.publish_to_mission = diff(r.t_auth_publish, r.t_first_mission)
    r.mission_stamp_lag = diff(r.t_first_mission, r.t_mission_rx)
    r.consumed_threat_minus_publish = diff(r.t_auth_publish,
                                           r.t_consumed_threat)
    if r.t_auth_publish is not None and cts:
        before = [c for c in cts if c[0] <= r.t_auth_publish]
        r.threat_alive_at_publish = any(
            c[0] + float(c[2].ttl_s) >= r.t_auth_publish for c in before)
        if before:
            r.gap_last_threat_before_publish = r.t_auth_publish - before[-1][0]
    if auths and not mission and r.threat_alive_at_publish:
        notes.append("authorisation recorded while a threat was still valid, "
                     "but no mission: T6 did not act on that authorisation")
    if clk.ok():
        # How well /clock places tokens stamped by a node at publication:
        # median of (mapped receive - own stamp) over every ConfirmedThreat.
        res = [clk(c[1]) - c[0] for c in cts if clk.inside(c[1])]
        r.clock_residual = statistics.median(res) if res else None
        r.rtf_run = clk.rtf()

    # --- [C] geometry -------------------------------------------------------------
    m0 = r.t_motion_start
    r.motion_to_first_acoustic = diff(m0, r.t_first_acoustic)
    r.motion_to_first_rf = diff(m0, r.t_first_rf)
    r.motion_to_first_radar = diff(m0, r.t_first_radar)
    r.motion_to_candidate = diff(m0, r.t_first_candidate)
    r.first_obs_to_rf = diff(r.t_first_obs, r.t_first_rf)
    r.rf_to_drone_link = diff(r.t_first_rf, r.t_first_drone_link)
    if r.t_first_possible_uav is not None and r.t_first_drone_link is not None:
        last = max(r.t_first_possible_uav, r.t_first_drone_link)
        r.evidence_to_candidate = diff(last, r.t_first_candidate)
        r.last_required_evidence = (
            "radar" if r.t_first_possible_uav >= r.t_first_drone_link else "rf")
    r.y_first_acoustic = gt.y(r.t_first_acoustic)
    r.y_first_rf = gt.y(r.t_first_rf)
    r.y_first_radar = gt.y(r.t_first_radar)
    r.y_candidate = gt.y(r.t_first_candidate)

    r.notes = "; ".join(notes)
    return r


# =============================================================================
# Report
# =============================================================================
def fmt(v, width: int = 8, prec: int = 2) -> str:
    """Right-aligned number, int, bool or n/a."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a".rjust(width)
    if isinstance(v, bool):
        return ("yes" if v else "no").rjust(width)
    if isinstance(v, int):
        return str(v).rjust(width)
    return f"{v:{width}.{prec}f}"


def describe(values: list) -> Optional[dict]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {
        "n": len(vals),
        "mean": statistics.fmean(vals),
        "median": statistics.median(vals),
        "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0,
        "min": min(vals),
        "max": max(vals),
    }


def print_summary(title: str, rows: List[Tuple[str, str]],
                  runs: List[RunAudit]) -> None:
    print(title)
    print(f"  {'quantity':<46}{'n':>4}{'mean':>9}{'median':>9}"
          f"{'sd':>8}{'min':>9}{'max':>9}")
    for label, attr in rows:
        s = describe([getattr(r, attr) for r in runs])
        if s is None:
            print(f"  {label:<46}{0:>4}{'n/a':>9}")
            continue
        print(f"  {label:<46}{s['n']:>4}{s['mean']:>9.3f}{s['median']:>9.3f}"
              f"{s['sd']:>8.3f}{s['min']:>9.3f}{s['max']:>9.3f}")
    print()


ROWS_A = [
    ("end-to-end: first obs -> mission", "end_to_end"),
    ("first obs -> CandidateTarget", "obs_to_candidate"),
    ("CandidateTarget -> ConfirmedThreat", "candidate_to_confirmed"),
    ("ConfirmedThreat -> mission", "confirmed_to_mission"),
    ("mission -> first task", "mission_to_task"),
]
ROWS_B = [
    ("first CT -> auth at recorder [constant offset]",
     "confirmed_to_auth_offset"),
    ("first CT -> auth at recorder [/clock]", "confirmed_to_auth_clock"),
    ("first CT -> auth publication (estimate)", "confirmed_to_publish"),
    ("auth publication -> mission (T6 reception)", "publish_to_mission"),
    ("first CT -> mission", "confirmed_to_mission"),
    ("mission stamp lag (received - stamp)", "mission_stamp_lag"),
    ("consumed threat stamp - auth publication",
     "consumed_threat_minus_publish"),
    ("last CT before publication -> publication",
     "gap_last_threat_before_publish"),
    ("/clock residual on ConfirmedThreat", "clock_residual"),
    ("real-time factor, whole run", "rtf_run"),
]
ROWS_C = [
    ("motion start -> first acoustic obs", "motion_to_first_acoustic"),
    ("motion start -> first RF obs", "motion_to_first_rf"),
    ("motion start -> first radar obs", "motion_to_first_radar"),
    ("motion start -> CandidateTarget", "motion_to_candidate"),
    ("first obs -> CandidateTarget", "obs_to_candidate"),
    ("first obs -> first RF obs", "first_obs_to_rf"),
    ("first RF obs -> first LikelyDroneLink", "rf_to_drone_link"),
    ("radar+RF evidence -> CandidateTarget", "evidence_to_candidate"),
    ("intruder y at first acoustic obs", "y_first_acoustic"),
    ("intruder y at first RF obs", "y_first_rf"),
    ("intruder y at first radar obs", "y_first_radar"),
    ("intruder y at CandidateTarget", "y_candidate"),
]


def short(name: str) -> str:
    return name[len("coastal-"):] if name.startswith("coastal-") else name


def print_report(runs: List[RunAudit]) -> None:
    complete = [r for r in runs if r.complete]
    clean = [r for r in runs if r.clean]
    clean_complete = [r for r in complete if r.clean]
    print("=" * 104)
    print("TIMING AUDIT - nominal chain (sim time, seconds)")
    print("=" * 104)
    print(f"runs read: {len(runs)}   complete: {len(complete)}   "
          f"clean: {len(clean)}   clean and complete: {len(clean_complete)}")
    stamped = [short(r.bag) for r in runs if r.auth_stamp_set]
    print("auth messages carrying their own stamp: "
          + (", ".join(stamped) if stamped else "none"))
    print()

    print("[A] CHAIN LATENCIES (token stamps)")
    print(f"{'run':<17}{'clean':>6}{'compl':>6}{'e2e':>8}{'obs>cnd':>8}"
          f"{'cnd>CT':>8}{'CT>mis':>8}{'mis>tsk':>8}")
    for r in runs:
        print(f"{short(r.bag):<17}{fmt(r.clean, 6)}{fmt(r.complete, 6)}"
              f"{fmt(r.end_to_end)}{fmt(r.obs_to_candidate)}"
              f"{fmt(r.candidate_to_confirmed)}{fmt(r.confirmed_to_mission)}"
              f"{fmt(r.mission_to_task)}")
    print()
    print_summary("[A] SUMMARY over all complete runs",
                  ROWS_A, complete)
    print_summary("[A] SUMMARY over clean complete runs", ROWS_A,
                  clean_complete)

    print("[B] AUTHORISATION PATH")
    print(f"{'run':<17}{'clean':>6}{'nCT':>5}{'nAuth':>6}{'nMis':>5}"
          f"{'CT>rec':>8}{'CT>pub':>8}{'pub>T6':>8}{'CT>mis':>8}"
          f"{'thr-pub':>8}{'lastCT':>8}{'alive':>6}")
    for r in runs:
        print(f"{short(r.bag):<17}{fmt(r.clean, 6)}{fmt(r.n_confirmed, 5)}"
              f"{fmt(r.n_auth, 6)}{fmt(r.n_missions, 5)}"
              f"{fmt(r.confirmed_to_auth_clock)}{fmt(r.confirmed_to_publish)}"
              f"{fmt(r.publish_to_mission)}{fmt(r.confirmed_to_mission)}"
              f"{fmt(r.consumed_threat_minus_publish)}"
              f"{fmt(r.gap_last_threat_before_publish)}"
              f"{fmt(r.threat_alive_at_publish, 6)}")
    print("  nAuth    authorisation messages the recorder captured")
    print("  CT>rec   first ConfirmedThreat -> auth received by the recorder")
    print("  CT>pub   first ConfirmedThreat -> auth publication (earliest "
          "reception)")
    print("  pub>T6   auth publication -> mission (T6 reception)")
    print("  thr-pub  stamp of the threat the mission consumed - publication")
    print("  lastCT   publication - last ConfirmedThreat before it")
    print("  alive    a ConfirmedThreat was still within its TTL at "
          "publication")
    print()
    print_summary("[B] SUMMARY over clean complete runs", ROWS_B,
                  clean_complete)

    print("[C] FIRST OBSERVATION -> CANDIDATE (relative to intruder motion "
          "start)")
    print(f"{'run':<17}{'first':>9}{'m>acou':>8}{'m>rf':>8}{'m>radar':>8}"
          f"{'m>cand':>8}{'obs>cnd':>8}{'y@acou':>8}{'y@rf':>8}"
          f"{'y@radar':>8}{'y@cand':>8}{'last':>7}{'gtHz':>6}{'jumps':>6}")
    for r in runs:
        print(f"{short(r.bag):<17}{r.first_obs_source:>9}"
              f"{fmt(r.motion_to_first_acoustic)}{fmt(r.motion_to_first_rf)}"
              f"{fmt(r.motion_to_first_radar)}{fmt(r.motion_to_candidate)}"
              f"{fmt(r.obs_to_candidate)}"
              f"{fmt(r.y_first_acoustic, 8, 1)}{fmt(r.y_first_rf, 8, 1)}"
              f"{fmt(r.y_first_radar, 8, 1)}{fmt(r.y_candidate, 8, 1)}"
              f"{r.last_required_evidence:>7}{fmt(r.gt_rate_hz, 6, 0)}"
              f"{fmt(r.gt_jumps, 6)}")
    print()
    print_summary("[C] SUMMARY over clean complete runs", ROWS_C,
                  clean_complete)

    noted = [r for r in runs if r.notes]
    if noted:
        print("NOTES")
        for r in noted:
            print(f"  {short(r.bag)}: {r.notes}")


def write_csv(runs: List[RunAudit], path: str) -> None:
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    names = [f.name for f in fields(RunAudit)]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in runs:
            row = []
            for n in names:
                v = getattr(r, n)
                row.append("" if v is None else
                           (f"{v:.6f}" if isinstance(v, float) else v))
            w.writerow(row)
    print(f"\nper-run CSV written to {path}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Timing audit of nominal-chain bags (read-only).")
    ap.add_argument("bags", nargs="+", help="bag directories")
    ap.add_argument("--csv", default=None, help="write per-run values here")
    args = ap.parse_args()

    runs: List[RunAudit] = []
    for bag in sorted(args.bags):
        if not os.path.isfile(os.path.join(bag, "metadata.yaml")):
            print(f"[audit] skipping {bag}: not a bag directory",
                  file=sys.stderr)
            continue
        print(f"[audit] reading {bag} ...", file=sys.stderr)
        try:
            runs.append(audit(read_bag(bag),
                              os.path.basename(os.path.normpath(bag))))
        except Exception as e:  # report and go on with the other bags
            print(f"[audit] {bag}: failed ({e})", file=sys.stderr)
    if not runs:
        print("no readable bags", file=sys.stderr)
        return 1
    print_report(runs)
    if args.csv:
        write_csv(runs, args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())