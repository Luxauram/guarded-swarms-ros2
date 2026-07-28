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
# @file metrics_chain.py
#
# Offline chain-latency metrics for the Guarded Swarms coastal pipeline.
#
# Reads one recorded rosbag (see scripts/record_run.sh) and computes the
# latency metrics of Group 1: how long the TB-CSPN chain takes to turn a raw
# observation into an authorised, dispatched mission. These answer the
# quantitative questions the IET 2026 paper leaves to future work (Section 8):
# the paper establishes the chain ObsToken -> CandidateTarget -> ConfirmedThreat
# -> InterceptMission as an "auditable semantic backbone" but does not measure
# how fast it runs. This does.
#
# WHY SIM TIME, NOT BAG TIME
# --------------------------
# Every token carries an internal `t` field stamped with SIMULATED time (the
# nodes run with use_sim_time). The bag itself is recorded on receive/wall time
# because ros2 bag record --use-sim-time stalls at startup. All latencies here
# are therefore computed from the messages' `t` fields, never from bag receive
# timestamps: sim time is what makes runs comparable when the real-time factor
# is below 1.
#
# WHAT IT COMPUTES (Group 1)
#   1. End-to-end latency: first ObsToken for a target -> its InterceptMission.
#   2. Per-transition latency: the waterfall across the chain's labels
#      (first ObsToken -> first CandidateTarget -> first ConfirmedThreat ->
#       MissionToken -> first VehicleTask).
#   3. Authorisation -> dispatch latency: SupervisorAuth -> the mission it
#      released -> the tasks dispatched from it.
#
# USAGE
#   source install/setup.bash
#   python3 scripts/metrics/metrics_chain.py bags/coastal-YYYYMMDD-HHMMSS/
#   python3 scripts/metrics/metrics_chain.py bags/coastal-*/ --json out.json
#
# The result is printed as a table and optionally written as JSON for the
# dashboard and for aggregating across runs.
# =============================================================================

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

# --- ROS bag reading --------------------------------------------------------
# rosbag2_py and the message types come from the sourced ROS environment; no
# extra pip dependency is needed. Import errors here almost always mean the
# workspace was not sourced.
try:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
except ImportError as e:
    sys.stderr.write(
        "error: could not import the ROS 2 bag API ({}).\n"
        "Did you `source install/setup.bash` first?\n".format(e)
    )
    sys.exit(2)


# =============================================================================
# Time helpers
# =============================================================================
def stamp_to_s(stamp) -> float:
    """
    Convert a builtin_interfaces/Time (the token's `t` field) to float seconds.

    @param stamp  A message with .sec and .nanosec (simulated time).
    @return       Seconds as a float.
    """
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


# =============================================================================
# Bag reading
# =============================================================================
def read_bag(bag_dir: str) -> dict:
    """
    Read every message from a rosbag directory, grouped by topic.

    Messages are returned with BOTH their bag receive time (for reference) and
    the deserialized message object (whose `t` field carries sim time). Latency
    maths downstream uses the message `t`, not the receive time.

    @param bag_dir  Path to the bag directory (the one containing *.db3).
    @return         dict: topic name -> list of (recv_time_ns, msg), time-ordered.
    """
    storage = rosbag2_py.StorageOptions(uri=bag_dir, storage_id="sqlite3")
    converter = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    reader = rosbag2_py.SequentialReader()
    reader.open(storage, converter)

    # Map topic -> message class, from the bag's own type metadata.
    type_map = {t.name: t.type for t in reader.get_all_topics_and_types()}
    msg_classes = {}
    for name, typestr in type_map.items():
        try:
            msg_classes[name] = get_message(typestr)
        except (AttributeError, ModuleNotFoundError):
            # A type we cannot resolve (e.g. px4_msgs not sourced): skip it,
            # we only need the guarded_swarms_msgs topics here.
            msg_classes[name] = None

    out: dict = {name: [] for name in type_map}
    while reader.has_next():
        topic, data, recv_ns = reader.read_next()
        cls = msg_classes.get(topic)
        if cls is None:
            continue
        try:
            msg = deserialize_message(data, cls)
        except Exception:
            continue
        out[topic].append((recv_ns, msg))
    return out


# =============================================================================
# Result container
# =============================================================================
@dataclass
class ChainMetrics:
    """All Group-1 latency figures for one run, in seconds (sim time)."""

    bag: str = ""
    target_id: str = ""

    # Absolute sim-time instants of the first occurrence of each stage.
    t_first_obs: Optional[float] = None
    t_first_candidate: Optional[float] = None
    t_first_confirmed: Optional[float] = None
    t_first_mission: Optional[float] = None
    t_first_task: Optional[float] = None
    t_auth: Optional[float] = None

    # 1. End-to-end.
    end_to_end_s: Optional[float] = None

    # 2. Per-transition (waterfall) deltas.
    obs_to_candidate_s: Optional[float] = None
    candidate_to_confirmed_s: Optional[float] = None
    confirmed_to_mission_s: Optional[float] = None
    mission_to_task_s: Optional[float] = None

    # 3. Authorisation path.
    auth_to_mission_s: Optional[float] = None
    auth_to_task_s: Optional[float] = None

    # 4. The three phases the paper's human-in-the-loop design implies, kept
    #    apart so system speed is not conflated with human decision time.
    system_obs_to_confirmed_s: Optional[float] = None   # automatic
    human_wait_confirmed_to_auth_s: Optional[float] = None  # human
    post_auth_to_task_s: Optional[float] = None         # automatic

    # Bookkeeping.
    counts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


# =============================================================================
# Metric computation
# =============================================================================
def earliest_by_label(msgs, label: str, target: str) -> Optional[float]:
    """
    Sim-time `t` of the earliest InterpToken with a given label for a target.

    @param msgs    List of (recv_ns, InterpToken) for /interp_tokens.
    @param label   The LABEL_* string to match.
    @param target  target_id to match.
    @return        Earliest sim-time in seconds, or None if never seen.
    """
    best = None
    for _, m in msgs:
        if m.target_id != target or m.label != label:
            continue
        t = stamp_to_s(m.t)
        if best is None or t < best:
            best = t
    return best


def pick_target(data: dict) -> Optional[str]:
    """
    Choose the target to analyse: the one with the most observations.

    A run normally has a single intruder, but selecting the busiest target_id
    keeps the script correct if several appear.

    @param data  The read_bag() output.
    @return      A target_id string, or None if there are no observations.
    """
    counts: dict = {}
    for _, m in data.get("/obs_tokens", []):
        tid = getattr(m, "target_id", "")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def compute(data: dict, bag_dir: str) -> ChainMetrics:
    """
    Compute all Group-1 metrics from a read bag.

    @param data     read_bag() output.
    @param bag_dir  bag path, stored in the result for reference.
    @return         A populated ChainMetrics.
    """
    r = ChainMetrics(bag=os.path.basename(os.path.normpath(bag_dir)))

    obs = data.get("/obs_tokens", [])
    interp = data.get("/interp_tokens", [])
    missions = data.get("/mission_tokens", [])
    tasks = data.get("/vehicle_tasks", [])
    auths = data.get("/supervisor_auth", [])

    r.counts = {
        "obs_tokens": len(obs),
        "interp_tokens": len(interp),
        "mission_tokens": len(missions),
        "vehicle_tasks": len(tasks),
        "supervisor_auth": len(auths),
    }

    target = pick_target(data)
    if target is None:
        r.notes.append("no observations with a target_id; nothing to measure")
        return r
    r.target_id = target

    # Estimate the offset between the bag receive clock (wall time on the
    # recording host) and the sim-time carried in token `t` fields. Tokens have
    # both: recv_ns from the bag and a valid sim `t`. The median of (sim - recv)
    # lets us place the auth -- which lacks a sim stamp -- on the sim axis.
    offsets = []
    for recv_ns, m in interp:
        st = stamp_to_s(m.t)
        if st > 0.0:
            offsets.append(st - recv_ns * 1e-9)
    for recv_ns, m in obs:
        st = stamp_to_s(m.t)
        if st > 0.0:
            offsets.append(st - recv_ns * 1e-9)
    clock_offset = None
    if offsets:
        offsets.sort()
        clock_offset = offsets[len(offsets) // 2]  # median

    # --- first ObsToken for the target ---
    obs_times = [stamp_to_s(m.t) for _, m in obs if m.target_id == target]
    r.t_first_obs = min(obs_times) if obs_times else None

    # --- first of each interpretation stage ---
    # CandidateTarget and ConfirmedThreat follow Figure 4's naming.
    r.t_first_candidate = earliest_by_label(interp, "CandidateTarget", target)
    r.t_first_confirmed = earliest_by_label(interp, "ConfirmedThreat", target)

    # --- first mission for the target ---
    mission_times = [stamp_to_s(m.t) for _, m in missions if m.target_id == target]
    r.t_first_mission = min(mission_times) if mission_times else None

    # --- first task for the target ---
    task_times = [stamp_to_s(m.t) for _, m in tasks if m.target_id == target]
    r.t_first_task = min(task_times) if task_times else None

    # --- authorisation instant (first authorise decision for the target) ---
    # The authorisation is published from the command line / console, which
    # does NOT stamp the message `t` field (it stays 0). So unlike the tokens,
    # the auth has no valid sim-time of its own. We therefore take the auth's
    # BAG RECEIVE time and convert it into the sim-time frame using the offset
    # between the two clocks measured on the tokens (see clock_offset below).
    # This keeps the auth-path latencies on the same sim-time axis as the rest.
    auth_recv_ns = None
    for recv_ns, m in auths:
        if getattr(m, "target_id", "") != target:
            continue
        if getattr(m, "decision", "") not in ("authorise", "authorize", ""):
            continue
        if auth_recv_ns is None or recv_ns < auth_recv_ns:
            auth_recv_ns = recv_ns
    r.t_auth = None
    if auth_recv_ns is not None and clock_offset is not None:
        # sim_time = recv_wall_time + offset
        r.t_auth = auth_recv_ns * 1e-9 + clock_offset

    # --- 1. end-to-end ---
    if r.t_first_obs is not None and r.t_first_mission is not None:
        r.end_to_end_s = r.t_first_mission - r.t_first_obs

    # --- 2. per-transition waterfall ---
    if r.t_first_obs is not None and r.t_first_candidate is not None:
        r.obs_to_candidate_s = r.t_first_candidate - r.t_first_obs
    if r.t_first_candidate is not None and r.t_first_confirmed is not None:
        r.candidate_to_confirmed_s = r.t_first_confirmed - r.t_first_candidate
    if r.t_first_confirmed is not None and r.t_first_mission is not None:
        r.confirmed_to_mission_s = r.t_first_mission - r.t_first_confirmed
    if r.t_first_mission is not None and r.t_first_task is not None:
        r.mission_to_task_s = r.t_first_task - r.t_first_mission

    # --- 3. authorisation path ---
    if r.t_auth is not None and r.t_first_mission is not None:
        r.auth_to_mission_s = r.t_first_mission - r.t_auth
    if r.t_auth is not None and r.t_first_task is not None:
        r.auth_to_task_s = r.t_first_task - r.t_auth

    # --- 4. the three phases, kept apart ---
    # System (automatic): raw observation to a confirmed threat.
    if r.t_first_obs is not None and r.t_first_confirmed is not None:
        r.system_obs_to_confirmed_s = r.t_first_confirmed - r.t_first_obs
    # Human: from a confirmed threat being available to the supervisor acting.
    if r.t_first_confirmed is not None and r.t_auth is not None:
        r.human_wait_confirmed_to_auth_s = r.t_auth - r.t_first_confirmed
    # System (automatic): authorisation to a dispatched task.
    if r.t_auth is not None and r.t_first_task is not None:
        r.post_auth_to_task_s = r.t_first_task - r.t_auth

    # The authorisation instant is projected from bag-receive time onto the sim
    # axis via a median clock offset, so it carries a small projection error
    # (clock jitter). That can make a near-zero auth-path latency come out
    # slightly negative. A negative here is not a real time-travel: it means the
    # latency is below the projection's resolution. Clamp such small negatives
    # to zero and record it, rather than print a misleading negative number.
    for attr in ("auth_to_mission_s", "auth_to_task_s", "post_auth_to_task_s"):
        v = getattr(r, attr)
        if v is not None and -1.0 < v < 0.0:
            setattr(r, attr, 0.0)
    if r.auth_to_task_s == 0.0:
        r.notes.append(
            "auth-path latency clamped to 0 (below the clock-projection "
            "resolution): dispatch after authorisation is effectively "
            "instantaneous"
        )

    # --- sanity notes ---
    if r.t_auth is not None and r.t_first_confirmed is not None \
            and r.t_auth < r.t_first_confirmed:
        r.notes.append(
            "authorisation precedes the first ConfirmedThreat; the release "
            "waited for the threat, so confirmed->mission includes that wait"
        )
    if len(missions) > 1:
        r.notes.append(
            "multiple mission tokens ({}) for one authorisation: the auth was "
            "published repeatedly; first-of-each is used, so latencies are "
            "unaffected".format(len(missions))
        )
    if r.confirmed_to_mission_s is not None and r.confirmed_to_mission_s < 0:
        r.notes.append(
            "confirmed->mission is negative: a mission predates the first "
            "ConfirmedThreat for this target (check target attribution)"
        )

    return r


# =============================================================================
# Reporting
# =============================================================================
def fmt(v: Optional[float]) -> str:
    """Format a latency in seconds, or a dash when it could not be computed."""
    return "     n/a" if v is None else "{:8.3f}".format(v)


def print_report(r: ChainMetrics):
    """Print a human-readable table of the metrics for one run."""
    print()
    print("=" * 64)
    print("  Chain-latency metrics (Group 1)   [sim time, seconds]")
    print("  bag:    {}".format(r.bag))
    print("  target: {}".format(r.target_id or "(none)"))
    print("=" * 64)

    print("  message counts:")
    for k, v in r.counts.items():
        print("    {:18s} {}".format(k, v))
    print("-" * 64)

    print("  1. end-to-end")
    print("     first ObsToken -> InterceptMission        {}".format(
        fmt(r.end_to_end_s)))
    print()
    print("  2. per-transition (waterfall)")
    print("     ObsToken     -> CandidateTarget           {}".format(
        fmt(r.obs_to_candidate_s)))
    print("     CandidateTgt -> ConfirmedThreat           {}".format(
        fmt(r.candidate_to_confirmed_s)))
    print("     ConfirmedThr -> InterceptMission          {}".format(
        fmt(r.confirmed_to_mission_s)))
    print("     Mission      -> VehicleTask               {}".format(
        fmt(r.mission_to_task_s)))
    print()
    print("  3. authorisation path (auth stamped on bag-receive time)")
    print("     SupervisorAuth -> InterceptMission        {}".format(
        fmt(r.auth_to_mission_s)))
    print("     SupervisorAuth -> VehicleTask             {}".format(
        fmt(r.auth_to_task_s)))
    print()
    print("  4. the loop, in three phases")
    print("     [system] ObsToken -> ConfirmedThreat      {}".format(
        fmt(r.system_obs_to_confirmed_s)))
    print("     [human]  ConfirmedThreat -> authorisation {}".format(
        fmt(r.human_wait_confirmed_to_auth_s)))
    print("     [system] authorisation -> VehicleTask     {}".format(
        fmt(r.post_auth_to_task_s)))
    print("     the middle line is human decision time, not system latency")

    if r.notes:
        print("-" * 64)
        print("  notes:")
        for n in r.notes:
            print("    - {}".format(n))
    print("=" * 64)
    print()


# =============================================================================
# Entry point
# =============================================================================
def resolve_bag(path: str) -> str:
    """
    Resolve a bag path that may be a glob or a directory.

    @param path  A directory, or a glob like bags/coastal-*/.
    @return      A concrete bag directory (the most recent match for a glob).
    """
    if os.path.isdir(path) and glob.glob(os.path.join(path, "*.db3")):
        return path
    matches = sorted(glob.glob(path))
    matches = [m for m in matches if glob.glob(os.path.join(m, "*.db3"))]
    if not matches:
        sys.stderr.write("error: no bag with a .db3 found at: {}\n".format(path))
        sys.exit(1)
    return matches[-1]  # most recent by name (timestamped)


def main():
    ap = argparse.ArgumentParser(
        description="Offline chain-latency metrics (Group 1) for a Guarded "
                    "Swarms coastal run.")
    ap.add_argument("bag", help="bag directory or glob (e.g. bags/coastal-*/)")
    ap.add_argument("--json", help="also write the metrics as JSON to this path")
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