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
audit_recordings.py - check that recorded runs are clean, and recompute their
time figures on both time axes.

Read-only analysis of bags that are already recorded; it starts nothing.

Pipeline runs (bags with observation tokens, from record_run.sh)

  A run is clean when nothing outside the run took part in it:
    - the intruder ground truth has one publisher: no two consecutive samples
      more than GT_JUMP_M apart, and at most GT_MAX_RATE_HZ samples per
      second (the intruder publishes at 20 Hz);
    - /clock comes from one simulator: simulated time never goes back;
    - each sensing agent runs once: the counter at the end of the observation
      ids never goes back. Every agent numbers its own tokens, so a second
      agent of the same modality (for example one left over from a previous
      run) shows up as a counter that goes back;
    - one target is observed;
    - a run configured to deny has no "authorise" decision;
    - every token is stamped in simulated time: no producer ran on the wall
      clock.
  The counters of the interpretation ids are checked the same way, but only
  reported (intBk): their format depends on the transitions.

  Time figures, on both axes:
    - sim: the token stamps (simulated time), as in audit_timing.py;
    - rx:  the recorder receive time (wall clock).

  Intruder speed: in simulated time (ground truth against /clock) and on the
  ground-truth stamps. An intruder that integrates its motion on the wall
  clock moves, in simulated time, at its commanded speed divided by the
  real-time factor.

Safety Board runs (bags with /safety_status and no tokens, from
record_veto.sh)

  A run is clean when:
    - no simulator was running: no /clock message;
    - the coordination layer was not running: no digital-layer message;
    - each sensor has one publisher: its stamps are on one clock, and each
      hazard is one block of out-of-bounds samples, not samples flapping
      between two publishers.
  When /clock or the digital-layer topics are not in the recording, the
  first two checks cannot be made, and the report says so.

  Reaction time, at the resolution of the recording: from the first
  out-of-bounds sensor sample to the first unsafe /safety_status, and to the
  first zero /actuator_cmd_safe while the raw command is non-zero. A hazard
  that starts while the board is already unsafe has no reaction time.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/audit_recordings.py bags/<run>... \\
        --csv results/audit_recordings.csv

    A bag is named by its folder (<configuration>-YYYYMMDD-HHMMSS), or, in a
    campaign, by its configuration and run folders
    (<campaign>/<configuration>/run-NN-seedS/bag).

@author Luca D'Aurizio
"""

import argparse
import bisect
import csv
import math
import os
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field, fields
from typing import Callable, Dict, List, Optional, Tuple

import yaml

from audit_timing import (AUTHORISE, BOOL_TYPE, GT_JUMP_M, GT_TYPE, SOURCES,
                          TYPES, ClockMap, describe, diff, fmt, stamp_s,
                          storage_id)

GT_MAX_RATE_HZ = 30.0  # the intruder publishes its ground truth at 20 Hz
WALL_EPOCH_S = 1.0e9   # a stamp past this (year 2001) is wall-clock time
MOVING_STEP_M = 1e-3   # a ground-truth step longer than this: intruder moving
FLAP_BLOCKS = 3        # more out-of-bounds blocks per hazard: flapping

# Topics of the Safety Board runs, by kind.
SAFETY_TOPICS = {
    "status": "/safety_status",
    "raw": "/actuator_cmd_raw",
    "safe": "/actuator_cmd_safe",
    "proximity": "/drone/proximity",
    "imu": "/drone/imu",
    "battery": "/drone/battery",
    "altitude": "/drone/altitude",
}

# Safety Board defaults (safety_board_node.hpp).
MIN_PROXIMITY_M = 1.5
MAX_TILT_DEG = 30.0      # pitch and roll
MIN_BATTERY_PCT = 15.0
MIN_ALTITUDE_M = 0.3
MAX_ALTITUDE_M = 50.0
STATUS_UNSAFE = 0.5      # /safety_status below this: unsafe
CMD_ACTIVE = 0.01        # raw command above this: a live command
CMD_ZERO = 1e-3          # safe command below this: clamped to zero

# What a run of each configuration must produce, by the name of its bags.
EXPECTED = {
    "coastal": "mission",
    "nominal": "mission",
    "vec-frontal": "mission",
    "loss-none": "mission",
    "loss-acoustic": "mission",
    "deny": "no-mission",
    "stale-eo": "stale-eo",
    "civilian": "civilian",
    "vec-east-deep": "cand-only",
    "vec-rear": "cand-only",
    "loss-radar": "no-cand",
    "loss-rf": "no-cand",
    "loss-eo": "no-eo",
    # A faulty UAV worker changes the flight, not the chain.
    "fault-worker": "mission",
    "fault-gate": "mission",
    "nominal-gate": "mission",
    # Forged observations: the threat forms from injected evidence; the mission
    # forms only under authorisation.
    "forge-obs-authorise": "mission",
    "forge-obs-deny": "no-mission",
}
OUTCOMES: Dict[str, Callable] = {
    # ConfirmedThreat and mission.
    "mission": lambda r: r.threats > 0 and r.missions > 0,
    # ConfirmedThreat without mission: authorisation withheld.
    "no-mission": lambda r: r.threats > 0 and r.missions == 0,
    # Candidate and EO confirmation, but no ConfirmedThreat: the EO arrived
    # too late.
    "stale-eo": lambda r: (r.candidates > 0 and r.aerial_objects > 0
                           and r.threats == 0),
    # Civilian RF label and no candidate: no concordant evidence.
    "civilian": lambda r: r.civilian > 0 and r.candidates == 0,
    # Candidate without ConfirmedThreat.
    "cand-only": lambda r: r.candidates > 0 and r.threats == 0,
    # No candidate.
    "no-cand": lambda r: r.candidates == 0,
    # Candidate, no EO confirmation, no ConfirmedThreat.
    "no-eo": lambda r: (r.candidates > 0 and r.aerial_objects == 0
                        and r.threats == 0),
}

CAMPAIGN_RUN = re.compile(r"^run-\d+-seed\d+(-try\d+)?$")
TIMESTAMPED = re.compile(r"^(?P<config>.+)-(?P<stamp>\d{8}-\d{6})$")
SEQ_ID = re.compile(r"^(?P<prefix>.*?)(?P<n>\d+)$")


# =============================================================================
# Bag reading
# =============================================================================
@dataclass
class RunData:
    """What the audit reads from one bag."""
    path: str
    types: Dict[str, str] = field(default_factory=dict)   # every topic: type
    counts: Dict[str, int] = field(default_factory=dict)  # messages per topic
    topics: Dict[str, list] = field(default_factory=dict)  # topic: [(rx, msg)]
    kind_of: Dict[str, str] = field(default_factory=dict)  # topic: kind
    base_s: float = 0.0  # receive time of the first message read, epoch s

    def get(self, kind: str) -> list:
        """Messages of every topic of one kind, in receive order.

        @return [(rx_s, msg), ...], rx_s relative to the first message read.
        """
        out: list = []
        for name, k in self.kind_of.items():
            if k == kind:
                out.extend(self.topics[name])
        out.sort(key=lambda p: p[0])
        return out

    def count(self, name: str) -> int:
        """Messages of a topic: from metadata.yaml, else from what was read."""
        if name in self.counts:
            return self.counts[name]
        return len(self.topics.get(name, []))


def classify(name: str, type_name: str) -> Optional[str]:
    """Kind of a topic for this audit, or None if the audit does not read it."""
    for kind, ty in TYPES.items():
        if ty == type_name:
            return kind
    if type_name == GT_TYPE and "intruder" in name:
        return "gt"
    if type_name == BOOL_TYPE and "intruder" in name and "active" in name:
        return "active"
    for kind, topic in SAFETY_TOPICS.items():
        if name == topic:
            return kind
    return None


def message_counts(bag_dir: str) -> Dict[str, int]:
    """Messages per topic, from metadata.yaml (empty if unreadable)."""
    try:
        with open(os.path.join(bag_dir, "metadata.yaml")) as f:
            info = yaml.safe_load(f)["rosbag2_bagfile_information"]
        return {t["topic_metadata"]["name"]: int(t.get("message_count", 0))
                for t in info.get("topics_with_message_count", [])}
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
        return {}


def read_run(bag_dir: str) -> RunData:
    """Read the topics this audit needs from one bag."""
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as e:
        sys.exit("Cannot import the ROS 2 Python modules ({}).\n"
                 "Run `source /opt/ros/humble/setup.bash && "
                 "source install/setup.bash` first.".format(e))

    data = RunData(path=bag_dir, counts=message_counts(bag_dir))
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=storage_id(bag_dir)),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                    output_serialization_format="cdr"),
    )
    classes = {}
    for topic in reader.get_all_topics_and_types():
        data.types[topic.name] = topic.type
        kind = classify(topic.name, topic.type)
        if kind is None:
            continue
        try:
            classes[topic.name] = get_message(topic.type)
        except (AttributeError, ModuleNotFoundError, ValueError):
            continue
        data.kind_of[topic.name] = kind
        data.topics[topic.name] = []
    if not classes:
        return data

    reader.set_filter(rosbag2_py.StorageFilter(topics=list(classes)))
    base_ns = None
    while reader.has_next():
        topic, raw, rx_ns = reader.read_next()
        if topic not in classes:
            continue
        if base_ns is None:
            base_ns = rx_ns
            data.base_s = rx_ns * 1e-9
        try:
            msg = deserialize_message(raw, classes[topic])
        except Exception:  # a single corrupt message must not stop the audit
            continue
        data.topics[topic].append(((rx_ns - base_ns) * 1e-9, msg))
    return data


def identity(bag_dir: str) -> Tuple[str, str]:
    """Configuration and run of a bag, from its path."""
    path = os.path.normpath(bag_dir)
    name = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    if name == "bag" and CAMPAIGN_RUN.match(parent):
        return os.path.basename(os.path.dirname(os.path.dirname(path))), parent
    m = TIMESTAMPED.match(name)
    if m:
        return m.group("config"), m.group("stamp")
    return name, ""


# =============================================================================
# Helpers
# =============================================================================
def clock_of(t: float) -> str:
    """Clock a stamp belongs to: unset (0), sim or wall."""
    if t <= 0.0:
        return "unset"
    return "wall" if t >= WALL_EPOCH_S else "sim"


def clocks(stamps: List[float]) -> str:
    """The clock of a set of stamps, or mixed(...) if more than one."""
    seen = sorted({clock_of(t) for t in stamps})
    if not seen:
        return ""
    return seen[0] if len(seen) == 1 else "mixed(" + "+".join(seen) + ")"


def counter_backsteps(msgs: list, stream: Callable) -> Dict[str, int]:
    """Times the counter at the end of the token ids goes back, per stream.

    The tokens are taken in the order the recorder received them, which for
    one producer is the order of publication. A stream is stream(msg) plus
    the id prefix; ids without a trailing number are ignored.

    @return {stream: backsteps}, only for streams with at least one.
    """
    last: Dict[str, int] = {}
    back: Dict[str, int] = {}
    for _, m in msgs:
        mm = SEQ_ID.match(getattr(m, "id", "") or "")
        if not mm:
            continue
        group, prefix = str(stream(m)), mm.group("prefix")
        key = prefix if prefix.startswith(group) else group + ":" + prefix
        n = int(mm.group("n"))
        if key in last and n < last[key]:
            back[key] = back.get(key, 0) + 1
        last[key] = n
    return back


def clock_backsteps(clock_msgs: list) -> int:
    """Times simulated time goes back between two /clock messages."""
    n, last = 0, None
    for _, m in clock_msgs:
        t = stamp_s(m.clock)
        if t <= 0.0:
            continue
        if last is not None and t < last:
            n += 1
        last = t
    return n


def jumps(points: List[Tuple[float, float, float, float]]) -> int:
    """Consecutive (t, x, y, z) samples farther apart than GT_JUMP_M."""
    return sum(1 for a, b in zip(points, points[1:])
               if math.dist(a[1:], b[1:]) > GT_JUMP_M)


def track_speed(points: List[Tuple[float, float, float, float]]
                ) -> Optional[float]:
    """Mean speed over the moving part of a time-ordered (t, x, y, z) track."""
    steps = [i for i in range(1, len(points))
             if math.dist(points[i][1:], points[i - 1][1:]) > MOVING_STEP_M]
    if len(steps) < 2:
        return None
    first, last = steps[0] - 1, steps[-1]
    length = sum(math.dist(points[i][1:], points[i - 1][1:])
                 for i in range(first + 1, last + 1))
    span = points[last][0] - points[first][0]
    return length / span if span > 0.0 else None


def first_stamp(msgs: list, pred: Callable = lambda m: True
                ) -> Optional[float]:
    """Earliest stamp `t` of the matching tokens stamped in simulated time."""
    ts = [stamp_s(m.t) for _, m in msgs
          if pred(m) and clock_of(stamp_s(m.t)) == "sim"]
    return min(ts) if ts else None


def first_rx(msgs: list, pred: Callable = lambda m: True) -> Optional[float]:
    """Earliest receive time (rx seconds) of the matching messages."""
    ts = [rx for rx, m in msgs if pred(m)]
    return min(ts) if ts else None


def rate_hz(samples: list) -> Optional[float]:
    """Messages per second over the span of a time-ordered list."""
    if len(samples) < 2:
        return None
    span = samples[-1][0] - samples[0][0]
    return (len(samples) - 1) / span if span > 0.0 else None


def by_label(label: str) -> Callable:
    return lambda m: m.label == label


# =============================================================================
# Pipeline runs
# =============================================================================
@dataclass
class ChainRun:
    """Audit of one pipeline run. Times in seconds."""
    bag: str = ""
    configuration: str = ""
    run: str = ""
    clean: bool = True
    problems: str = ""
    expected: str = ""
    outcome_ok: Optional[bool] = None
    # --- what the run produced, for its target ---
    target_id: str = ""
    targets: int = 0
    obs_radar: int = 0
    obs_rf: int = 0
    obs_acoustic: int = 0
    obs_eo: int = 0
    possible_uav: int = 0
    drone_link: int = 0
    civilian: int = 0
    aerial_objects: int = 0
    candidates: int = 0
    threats: int = 0
    authorise: int = 0
    deny: int = 0
    auth_clock: str = ""
    missions: int = 0
    tasks: int = 0
    # --- cleanliness ---
    gt_topic: str = ""
    gt_samples: int = 0
    gt_rate_hz: Optional[float] = None     # per second of recorder time
    gt_jumps: Optional[int] = None         # on the ground-truth topic
    gt_jumps_all: Optional[int] = None     # every intruder pose topic merged
    clock_backsteps: Optional[int] = None
    obs_backsteps: int = 0
    interp_backsteps: int = 0
    backstep_streams: str = ""
    wall_tokens: int = 0
    unset_tokens: int = 0
    # --- clocks and intruder ---
    rtf: Optional[float] = None
    gt_clock: str = ""
    v_sim: Optional[float] = None
    v_stamp: Optional[float] = None
    route_done: Optional[bool] = None
    # --- times, sim axis (token stamps) ---
    obs_to_candidate: Optional[float] = None
    candidate_to_threat: Optional[float] = None
    obs_to_threat: Optional[float] = None
    threat_to_mission: Optional[float] = None
    obs_to_mission: Optional[float] = None
    first_source: str = ""
    first_radar: Optional[float] = None    # after the first observation
    first_rf: Optional[float] = None
    first_acoustic: Optional[float] = None
    first_eo: Optional[float] = None
    # --- times, rx axis (recorder receive time) ---
    rx_obs_to_candidate: Optional[float] = None
    rx_obs_to_threat: Optional[float] = None
    rx_obs_to_mission: Optional[float] = None
    notes: str = ""


def audit_chain(data: RunData) -> ChainRun:
    """Audit one pipeline run from its read_run() output."""
    config, run = identity(data.path)
    r = ChainRun(bag=data.path, configuration=config, run=run,
                 expected=EXPECTED.get(config, ""))
    problems: List[str] = []
    notes: List[str] = []
    clk = ClockMap(data.get("clock"))

    # --- the target and what the run produced for it ---------------------------
    obs_all = data.get("obs")
    interp_all = data.get("interp")
    seen = Counter(m.target_id for _, m in obs_all if m.target_id)
    r.targets = len(seen)
    if not seen:
        r.clean = False
        r.problems = "no observation of any target"
        return r
    r.target_id = max(seen, key=seen.get)
    if r.targets > 1:
        problems.append("{} targets observed: {}".format(
            r.targets, ", ".join(sorted(seen))))

    def mine(kind: str) -> list:
        return [(rx, m) for rx, m in data.get(kind)
                if m.target_id == r.target_id]

    obs, interp = mine("obs"), mine("interp")
    missions, tasks, auths = mine("mission"), mine("task"), mine("auth")
    by_source = Counter(m.source for _, m in obs)
    for src in SOURCES:
        setattr(r, "obs_" + src, by_source.get(src, 0))
    labels = Counter(m.label for _, m in interp)
    r.possible_uav = labels.get("PossibleUAV", 0)
    r.drone_link = labels.get("LikelyDroneLink", 0)
    r.civilian = labels.get("LikelyCivilianTraffic", 0)
    r.aerial_objects = labels.get("ConfirmedAerialObject", 0)
    r.candidates = labels.get("CandidateTarget", 0)
    r.threats = labels.get("ConfirmedThreat", 0)
    r.missions, r.tasks = len(missions), len(tasks)
    r.authorise = sum(1 for _, m in auths if m.decision in AUTHORISE)
    r.deny = sum(1 for _, m in auths if m.decision == "deny")
    r.auth_clock = clocks([stamp_s(m.t) for _, m in auths])
    others = len(data.get("auth")) - len(auths)
    if others:
        notes.append("{} decision(s) for other targets".format(others))
    if r.expected:
        r.outcome_ok = bool(OUTCOMES[r.expected](r))
    if config == "deny" and r.authorise:
        problems.append("{} authorise decision(s) in a deny run".format(
            r.authorise))
    if r.missions > 1:
        notes.append("{} missions for the target".format(r.missions))

    # --- one producer per token stream ------------------------------------------
    back_obs = counter_backsteps(obs_all, lambda m: m.source)
    back_int = counter_backsteps(interp_all, lambda m: m.label)
    r.obs_backsteps = sum(back_obs.values())
    r.interp_backsteps = sum(back_int.values())
    r.backstep_streams = ", ".join(
        "{} {}".format(k, v) for k, v in sorted({**back_obs,
                                                  **back_int}.items()))
    if r.obs_backsteps:
        problems.append("observation counters went back ({}): more than one "
                        "agent per modality".format(
                            ", ".join("{} {}".format(k, v)
                                      for k, v in sorted(back_obs.items()))))
    if r.interp_backsteps:
        notes.append("interpretation counters went back ({})".format(
            ", ".join("{} {}".format(k, v)
                      for k, v in sorted(back_int.items()))))

    # --- every token in simulated time ------------------------------------------
    for kind in ("obs", "interp", "mission", "task"):
        for _, m in data.get(kind):
            c = clock_of(stamp_s(m.t))
            r.wall_tokens += c == "wall"
            r.unset_tokens += c == "unset"
    if r.wall_tokens:
        problems.append("{} token(s) stamped on the wall clock: a producer "
                        "without simulated time".format(r.wall_tokens))
    if r.unset_tokens:
        notes.append("{} token(s) with an unset stamp".format(r.unset_tokens))
    if auths and r.auth_clock != "sim":
        notes.append("authorisation stamps: {}".format(r.auth_clock))

    # --- /clock ---------------------------------------------------------------
    # Receive times are mapped to simulated time only if /clock is consistent.
    clock_msgs = data.get("clock")
    clock_ok = False
    if clock_msgs:
        r.clock_backsteps = clock_backsteps(clock_msgs)
        if r.clock_backsteps:
            problems.append("simulated time went back {} time(s): more than "
                            "one simulator, or a restart".format(
                                r.clock_backsteps))
        else:
            clock_ok = clk.ok()
            r.rtf = clk.rtf()
    else:
        notes.append("no /clock: simulated-time checks not made")

    # --- intruder ground truth ----------------------------------------------------
    pose_topics = {n: d for n, d in data.topics.items()
                   if data.kind_of.get(n) == "gt"}
    if pose_topics:
        ends = [n for n in pose_topics if n.endswith("ground_truth")]
        r.gt_topic = ends[0] if ends else max(
            pose_topics, key=lambda n: len(pose_topics[n]))
        gt = pose_topics[r.gt_topic]
        r.gt_samples = len(gt)
        r.gt_rate_hz = rate_hz(gt)
        stamps = [stamp_s(m.header.stamp) for _, m in gt]
        r.gt_clock = clocks(stamps)
        # Samples are ordered in simulated time (/clock), else on their own
        # stamps, else in the order they were received.
        if clock_ok:
            axis = "clock"
        elif r.gt_clock in ("sim", "wall"):
            axis = "stamp"
        else:
            axis = "rx"

        def track(msgs: list, on: str) -> list:
            pts = []
            for rx, m in msgs:
                p = m.pose.position
                if on == "clock":
                    if not clk.inside(rx):
                        continue
                    t = clk(rx)
                elif on == "stamp":
                    t = stamp_s(m.header.stamp)
                else:
                    t = rx
                pts.append((t, p.x, p.y, p.z))
            pts.sort(key=lambda q: q[0])
            return pts

        main_track = track(gt, axis)
        r.gt_jumps = jumps(main_track)
        merged = [p for d in pose_topics.values() for p in d]
        r.gt_jumps_all = jumps(track(merged, axis))
        if r.gt_jumps:
            problems.append("intruder ground truth from more than one "
                            "source ({} jumps > {:.0f} m)".format(
                                r.gt_jumps, GT_JUMP_M))
        elif r.gt_jumps_all:
            notes.append("{} jumps only with every intruder pose topic "
                         "merged".format(r.gt_jumps_all))
        if r.gt_rate_hz and r.gt_rate_hz > GT_MAX_RATE_HZ:
            problems.append("intruder ground truth at {:.0f} Hz: more than "
                            "one publisher".format(r.gt_rate_hz))
        busy = sorted(n for n, d in pose_topics.items()
                      if d and n != r.gt_topic)
        if busy:
            notes.append("other intruder pose topics with messages: "
                         + ", ".join("{} ({})".format(n, len(pose_topics[n]))
                                     for n in busy))
        if not r.gt_jumps:
            if axis == "clock":
                r.v_sim = track_speed(main_track)
            if r.gt_clock in ("sim", "wall"):
                r.v_stamp = track_speed(track(gt, "stamp"))
    else:
        notes.append("no intruder ground truth: one-intruder check not made")
    active = [bool(m.data) for _, m in data.get("active")]
    if active:
        r.route_done = True in active and not active[-1]
        if not r.route_done:
            notes.append("the intruder had not reached its target when the "
                         "recording ended")

    # --- times, sim axis ----------------------------------------------------------
    t_obs = first_stamp(obs)
    t_cand = first_stamp(interp, by_label("CandidateTarget"))
    t_threat = first_stamp(interp, by_label("ConfirmedThreat"))
    t_mission = first_stamp(missions)
    r.obs_to_candidate = diff(t_obs, t_cand)
    r.candidate_to_threat = diff(t_cand, t_threat)
    r.obs_to_threat = diff(t_obs, t_threat)
    r.threat_to_mission = diff(t_threat, t_mission)
    r.obs_to_mission = diff(t_obs, t_mission)
    firsts = {src: first_stamp(obs, lambda m, s=src: m.source == s)
              for src in SOURCES}
    for src in SOURCES:
        setattr(r, "first_" + src, diff(t_obs, firsts[src]))
    present = {s: t for s, t in firsts.items() if t is not None}
    if present:
        r.first_source = min(present, key=present.get)

    # --- times, rx axis -----------------------------------------------------------
    rx_obs = first_rx(obs)
    r.rx_obs_to_candidate = diff(rx_obs, first_rx(
        interp, by_label("CandidateTarget")))
    r.rx_obs_to_threat = diff(rx_obs, first_rx(
        interp, by_label("ConfirmedThreat")))
    r.rx_obs_to_mission = diff(rx_obs, first_rx(missions))

    r.clean = not problems
    r.problems = "; ".join(problems)
    r.notes = "; ".join(notes)
    return r


# =============================================================================
# Safety Board runs
# =============================================================================
@dataclass
class VetoRun:
    """Audit of one Safety Board run. Times in seconds unless stated."""
    bag: str = ""
    configuration: str = ""
    run: str = ""
    clean: bool = True
    problems: str = ""
    duration_s: Optional[float] = None
    topics: int = 0
    other_topics: str = ""
    clock_messages: Optional[int] = None    # None: /clock not recorded
    digital_messages: Optional[int] = None  # None: no digital-layer topic
    rates_hz: str = ""
    stamp_clock: str = ""
    stamp_lag_ms: Optional[float] = None    # receive time - stamp, median
    blocks: str = ""
    onsets: int = 0
    measurable: int = 0
    reaction_status_ms: Optional[float] = None
    reaction_cmd_ms: Optional[float] = None
    reactions: str = ""
    notes: str = ""


def tilt_deg(q) -> float:
    """Larger of |pitch| and |roll| of a quaternion, as the board computes."""
    roll = math.degrees(math.atan2(2.0 * (q.w * q.x + q.y * q.z),
                                   1.0 - 2.0 * (q.x * q.x + q.y * q.y)))
    sinp = max(-1.0, min(1.0, 2.0 * (q.w * q.y - q.z * q.x)))
    return max(abs(math.degrees(math.asin(sinp))), abs(roll))


def series(data: RunData, kind: str, value: Callable) -> list:
    """[(rx_s, value)] of one kind; messages value() cannot read are skipped."""
    out = []
    for rx, m in data.get(kind):
        try:
            out.append((rx, value(m)))
        except (AttributeError, TypeError, ValueError):
            continue
    return out


def blocks_of(samples: list, bad: Callable) -> List[Tuple[float, float]]:
    """Blocks of consecutive out-of-bounds samples, as (first, last) times."""
    out: List[Tuple[float, float]] = []
    start = prev = None
    for t, v in samples:
        if bad(v):
            if start is None:
                start = t
            prev = t
        elif start is not None:
            out.append((start, prev))
            start = None
    if start is not None:
        out.append((start, prev))
    return out


def value_at(samples: list, times: list, t: float):
    """Value of the last sample at or before t, or None."""
    i = bisect.bisect_right(times, t)
    return samples[i - 1][1] if i else None


def audit_veto(data: RunData) -> VetoRun:
    """Audit one Safety Board run from its read_run() output."""
    config, run = identity(data.path)
    r = VetoRun(bag=data.path, configuration=config, run=run)
    problems: List[str] = []
    notes: List[str] = []

    # --- nothing else running ---------------------------------------------------
    r.topics = len(data.types)
    r.other_topics = ", ".join(sorted(
        n for n in data.types if n not in SAFETY_TOPICS.values()))
    clock_topics = [n for n, ty in data.types.items() if ty == TYPES["clock"]]
    digital = [n for n, ty in data.types.items()
               if ty.startswith("guarded_swarms_msgs/")
               and n not in SAFETY_TOPICS.values()]
    if clock_topics:
        r.clock_messages = sum(data.count(n) for n in clock_topics)
        if r.clock_messages:
            problems.append("{} /clock message(s): a simulator was "
                            "running".format(r.clock_messages))
    if digital:
        r.digital_messages = sum(data.count(n) for n in digital)
        if r.digital_messages:
            problems.append("{} digital-layer message(s): the coordination "
                            "layer was running".format(r.digital_messages))
    unchecked = [w for w, ok in (("/clock", clock_topics),
                                 ("digital-layer topics", digital)) if not ok]
    if unchecked:
        notes.append("not in the recording: " + ", ".join(unchecked))

    # --- streams ------------------------------------------------------------------
    status = series(data, "status", lambda m: float(m.data))
    raw = series(data, "raw", lambda m: float(m.data))
    safe = series(data, "safe", lambda m: float(m.data))
    sensors = {
        "proximity": (series(data, "proximity", lambda m: float(m.range)),
                      lambda v: v < MIN_PROXIMITY_M),
        "attitude": (series(data, "imu", lambda m: tilt_deg(m.orientation)),
                     lambda v: v > MAX_TILT_DEG),
        "battery": (series(data, "battery",
                           lambda m: float(m.percentage) * 100.0),
                    lambda v: v < MIN_BATTERY_PCT),
        "altitude": (series(data, "altitude", lambda m: float(m.data)),
                     lambda v: v < MIN_ALTITUDE_M or v > MAX_ALTITUDE_M),
    }
    if not status:
        problems.append("no /safety_status")
    else:
        r.duration_s = status[-1][0] - status[0][0]
    rates = []
    for kind in SAFETY_TOPICS:
        hz = rate_hz(data.get(kind))
        rates.append("{} {}".format(kind, "n/a" if hz is None
                                    else "{:.1f}".format(hz)))
    r.rates_hz = ", ".join(rates)

    # --- one publisher per sensor: stamps on one clock ----------------------------
    lags: List[float] = []
    stamp_clocks = []
    for kind in ("proximity", "imu", "battery"):
        st = []
        for rx, m in data.get(kind):
            try:
                s = stamp_s(m.header.stamp)
            except AttributeError:
                continue
            st.append(s)
            if clock_of(s) == "wall":
                lags.append(data.base_s + rx - s)
        if st:
            c = clocks(st)
            stamp_clocks.append("{} {}".format(kind, c))
            if c.startswith("mixed"):
                problems.append("{} stamps on more than one clock: more than "
                                "one publisher".format(kind))
    r.stamp_clock = ", ".join(stamp_clocks)
    if lags:
        r.stamp_lag_ms = statistics.median(lags) * 1000.0

    # --- hazards and reaction times -------------------------------------------------
    st_times = [t for t, _ in status]
    raw_times = [t for t, _ in raw]
    safe_times = [t for t, _ in safe]
    found = []
    status_ms: List[float] = []
    cmd_ms: List[float] = []
    for name, (samples, bad) in sensors.items():
        blocks = blocks_of(samples, bad)
        found.append("{} {}".format(name, len(blocks)))
        if len(blocks) > FLAP_BLOCKS:
            problems.append("{}: {} out-of-bounds blocks, flapping between "
                            "two publishers?".format(name, len(blocks)))
        for t_on, _ in blocks:
            r.onsets += 1
            before = value_at(status, st_times, t_on)
            if before is None or before < STATUS_UNSAFE:
                continue  # the board was not up yet, or already unsafe
            r.measurable += 1
            i = bisect.bisect_left(st_times, t_on)
            t_st = next((t for t, v in status[i:] if v < STATUS_UNSAFE), None)
            t_cmd = None
            for t, v in safe[bisect.bisect_left(safe_times, t_on):]:
                rv = value_at(raw, raw_times, t)
                if abs(v) < CMD_ZERO and rv is not None and rv > CMD_ACTIVE:
                    t_cmd = t
                    break
            ms_st = None if t_st is None else (t_st - t_on) * 1000.0
            ms_cmd = None if t_cmd is None else (t_cmd - t_on) * 1000.0
            if ms_st is not None:
                status_ms.append(ms_st)
            if ms_cmd is not None:
                cmd_ms.append(ms_cmd)
            r.reactions += "{}{} {}/{} ms".format(
                "; " if r.reactions else "", name,
                "n/a" if ms_st is None else "{:.0f}".format(ms_st),
                "n/a" if ms_cmd is None else "{:.0f}".format(ms_cmd))
    r.blocks = ", ".join(found)
    if status_ms:
        r.reaction_status_ms = statistics.median(status_ms)
    if cmd_ms:
        r.reaction_cmd_ms = statistics.median(cmd_ms)
    if r.onsets > r.measurable:
        notes.append("{} of {} hazards started while the board was already "
                     "unsafe (or not up yet): no reaction time".format(
                         r.onsets - r.measurable, r.onsets))

    r.clean = not problems
    r.problems = "; ".join(problems)
    r.notes = "; ".join(notes)
    return r


# =============================================================================
# Report
# =============================================================================
def ms(values: list) -> str:
    """mean+-sd (sample sd) of the values that are not None, or n/a."""
    s = describe(values)
    if s is None:
        return "n/a"
    return "{:.2f}+-{:.2f}".format(s["mean"], s["sd"])


def mean_of(values: list, prec: int = 2) -> str:
    s = describe(values)
    return "n/a" if s is None else "{:.{}f}".format(s["mean"], prec)


def print_chain(runs: List[ChainRun]) -> None:
    w = 104
    print("=" * w)
    print("PIPELINE RUNS: {}   clean: {}".format(
        len(runs), sum(r.clean for r in runs)))
    print("=" * w)
    print("{:<14}{:<17}{:>6}{:>5}{:>6}{:>6}{:>6}{:>6}{:>6}{:>5}{:>6}"
          "{:>7}{:>5}{:>5}{:>5}".format(
              "config", "run", "clean", "ok", "gtHz", "jumps", "clkBk",
              "obsBk", "intBk", "tgts", "wallT", "auth", "cand", "CT",
              "mis"))
    for r in runs:
        print("{:<14}{:<17}{}{}{}{}{}{}{}{}{}{:>7}{}{}{}".format(
            r.configuration[:13], r.run[:16], fmt(r.clean, 6),
            fmt(r.outcome_ok, 5), fmt(r.gt_rate_hz, 6, 1),
            fmt(r.gt_jumps, 6), fmt(r.clock_backsteps, 6),
            fmt(r.obs_backsteps, 6), fmt(r.interp_backsteps, 6),
            fmt(r.targets, 5), fmt(r.wall_tokens, 6),
            "{}/{}".format(r.authorise, r.deny), fmt(r.candidates, 5),
            fmt(r.threats, 5), fmt(r.missions, 5)))
    print("  ok     the run produced what its configuration must produce")
    print("  gtHz   intruder ground-truth samples per second of recorder "
          "time (one publisher: 20)")
    print("  jumps  consecutive ground-truth samples more than {:.0f} m "
          "apart".format(GT_JUMP_M))
    print("  clkBk  times simulated time went back")
    print("  obsBk  times an observation counter went back; intBk the same "
          "for interpretations")
    print("  tgts   targets observed; wallT tokens stamped on the wall clock")
    print("  auth   authorise/deny decisions; cand, CT, mis: CandidateTarget, "
          "ConfirmedThreat, missions")
    print()
    print("TIMES (seconds; sim = token stamps, rx = recorder receive time)")
    print("{:<14}{:<17}{:>6}{:>7}{:>7}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8}"
          .format("config", "run", "rtf", "v_sim", "v_stmp", "gtClock",
                  "o>c sim", "o>c rx", "c>T sim", "o>T sim", "o>T rx",
                  "o>M sim"))
    for r in runs:
        print("{:<14}{:<17}{}{}{}{:>8}{}{}{}{}{}{}".format(
            r.configuration[:13], r.run[:16], fmt(r.rtf, 6, 3),
            fmt(r.v_sim, 7), fmt(r.v_stamp, 7), r.gt_clock[:7] or "n/a",
            fmt(r.obs_to_candidate), fmt(r.rx_obs_to_candidate),
            fmt(r.candidate_to_threat), fmt(r.obs_to_threat),
            fmt(r.rx_obs_to_threat), fmt(r.obs_to_mission)))
    print("  v_sim   intruder speed in simulated time (ground truth against "
          "/clock), m/s")
    print("  v_stmp  intruder speed on the ground-truth stamps, m/s; gtClock "
          "the clock of those stamps")
    print("  o>c first observation -> CandidateTarget, c>T CandidateTarget -> "
          "ConfirmedThreat,")
    print("  o>T first observation -> ConfirmedThreat, o>M first observation "
          "-> mission")
    print()

    configs = sorted({r.configuration for r in runs})
    print("SUMMARY BY CONFIGURATION (mean+-sd, sample sd, over the runs that "
          "have the value)")
    print("{:<14}{:>5}{:>6}{:>4}{:>7}{:>6}{:>7}{:>12}{:>12}{:>12}{:>12}"
          "{:>12}{:>12}".format("config", "runs", "clean", "ok", "rtf",
                                "v_sim", "v_stmp", "o>c sim", "o>c rx",
                                "o>T sim", "o>T rx", "o>M sim", "o>M rx"))
    for c in configs:
        rs = [r for r in runs if r.configuration == c]
        oks = [r.outcome_ok for r in rs if r.outcome_ok is not None]
        print("{:<14}{:>5}{:>6}{:>4}{:>7}{:>6}{:>7}{:>12}{:>12}{:>12}{:>12}"
              "{:>12}{:>12}".format(
                  c[:13], len(rs), sum(r.clean for r in rs),
                  "{}".format(sum(oks)) if oks else "-",
                  mean_of([r.rtf for r in rs], 3),
                  mean_of([r.v_sim for r in rs]),
                  mean_of([r.v_stamp for r in rs]),
                  ms([r.obs_to_candidate for r in rs]),
                  ms([r.rx_obs_to_candidate for r in rs]),
                  ms([r.obs_to_threat for r in rs]),
                  ms([r.rx_obs_to_threat for r in rs]),
                  ms([r.obs_to_mission for r in rs]),
                  ms([r.rx_obs_to_mission for r in rs])))
    print()
    print("FIRST OBSERVATION OF EACH MODALITY (sim seconds after the first "
          "observation, mean)")
    print("{:<14}{:>5}  {:<22}{:>9}{:>9}{:>9}{:>9}".format(
        "config", "runs", "first (runs)", "radar", "rf", "acoustic", "eo"))
    for c in configs:
        rs = [r for r in runs if r.configuration == c]
        first = Counter(r.first_source for r in rs if r.first_source)
        print("{:<14}{:>5}  {:<22}{:>9}{:>9}{:>9}{:>9}".format(
            c[:13], len(rs),
            ", ".join("{} {}".format(k, v) for k, v in first.most_common()),
            mean_of([r.first_radar for r in rs]),
            mean_of([r.first_rf for r in rs]),
            mean_of([r.first_acoustic for r in rs]),
            mean_of([r.first_eo for r in rs])))
    print()


def print_veto(runs: List[VetoRun]) -> None:
    w = 104
    print("=" * w)
    print("SAFETY BOARD RUNS: {}   clean: {}".format(
        len(runs), sum(r.clean for r in runs)))
    print("=" * w)
    print("{:<14}{:<17}{:>6}{:>7}{:>7}{:>8}{:>8}{:>7}{:>11}{:>10}".format(
        "config", "run", "clean", "dur", "clock", "digital", "lag ms",
        "hazard", "measurable", "react ms"))
    for r in runs:
        react = "n/a" if r.reaction_status_ms is None else "{:.0f}/{}".format(
            r.reaction_status_ms, "n/a" if r.reaction_cmd_ms is None
            else "{:.0f}".format(r.reaction_cmd_ms))
        print("{:<14}{:<17}{}{}{:>7}{:>8}{}{}{}{:>10}".format(
            r.configuration[:13], r.run[:16], fmt(r.clean, 6),
            fmt(r.duration_s, 7, 1),
            "n/r" if r.clock_messages is None else str(r.clock_messages),
            "n/r" if r.digital_messages is None else str(r.digital_messages),
            fmt(r.stamp_lag_ms, 8, 1), fmt(r.onsets, 7),
            fmt(r.measurable, 11), react))
        print("    rates (Hz): {}".format(r.rates_hz))
        print("    stamps: {}   out-of-bounds blocks: {}".format(
            r.stamp_clock or "n/a", r.blocks))
        if r.reactions:
            print("    reactions (status/command): {}".format(r.reactions))
        if r.other_topics:
            print("    other topics: {}".format(r.other_topics))
    print("  clock, digital  messages on /clock and on digital-layer topics "
          "(n/r: not in the recording)")
    print("  lag ms   receive time - sensor stamp, median")
    print("  hazard   out-of-bounds blocks found; measurable: those that "
          "began while the board was safe")
    print("  react    median reaction, ms: first unsafe /safety_status / "
          "first zero /actuator_cmd_safe")
    print()


def print_findings(chain: List[ChainRun], veto: List[VetoRun]) -> None:
    runs = list(chain) + list(veto)
    bad = [r for r in runs if not r.clean]
    print("PROBLEMS (the run is not clean)")
    if not bad:
        print("  none")
    for r in bad:
        print("  {} {}: {}".format(r.configuration, r.run, r.problems))
    noted = [r for r in runs if r.notes]
    if noted:
        print("NOTES")
        for r in noted:
            print("  {} {}: {}".format(r.configuration, r.run, r.notes))


def write_csv(rows: list, cls, path: str) -> None:
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    names = [f.name for f in fields(cls)]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(names)
        for r in rows:
            out = []
            for n in names:
                v = getattr(r, n)
                out.append("" if v is None else
                           ("{:.6f}".format(v) if isinstance(v, float) else v))
            w.writerow(out)
    print("per-run CSV written to {}".format(path))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check that recorded runs are clean (read-only).")
    ap.add_argument("bags", nargs="+", help="bag directories")
    ap.add_argument("--csv", default=None,
                    help="write the pipeline runs here, and the Safety Board "
                         "runs next to it with a _veto suffix")
    args = ap.parse_args()

    chain: List[ChainRun] = []
    veto: List[VetoRun] = []
    print("[audit] reading {} folder(s) ...".format(len(args.bags)),
          file=sys.stderr)
    for bag in sorted(args.bags, key=identity):
        if not os.path.isfile(os.path.join(bag, "metadata.yaml")):
            print("[audit] skipping {}: not a bag directory".format(bag),
                  file=sys.stderr)
            continue
        try:
            data = read_run(bag)
            if data.get("obs"):
                chain.append(audit_chain(data))
            elif data.get("status"):
                veto.append(audit_veto(data))
            else:
                print("[audit] skipping {}: neither observation tokens nor "
                      "/safety_status".format(bag), file=sys.stderr)
        except Exception as e:  # report and go on with the other bags
            print("[audit] {}: failed ({})".format(bag, e), file=sys.stderr)
    if not chain and not veto:
        print("no readable bags", file=sys.stderr)
        return 1
    if chain:
        print_chain(chain)
    if veto:
        print_veto(veto)
    print_findings(chain, veto)
    if args.csv:
        print()
        if chain:
            write_csv(chain, ChainRun, args.csv)
        if veto:
            root, ext = os.path.splitext(args.csv)
            write_csv(veto, VetoRun, root + "_veto" + (ext or ".csv"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
