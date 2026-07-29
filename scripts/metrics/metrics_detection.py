#!/usr/bin/env python3
# Copyright 2026 Luca D'Aurizio
# Licensed under the Apache License, Version 2.0 (the "License").
"""Group 4a metrics: detection latency and modality richness by attack vector.

The IET paper (Section 2) notes that sensing modalities have "distinct profiles
of latency, reliability and ambiguity", and that the coordination layer must
fuse them under partial and evolving information. It does not quantify how the
detection depends on the geometry of the intruder's ingress -- that is deferred
to future work, which this thesis supplies.

This module measures, offline from a bag recorded by record_run.sh with a given
ATTACK_VECTOR, how the sensing chain responds to one ingress geometry:

  - modality richness : which of the four modalities (radar, rf, acoustic, eo)
                        detected the intruder at all, and how many observations
                        each produced. This is what discriminates the vectors:
                        a well-covered front is seen by three or four modalities,
                        a sparse flank by fewer.
  - first-detection latency per modality : time from the intruder becoming
                        active (first ground-truth sample) to that modality's
                        first observation. A modality that never fires has no
                        latency and is reported as "not detected".
  - chain latency : time from intruder-active to the first CandidateTarget
                        (radar+rf fused) and to the first ConfirmedThreat
                        (candidate + EO confirmation). Whether the threat forms
                        at all, and how late, is the headline number.

All times use the message `t` field (sim time), consistent with the other
metric modules.

Usage:
    python3 scripts/metrics/metrics_detection.py bags/frontal-YYYYMMDD-HHMMSS
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics_chain import read_bag, resolve_bag, stamp_to_s  # noqa: E402


MODALITIES = ["radar", "rf", "acoustic", "eo"]


def analyse(bag_path):
    bag = read_bag(bag_path)
    name = os.path.basename(bag_path.rstrip("/"))

    # Everything is measured in SIM TIME (the message `t` field), and anchored
    # to the earliest observation of ANY modality -- the first moment the
    # intruder was senseable. Anchoring in one clock domain avoids mixing bag
    # receive time (wall) with message time (sim).
    obs = bag.get("/obs_tokens", [])
    counts = {mod: 0 for mod in MODALITIES}
    first_t = {mod: None for mod in MODALITIES}
    all_obs_t = []
    for recv, m in obs:
        src = getattr(m, "source", None)
        if src in counts:
            ts = stamp_to_s(m.t)
            all_obs_t.append(ts)
            counts[src] += 1
            if first_t[src] is None or ts < first_t[src]:
                first_t[src] = ts

    if not all_obs_t:
        print(f"  no observations in {name}; nothing detected.")
        return
    sim_anchor = min(all_obs_t)

    # higher-level tokens, earliest sim-time each
    interp = bag.get("/interp_tokens", [])
    def first_label_t(label):
        best = None
        for recv, m in interp:
            if getattr(m, "label", None) == label:
                ts = stamp_to_s(m.t)
                # ignore tokens stamped before the first observation: those are
                # clock artefacts, not real chain formation.
                if ts < sim_anchor:
                    continue
                if best is None or ts < best:
                    best = ts
        return best

    t_candidate = first_label_t("CandidateTarget")
    t_confirmed = first_label_t("ConfirmedThreat")
    t_aerial = first_label_t("ConfirmedAerialObject")

    print("=" * 66)
    print("  Group 4a - detection by attack vector")
    print(f"  bag: {name}")
    print("=" * 66)

    detected = [m for m in MODALITIES if counts[m] > 0]
    print(f"  modality richness: {len(detected)}/4 modalities detected the intruder")
    for mod in MODALITIES:
        if counts[mod] > 0:
            print(f"    {mod:9s}: {counts[mod]:5d} observations")
        else:
            print(f"    {mod:9s}:    -- not detected")
    print("-" * 66)

    # Chain formation, as sim-time latency from the first observation. A single
    # robust number per token: whether it formed and how long after the target
    # first became senseable.
    print("  chain formation (latency from first detection):")
    def rel_or_none(t):
        if t is None:
            return None
        return t - sim_anchor
    for label, t in [("CandidateTarget", t_candidate),
                     ("ConfirmedAerialObject", t_aerial),
                     ("ConfirmedThreat", t_confirmed)]:
        r = rel_or_none(t)
        if r is not None and r >= 0:
            print(f"    {label:22s}: formed at +{r:6.2f}s")
        else:
            print(f"    {label:22s}: NOT formed")
    print("-" * 66)

    formed = t_confirmed is not None and (t_confirmed - sim_anchor) >= 0
    # The EO confirmation is the gate: without it T5 cannot promote the
    # candidate. Report it explicitly, since it is what distinguishes the
    # vectors (the EO cone is narrow and frontal).
    eo_seen = counts["eo"] > 0
    print(f"  outcome: threat {'CONFIRMED' if formed else 'NOT confirmed'} "
          f"| {len(detected)}/4 modalities | EO confirmation "
          f"{'present' if eo_seen else 'ABSENT (no T5 promotion)'}")
    print("=" * 66)


def main():
    ap = argparse.ArgumentParser(description="Group 4a detection-by-vector metrics")
    ap.add_argument("bag", help="path to a bag from record_run.sh (with ATTACK_VECTOR)")
    args = ap.parse_args()
    analyse(resolve_bag(args.bag))


if __name__ == "__main__":
    main()