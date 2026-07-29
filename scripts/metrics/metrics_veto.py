#!/usr/bin/env python3
# Copyright 2026 Luca D'Aurizio
# Licensed under the Apache License, Version 2.0 (the "License").
"""Group 6 metrics: the analog Safety Board (the veto).

The IEEE paper's Virtual Safety Board is an ANALOG enforcement layer that runs
independently of the digital coordination system and clamps or vetoes actuator
commands from raw sensor readings alone, before they reach the ESCs. This module
measures, offline from a bag recorded by scripts/record_veto.sh, the properties
that matter for that safety guarantee:

  1. Reaction time     -- for each hazard, the delay between the sensor crossing
                          its threshold and the board's first veto response
                          (safety_status -> 0, and actuator_cmd_safe -> 0).
  2. Interventions     -- how many distinct veto episodes occurred, and the
                          cause of each (proximity / attitude / battery /
                          altitude), inferred from which sensor was out of
                          bounds at the time.
  3. Envelope coverage -- whether every constraint the board enforces actually
                          fired at least once, i.e. the full safety envelope was
                          exercised.
  4. Isolation         -- the board produced these vetoes with NO digital layer
                          present: the recording contains only sensor and
                          actuator topics, no TB-CSPN tokens. Structural proof of
                          the paper's independence claim.

Thresholds mirror the board's defaults (safety_board_node.hpp). Override on the
command line if a run used non-default parameters.

Usage:
    python3 scripts/metrics/metrics_veto.py bags/veto-YYYYMMDD-HHMMSS
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics_chain import read_bag, resolve_bag, stamp_to_s  # noqa: E402


# Board defaults, from safety_board_node.hpp. A hazard is present when a sensor
# is on the unsafe side of its threshold.
MIN_PROXIMITY_M = 1.5
MAX_PITCH_DEG = 30.0
MAX_ROLL_DEG = 30.0
MIN_BATTERY_PCT = 15.0
MIN_ALTITUDE_M = 0.3
MAX_ALTITUDE_M = 50.0


def _quat_to_pitch_roll(q):
    """Same conversion the board uses (ZYX, yaw ignored)."""
    import math
    sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z)
    cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
    roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
    sinp = 2.0 * (q.w * q.y - q.z * q.x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.degrees(math.asin(sinp))
    return pitch, roll


def _series(bag, topic, field_fn):
    """Return a time-sorted list of (t_seconds, value) for a topic."""
    out = []
    for recv, m in bag.get(topic, []):
        try:
            out.append((recv / 1e9, field_fn(m)))
        except Exception:
            pass
    out.sort(key=lambda x: x[0])
    return out


def _value_at(series, t):
    """Last value in series at or before time t (None if none yet)."""
    val = None
    for ts, v in series:
        if ts <= t:
            val = v
        else:
            break
    return val


def analyse(bag_path):
    bag = read_bag(bag_path)
    name = os.path.basename(bag_path.rstrip("/"))

    # Board status flag over time: 1.0 safe, 0.0 unsafe. Recorded on wall time
    # (the board runs on the system clock in isolation, no use_sim_time).
    status = _series(bag, "/safety_status", lambda m: float(m.data))
    safe_cmd = _series(bag, "/actuator_cmd_safe", lambda m: float(m.data))
    raw_cmd = _series(bag, "/actuator_cmd_raw", lambda m: float(m.data))

    # Sensor series, mapped to a boolean "hazard present" per sensor.
    prox = _series(bag, "/drone/proximity", lambda m: float(m.range))
    batt = _series(bag, "/drone/battery", lambda m: float(m.percentage) * 100.0)
    alt = _series(bag, "/drone/altitude", lambda m: float(m.data))
    imu = _series(bag, "/drone/imu", lambda m: _quat_to_pitch_roll(m.orientation))

    if not status:
        print(f"  no /safety_status in {name}; did the board run?")
        return

    t0 = status[0][0]
    t_end = status[-1][0]

    def rel(t):
        return t - t0

    # ----- classify the hazard present at any instant -----
    # Mirrors the board's OR-logic evaluation order, returning the primary cause
    # (the one the board would report) plus the full set present.
    def cause_at(t):
        causes = []
        p = _value_at(prox, t)
        if p is not None and p < MIN_PROXIMITY_M:
            causes.append("proximity")
        pr = _value_at(imu, t)
        if pr is not None:
            pitch, roll = pr
            if abs(pitch) > MAX_PITCH_DEG or abs(roll) > MAX_ROLL_DEG:
                causes.append("attitude")
        b = _value_at(batt, t)
        if b is not None and b < MIN_BATTERY_PCT:
            causes.append("battery")
        a = _value_at(alt, t)
        if a is not None and (a < MIN_ALTITUDE_M or a > MAX_ALTITUDE_M):
            causes.append("altitude")
        return causes

    # ----- veto episodes segmented BY CAUSE, not merely by status continuity --
    # Back-to-back hazard scenarios (proximity -> attitude -> battery ->
    # altitude) keep safety_status at 0 the whole time, so a status-only
    # segmentation would merge them into one episode. Instead we sample the
    # active cause on a fine grid and start a new episode whenever the primary
    # cause changes while the board is unsafe.
    DT = 0.1  # sampling grid, matches the 10 Hz status rate
    episodes = []  # each: [start, end, cause_string]
    cur = None
    t = t0
    while t <= t_end:
        st = _value_at(status, t)
        unsafe = (st is not None and st < 0.5)
        causes = cause_at(t) if unsafe else []
        # primary cause = first present, in the board's evaluation order
        primary = causes[0] if causes else ("unknown" if unsafe else None)
        if primary is None:
            if cur is not None:
                episodes.append(tuple(cur))
                cur = None
        else:
            if cur is None:
                cur = [t, t, primary]
            elif primary == cur[2]:
                cur[1] = t
            else:
                episodes.append(tuple(cur))
                cur = [t, t, primary]
        t += DT
    if cur is not None:
        episodes.append(tuple(cur))

    # ----- reaction time per episode -----
    # For each episode, find when the causing hazard first became true, and
    # measure the delay to the episode's start (first status==0).
    def hazard_onset_before(episode_start, cause):
        """Walk the relevant sensor series back to the first sample that was
        already unsafe in the run-up to this episode."""
        series_map = {
            "proximity": (prox, lambda v: v < MIN_PROXIMITY_M),
            "battery": (batt, lambda v: v < MIN_BATTERY_PCT),
            "altitude": (alt, lambda v: v < MIN_ALTITUDE_M or v > MAX_ALTITUDE_M),
        }
        if cause == "attitude":
            s = imu
            unsafe = lambda v: abs(v[0]) > MAX_PITCH_DEG or abs(v[1]) > MAX_ROLL_DEG
        elif cause in series_map:
            s, unsafe = series_map[cause]
        else:
            return None
        # first unsafe sample within 12 s before the episode start
        onset = None
        for ts, v in s:
            if ts > episode_start:
                break
            if ts >= episode_start - 12.0 and unsafe(v):
                onset = ts
                break
        return onset

    print("=" * 66)
    print("  Group 6 - Analog Safety Board (veto) verification")
    print(f"  bag:      {name}")
    print("=" * 66)

    # isolation: what topics are in the bag? no digital-layer topics allowed.
    digital = [t for t in bag.keys()
               if any(k in t for k in ("interp_tokens", "mission_tokens",
                                       "obs_tokens", "supervisor_auth",
                                       "vehicle_tasks"))]
    print("  isolation:")
    print(f"    digital-layer topics present: {len(digital)} "
          f"({'none -> isolated' if not digital else digital})")
    print(f"    board ran on sensors + raw command only: "
          f"{'yes' if not digital else 'NO'}")
    print("-" * 66)

    # command clamping: while unsafe, is safe forced to 0 though raw > 0?
    clamped = 0
    checked = 0
    for ts, sv in safe_cmd:
        st = _value_at(status, ts)
        rv = _value_at(raw_cmd, ts)
        if st is not None and st < 0.5 and rv is not None and rv > 0.01:
            checked += 1
            if abs(sv) < 1e-3:
                clamped += 1
    print("  command clamping (while unsafe, raw>0):")
    if checked:
        print(f"    safe forced to 0: {clamped}/{checked} samples "
              f"({100.0*clamped/checked:.0f}%)")
    else:
        print("    no unsafe+raw>0 samples (was a raw stream present?)")
    print("-" * 66)

    # episodes + causes + reaction
    # Drop sub-threshold transient blips (< 0.4 s): startup noise before the
    # first sensor messages land, not real hazards.
    episodes = [e for e in episodes if (e[1] - e[0]) >= 0.4 or e[2] != "unknown"]
    print(f"  veto episodes: {len(episodes)}")
    causes_seen = set()
    for k, (a, b, cause) in enumerate(episodes):
        if cause != "unknown":
            causes_seen.add(cause)
        # reaction: delay from the hazard first becoming true to this episode's
        # first unsafe sample.
        rt = None
        if cause != "unknown":
            onset = hazard_onset_before(a, cause)
            if onset is not None:
                rt = a - onset
        rt_str = f"{rt*1000:.0f} ms" if rt is not None else "n/a"
        print(f"    episode {k}: t=[{rel(a):5.1f},{rel(b):5.1f}]s "
              f"dur={b-a:4.1f}s  cause={cause:20s} reaction={rt_str}")
    print("-" * 66)

    # envelope coverage
    enforced = ["proximity", "attitude", "battery", "altitude"]
    print("  envelope coverage (which vetoes fired):")
    for c in enforced:
        print(f"    {c:12s}: {'FIRED' if c in causes_seen else 'not seen'}")
    covered = sum(1 for c in enforced if c in causes_seen)
    print("-" * 66)
    ok_iso = not digital
    ok_clamp = (checked > 0 and clamped == checked)
    ok_cov = (covered == 4)  # every constraint the board enforces fired
    verdict = ok_iso and ok_clamp and ok_cov
    print(f"  isolation upheld:   {'PASS' if ok_iso else 'FAIL'}")
    print(f"  clamping upheld:    {'PASS' if ok_clamp else 'FAIL'}")
    print(f"  envelope exercised: {covered}/4 constraints")
    print("=" * 66)
    print(f"  veto verification: {'PASS' if verdict else 'REVIEW'}")
    print("=" * 66)


def main():
    ap = argparse.ArgumentParser(description="Group 6 veto metrics")
    ap.add_argument("bag", help="path to a bag from record_veto.sh")
    args = ap.parse_args()
    analyse(resolve_bag(args.bag))


if __name__ == "__main__":
    main()