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
analyze_campaign.py - the tables of a campaign of recorded runs.

Read-only: it reads the manifest and the bags of a campaign recorded by
scripts/experiments/run_campaign.sh, and writes tables and CSV files.

For every run of every configuration it takes the valid attempts of the
manifest and checks that their recording is clean: the checks of
audit_recordings.py, plus three that every run of the current code must
pass:
  - each interpretation stream has one producer: the counter at the end of
    the interpretation ids never goes back;
  - the intruder runs in simulated time: its ground-truth stamps are in
    simulated time, and its speed in simulated time is the commanded one
    (INTRUDER_SPEED_MPS, within SPEED_TOLERANCE_MPS);
  - at most one supervisor decision for the target.
A configuration that sets T3_WINDOW_S in configurations.conf adds a fourth:
T3 ran with that window, as it logged it at start-up (logs/gs_tbcspn.log next
to the bag).
The first valid attempt that is clean is used. A run with no clean attempt is
left out of the tables and listed with the reasons.

Several campaign folders can be given. An attempt in a later folder with the
configuration and seed of a run of an earlier folder is one more attempt of
that run: this is how a run is repeated after its valid attempt turned out
not to be clean. The attempts set aside are listed.

Every time comes from the token stamps, in simulated time. Binary outcomes
are given with their 95% Wilson score interval. A ConfirmedThreat is valid
from its stamp for its ttl_s, and so is an authorisation: T6 releases a
mission when the two are valid at the same time. The threat window of a run
is made of the spans in which a ConfirmedThreat was valid, and tells whether
the authorisation, while valid, met one.

The EO evidence of the threat is measured in the runs in which UAV0, which
carries the EO camera, stays at its post (no UAV task, or the first one to
another UAV), so that the camera sees the whole pass of the target: the EO
pass, from the first EO confirmation (ConfirmedAerialObject) to the last; the
last ConfirmedThreat after the last EO confirmation, and the age of the EO
confirmation that T5 fused into it; the CandidateTargets per second during
the EO pass.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/analyze_campaign.py bags/campaigns/<campaign> \\
        [bags/campaigns/<repeats> ...] [--out results/<campaign>]

Output, in --out (default results/<first campaign>):
    tables.md       the tables, also printed
    runs.csv        one line per run: identity, checks, counts and times
    outcomes.csv    binary outcomes per configuration, with the intervals
    latencies.csv   time statistics per configuration

@author Luca D'Aurizio
"""

import argparse
import csv
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, fields
from typing import Callable, Dict, List, Optional, Tuple

from audit_recordings import (EXPECTED, OUTCOMES, ChainRun, audit_chain,
                              by_label, clock_of, first_stamp, read_run)
from audit_timing import AUTHORISE, SOURCES, describe, diff, stamp_s

INTRUDER_SPEED_MPS = 6.0    # commanded intruder speed
SPEED_TOLERANCE_MPS = 0.1   # allowed gap from it, in simulated time
LOW_RTF = 0.9               # a lower real-time factor is noted
Z95 = 1.959963984540054     # two-sided 95% normal quantile
EO_CARRIER = 1              # system id of UAV0, which carries the EO camera
UGV_SYSTEM = 3              # system id of the UGV

# The line T3 logs at start-up with its synchronisation window (one decimal),
# in the log of the coordination layer that the campaign keeps with the bag.
T3_LOG = "gs_tbcspn.log"
T3_WINDOW_LINE = re.compile(
    r"\[t3_candidate\]:\s+sync threshold ths:\s*([0-9]+(?:\.[0-9]+)?)\s*s")
ANSI_CODE = re.compile(r"\x1b\[[0-9;]*m")

OUTCOME_LABELS = {
    "mission": "mission",
    "no-mission": "threat, no mission",
    "stale-eo": "late EO, no threat",
    "civilian": "civilian RF, no candidate",
    "cand-only": "candidate, no threat",
    "no-cand": "no candidate",
    "no-eo": "candidate, no EO, no threat",
}
MODALITY_LABELS = {"radar": "Radar", "rf": "RF", "acoustic": "Acoustic",
                   "eo": "EO"}


# =============================================================================
# Campaign files
# =============================================================================
@dataclass
class Attempt:
    """One line of manifest.csv, and the campaign folder it comes from."""
    configuration: str
    run: int
    attempt: int
    seed: int
    commit: str
    outcome: str
    valid: bool
    folder: str
    campaign_dir: str = ""

    @property
    def campaign(self) -> str:
        return os.path.basename(self.campaign_dir)


def read_manifest(path: str, campaign_dir: str) -> List[Attempt]:
    """Every attempt of a campaign, in the order of its manifest."""
    out = []
    with open(path, newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            try:
                out.append(Attempt(
                    configuration=row["configuration"], run=int(row["run"]),
                    attempt=int(row["attempt"]), seed=int(row["seed"]),
                    commit=row["commit"], outcome=row["outcome"],
                    valid=row["valid"] == "yes", folder=row["folder"],
                    campaign_dir=campaign_dir))
            except (KeyError, TypeError, ValueError):
                sys.exit("{}: line {} is not a manifest line".format(path, n))
    return out


def read_env(path: str) -> Dict[str, str]:
    """KEY=value lines of campaign.env (empty if missing)."""
    env: Dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    env[k] = v
    except OSError:
        pass
    return env


def configuration_vars(path: str) -> Dict[str, Dict[str, str]]:
    """Variables of each configuration of configurations.conf (empty if the
    file is missing)."""
    out: Dict[str, Dict[str, str]] = {}
    try:
        with open(path) as f:
            for line in f:
                tokens = line.split("#", 1)[0].split()
                if tokens:
                    out[tokens[0]] = dict(t.split("=", 1) for t in tokens[1:]
                                          if "=" in t)
    except OSError:
        pass
    return out


def configuration_order(path: str) -> List[str]:
    """Configuration names in the order of configurations.conf."""
    names: List[str] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    names.append(line.split()[0])
    except OSError:
        pass
    return names


def bag_of(a: Attempt) -> str:
    """Bag folder of an attempt, under the campaign folder given."""
    return os.path.join(a.campaign_dir, a.configuration,
                        os.path.basename(os.path.normpath(a.folder)), "bag")


# =============================================================================
# One run
# =============================================================================
@dataclass
class RunResult:
    """A run: the attempt used, its audit, and the times the audit leaves
    out. run is the run number in the first campaign."""
    attempt: Attempt
    run: int = 0
    audit: Optional[ChainRun] = None
    clean: bool = False
    problems: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    threat_to_decision: Optional[float] = None
    decision_to_mission: Optional[float] = None
    mission_to_task: Optional[float] = None
    modalities: int = 0
    # The threat window: from the first ConfirmedThreat to the last, and to
    # the end of the first span in which one was valid; the number of spans;
    # whether the authorisation, while valid, met a valid threat.
    threat_confirmed_for: Optional[float] = None
    threat_valid_for: Optional[float] = None
    threat_spans: int = 0
    auth_meets_threat: Optional[bool] = None
    t3_window: Optional[float] = None    # as T3 logged it, s
    # The EO evidence of the threat: whether UAV0 stayed at its post; the EO
    # pass; the last ConfirmedThreat after the last EO confirmation, and the
    # age of the EO confirmation in it; CandidateTargets per s in the pass.
    eo_at_post: Optional[bool] = None
    eo_pass: Optional[float] = None
    eo_tail: Optional[float] = None
    eo_age: Optional[float] = None
    candidates_per_s: Optional[float] = None


def split(text: str) -> List[str]:
    return [p for p in text.split("; ") if p]


def valid_spans(intervals: List[Tuple[float, float]]
                ) -> List[Tuple[float, float]]:
    """The union of (start, end) intervals, as disjoint spans in time order."""
    spans: List[List[float]] = []
    for s, e in sorted(intervals):
        if spans and s <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    return [(s, e) for s, e in spans]


def t3_window_of(log_path: str) -> Optional[float]:
    """The window T3 logged at start-up, in seconds, or None if not found."""
    try:
        with open(log_path, errors="replace") as f:
            for line in f:
                m = T3_WINDOW_LINE.search(ANSI_CODE.sub("", line))
                if m:
                    return float(m.group(1))
    except OSError:
        pass
    return None


def analyze_run(a: Attempt, commit: str,
                t3_window: Optional[float] = None) -> RunResult:
    """Read, audit and time one valid attempt of a run. t3_window is the
    T3_WINDOW_S of its configuration, if it sets one."""
    res = RunResult(attempt=a, run=a.run)
    bag = bag_of(a)
    if not os.path.isfile(os.path.join(bag, "metadata.yaml")):
        res.problems.append("bag not found: {}".format(bag))
        return res
    try:
        data = read_run(bag)
    except Exception as e:  # report and go on with the other runs
        res.problems.append("bag not readable ({})".format(e))
        return res
    if not data.get("obs"):
        tokens = sum(len(data.get(k)) for k in
                     ("obs", "interp", "mission", "task", "auth"))
        if not data.get("clock"):
            res.problems.append(
                "no /clock message in the bag: the simulated time did not "
                "reach the run, and no node of the chain published (ground "
                "truth {}, tokens {})".format(len(data.get("gt")), tokens))
        else:
            res.problems.append(
                "no observation tokens in the bag (/clock {}, ground truth "
                "{})".format(len(data.get("clock")), len(data.get("gt"))))
        return res
    r = audit_chain(data)
    res.audit = r
    res.problems = split(r.problems)
    res.notes = [n for n in split(r.notes)
                 if not n.startswith("interpretation counters went back")]

    # --- checks every run of the current code must pass --------------------------
    if r.interp_backsteps:
        res.problems.append(
            "interpretation counters went back ({}): more than one producer "
            "per transition".format(r.backstep_streams))
    if r.clock_backsteps is None:
        res.problems.append("no /clock: the simulated-time checks cannot be "
                            "made")
    if not r.gt_topic:
        res.problems.append("no intruder ground truth: the one-intruder "
                            "check cannot be made")
    elif r.gt_clock != "sim":
        res.problems.append("ground-truth stamps on the {} clock: the "
                            "intruder does not run in simulated "
                            "time".format(r.gt_clock or "unknown"))
    elif r.v_sim is None:
        if not r.gt_jumps:
            res.problems.append("intruder speed in simulated time not "
                                "measured")
    elif abs(r.v_sim - INTRUDER_SPEED_MPS) > SPEED_TOLERANCE_MPS:
        res.problems.append("intruder at {:.2f} m/s in simulated time, "
                            "commanded {:.1f}: mixed clocks".format(
                                r.v_sim, INTRUDER_SPEED_MPS))
    if r.authorise + r.deny > 1:
        res.problems.append("{} supervisor decisions for the target: more "
                            "than one supervisor".format(r.authorise + r.deny))
    if r.rtf is not None and r.rtf < LOW_RTF:
        res.notes.append("real-time factor {:.2f}".format(r.rtf))
    if commit and a.commit != commit:
        res.notes.append("commit {} (campaign started at {})".format(
            a.commit, commit))

    # --- times the audit leaves out ------------------------------------------------
    def mine(kind: str) -> list:
        return [(rx, m) for rx, m in data.get(kind)
                if m.target_id == r.target_id]

    t_threat = first_stamp(mine("interp"), by_label("ConfirmedThreat"))
    t_decision = first_stamp(mine("auth"))
    t_mission = first_stamp(mine("mission"))
    res.threat_to_decision = diff(t_threat, t_decision)
    res.decision_to_mission = diff(t_decision, t_mission)
    res.mission_to_task = diff(t_mission, first_stamp(mine("task")))
    res.modalities = sum(1 for s in SOURCES if getattr(r, "obs_" + s) > 0)

    # --- the threat window -------------------------------------------------------
    # T6 keeps a ConfirmedThreat and an authorisation each for its ttl_s from
    # its stamp, and releases a mission when the two are valid at the same
    # time. The validity intervals of the ConfirmedThreats merge into the spans
    # in which one was valid; the authorisation meets a valid threat if its own
    # interval overlaps one of them.
    cts = sorted((stamp_s(m.t), stamp_s(m.t) + float(m.ttl_s))
                 for _, m in mine("interp")
                 if m.label == "ConfirmedThreat"
                 and clock_of(stamp_s(m.t)) == "sim")
    spans = valid_spans(cts)
    if spans:
        res.threat_confirmed_for = cts[-1][0] - cts[0][0]
        res.threat_valid_for = spans[0][1] - spans[0][0]
        res.threat_spans = len(spans)
        auths = sorted((stamp_s(m.t), max(0.0, float(m.ttl_s)))
                       for _, m in mine("auth")
                       if m.decision in AUTHORISE
                       and clock_of(stamp_s(m.t)) == "sim")
        if auths:
            ta, ttl = auths[0]
            res.auth_meets_threat = any(s <= ta + ttl and ta <= e
                                        for s, e in spans)

    # --- the EO evidence of the threat ------------------------------------------
    # T5 fuses a CandidateTarget with an EO confirmation into a
    # ConfirmedThreat, whose origin ends with the id of that EO confirmation.
    uav_task = next((m.assigned_system for _, m in data.get("task")
                     if m.assigned_system != UGV_SYSTEM), None)
    res.eo_at_post = uav_task != EO_CARRIER
    interp = data.get("interp")
    stamp = {m.id: stamp_s(m.t) for _, m in interp}
    eo = sorted(stamp_s(m.t) for _, m in interp
                if m.label == "ConfirmedAerialObject")
    last = max(((stamp_s(m.t), m) for _, m in interp
                if m.label == "ConfirmedThreat"),
               key=lambda p: p[0], default=None)
    if len(eo) >= 2 and eo[-1] > eo[0] and last is not None:
        t_last, threat = last
        res.eo_pass = eo[-1] - eo[0]
        res.eo_tail = t_last - eo[-1]
        if threat.origin and threat.origin[-1] in stamp:
            res.eo_age = t_last - stamp[threat.origin[-1]]
        res.candidates_per_s = sum(
            1 for _, m in interp if m.label == "CandidateTarget"
            and eo[0] <= stamp_s(m.t) <= eo[-1]) / res.eo_pass

    # --- the window of T3 --------------------------------------------------------
    res.t3_window = t3_window_of(
        os.path.join(os.path.dirname(bag), "logs", T3_LOG))
    if t3_window is not None:
        if res.t3_window is None:
            res.problems.append(
                "no T3 window in logs/{}: the T3_WINDOW_S of the run cannot "
                "be checked".format(T3_LOG))
        elif abs(res.t3_window - round(t3_window, 1)) > 0.05:
            res.problems.append(
                "T3 ran with a {:.1f} s window, the configuration sets "
                "{:g} s".format(res.t3_window, t3_window))

    res.clean = not res.problems
    return res


# =============================================================================
# Statistics
# =============================================================================
def wilson(k: int, n: int) -> Optional[Tuple[float, float]]:
    """95% Wilson score interval of k successes out of n."""
    if n == 0:
        return None
    p, z2 = k / n, Z95 * Z95
    den = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / den
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_cell(k: int, n: int) -> str:
    """k/n [low-high], the interval in percent."""
    ci = wilson(k, n)
    if ci is None:
        return "—"
    return "{}/{} [{:.1f}–{:.1f}]".format(k, n, 100 * ci[0], 100 * ci[1])


def time_cell(values: list) -> str:
    """mean ± sample sd (n), or a dash."""
    s = describe(values)
    if s is None:
        return "—"
    return "{:.2f} ± {:.2f} ({})".format(s["mean"], s["sd"], s["n"])


# Binary outcomes: key, label, test on the audit (None: does not apply).
BINARY: List[Tuple[str, str, Callable]] = [
    ("expected", "expected outcome",
     lambda r: OUTCOMES[r.expected](r) if r.expected else None),
    ("candidate", "CandidateTarget", lambda r: r.candidates > 0),
    ("eo_confirmation", "EO confirmation", lambda r: r.aerial_objects > 0),
    ("threat", "ConfirmedThreat", lambda r: r.threats > 0),
    ("mission", "mission", lambda r: r.missions > 0),
    ("mission_after_authorise", "mission after an authorise decision",
     lambda r: r.missions > 0 if r.authorise else None),
] + [("detected_" + s, MODALITY_LABELS[s] + " detection",
      lambda r, s=s: getattr(r, "obs_" + s) > 0) for s in SOURCES]

# Times: key, label, value of a run.
TIMES: List[Tuple[str, str, Callable]] = [
    ("obs_to_candidate", "first obs → CandidateTarget",
     lambda x: x.audit.obs_to_candidate),
    ("candidate_to_threat", "CandidateTarget → ConfirmedThreat",
     lambda x: x.audit.candidate_to_threat),
    ("obs_to_threat", "first obs → ConfirmedThreat",
     lambda x: x.audit.obs_to_threat),
    ("threat_to_decision", "ConfirmedThreat → decision",
     lambda x: x.threat_to_decision),
    ("decision_to_mission", "decision → mission",
     lambda x: x.decision_to_mission),
    ("obs_to_mission", "first obs → mission",
     lambda x: x.audit.obs_to_mission),
    ("mission_to_task", "mission → first task",
     lambda x: x.mission_to_task),
] + [("first_" + s, "first obs → first " + MODALITY_LABELS[s],
      lambda x, s=s: getattr(x.audit, "first_" + s)) for s in SOURCES] + [
    ("threat_confirmed_for", "threat confirmed for",
     lambda x: x.threat_confirmed_for),
    ("threat_valid_for", "threat valid for", lambda x: x.threat_valid_for),
]


def binary(clean: List[RunResult], test: Callable) -> Tuple[int, int]:
    """Successes and runs among the clean runs the test applies to."""
    got = [test(x.audit) for x in clean]
    got = [g for g in got if g is not None]
    return sum(1 for g in got if g), len(got)


# =============================================================================
# Report
# =============================================================================
def md_table(header: List[str], rows: List[List[str]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines + [""]


def report(name: str, envs: Dict[str, Dict[str, str]],
           attempts: List[Attempt], order: List[str],
           results: Dict[str, List[RunResult]], missing: List[str],
           repeated: List[str]) -> List[str]:
    commits = sorted({x.attempt.commit for rs in results.values() for x in rs})
    n_runs = sum(len(rs) for rs in results.values())
    n_clean = sum(1 for rs in results.values() for x in rs if x.clean)
    out = ["# Campaign `{}`".format(name), ""]
    out.append("- Runs with a valid attempt: {}; clean: {}; left out: "
               "{}.".format(n_runs, n_clean, n_runs - n_clean))
    out.append("- Campaigns: {}.".format("; ".join(
        "`{}` (first seed {}, started {})".format(
            os.path.basename(d), env.get("FIRST_SEED", "n/a"),
            env.get("STARTED_UTC", "n/a")) for d, env in envs.items())))
    out.append("- Commit of the runs: {}.".format(", ".join(commits) or "n/a"))
    by_outcome = Counter(a.outcome for a in attempts)
    out.append("- Attempts: {} ({}).".format(len(attempts), ", ".join(
        "{} {}".format(v, k) for k, v in by_outcome.most_common())))
    out.append("- All times in simulated time (token stamps), in seconds; "
               "rates over the clean runs, with the 95% Wilson interval in "
               "percent.")
    out.append("")

    out.append("## Outcomes")
    out.append("")
    rows = []
    for c in order:
        clean = [x for x in results[c] if x.clean]
        exp = EXPECTED.get(c, "")
        cells = [c, "{}/{}".format(len(clean), len(results[c])),
                 OUTCOME_LABELS.get(exp, "—")]
        for key, _, test in BINARY[:5]:
            k, n = binary(clean, test)
            cells.append(rate_cell(k, n))
        rows.append(cells)
    out += md_table(["Configuration", "Clean runs", "Expected outcome",
                     "Rate", "CandidateTarget", "EO confirmation",
                     "ConfirmedThreat", "Mission"], rows)

    out.append("## Times")
    out.append("")
    rows = []
    for c in order:
        clean = [x for x in results[c] if x.clean]
        rows.append([c] + [time_cell([get(x) for x in clean])
                           for _, _, get in TIMES[:7]])
    out += md_table(["Configuration"] + [label for _, label, _ in TIMES[:7]],
                    rows)

    out.append("## Authorisation")
    out.append("")
    rows = []
    for c in order:
        clean = [x for x in results[c] if x.clean]
        decided = [x for x in clean if x.audit.authorise + x.audit.deny]
        if not decided:
            continue
        k, n = binary(clean, BINARY[5][2])
        rows.append([c, "{} authorise, {} deny".format(
            sum(1 for x in decided if x.audit.authorise),
            sum(1 for x in decided if x.audit.deny)),
            rate_cell(k, n) if n else "—",
            time_cell([x.threat_to_decision for x in clean]),
            time_cell([x.decision_to_mission for x in clean])])
    out += md_table(["Configuration", "Runs with a decision",
                     "Mission after authorise", "ConfirmedThreat → decision",
                     "decision → mission"], rows)

    out.append("## Threat window")
    out.append("")
    out.append("Runs with an authorise decision. A ConfirmedThreat is valid "
               "from its stamp for its TTL, and so is the authorisation; T6 "
               "releases a mission when the two are valid at the same time. "
               "Threat confirmed for: from the first ConfirmedThreat to the "
               "last. Threat valid for: from the first ConfirmedThreat to the "
               "end of the first span in which one was valid (mean ± sample "
               "sd, s).")
    out.append("")
    mission = {key: test for key, _, test in BINARY}["mission"]
    rows = []
    for c in order:
        clean = [x for x in results[c] if x.clean]
        decided = [x for x in clean if x.auth_meets_threat is not None]
        if not decided:
            continue
        k, n = binary(decided, mission)
        rows.append([
            c, str(len(decided)),
            time_cell([x.threat_confirmed_for for x in decided]),
            time_cell([x.threat_valid_for for x in decided]),
            "{}/{}".format(sum(1 for x in decided if x.threat_spans > 1),
                           len(decided)),
            time_cell([x.threat_to_decision for x in decided]),
            "{}/{}".format(sum(1 for x in decided if x.auth_meets_threat),
                           len(decided)),
            rate_cell(k, n)])
    out += md_table(["Configuration", "Runs", "Threat confirmed for",
                     "Threat valid for", "Threat valid again after a lapse",
                     "ConfirmedThreat → authorisation",
                     "Authorisation meets a valid threat", "Mission"], rows)

    out.append("## EO evidence of the threat")
    out.append("")
    out.append("Runs with a ConfirmedThreat in which UAV0, which carries the "
               "EO camera, stays at its post (no UAV task, or the first one "
               "to another UAV). T5 fuses a CandidateTarget with an EO "
               "confirmation into a ConfirmedThreat. EO pass: from the first "
               "EO confirmation to the last. Last threat after the last EO: "
               "from the last EO confirmation to the last ConfirmedThreat. "
               "EO age: the stamp of the last ConfirmedThreat minus that of "
               "the EO confirmation fused into it. CandidateTargets per s: "
               "during the EO pass (mean ± sample sd).")
    out.append("")
    rows = []
    for c in order:
        held = [x for x in results[c] if x.clean and x.eo_at_post
                and x.eo_pass is not None]
        if not held:
            continue
        rows.append([c, str(len(held))] + [time_cell(
            [getattr(x, k) for x in held]) for k in (
                "eo_pass", "threat_confirmed_for", "eo_tail", "eo_age",
                "candidates_per_s")])
    out += md_table(["Configuration", "Runs", "EO pass (s)",
                     "Threat confirmed for (s)",
                     "Last threat after the last EO (s)",
                     "EO age in the last threat (s)",
                     "CandidateTargets per s"], rows)

    out.append("## Detection by modality")
    out.append("")
    out.append("Runs in which the modality observed the target, and its "
               "first observation after the first observation of any "
               "modality (mean, s).")
    out.append("")
    rows = []
    for c in order:
        clean = [x for x in results[c] if x.clean]
        cells = [c]
        for s in SOURCES:
            k, n = binary(clean, lambda r, s=s: getattr(r, "obs_" + s) > 0)
            m = describe([getattr(x.audit, "first_" + s) for x in clean])
            cells.append("—" if n == 0 else "{}/{}{}".format(
                k, n, "" if m is None else ", +{:.2f}".format(m["mean"])))
        first = Counter(x.audit.first_source for x in clean
                        if x.audit.first_source)
        cells.append(", ".join("{} {}".format(k, v)
                               for k, v in first.most_common()) or "—")
        rows.append(cells)
    out += md_table(["Configuration"] + [MODALITY_LABELS[s] for s in SOURCES]
                    + ["First modality (runs)"], rows)

    out.append("## Runs")
    out.append("")
    rows = []
    for c in order:
        clean = [x for x in results[c] if x.clean]
        rtf = describe([x.audit.rtf for x in clean])
        v = describe([x.audit.v_sim for x in clean])
        t3 = Counter(x.t3_window for x in clean if x.t3_window is not None)
        rows.append([c, str(len(results[c])), str(len(clean)),
                     str(len(results[c]) - len(clean)),
                     "—" if rtf is None else "{:.3f} ({:.3f})".format(
                         rtf["mean"], rtf["min"]),
                     "—" if v is None else "{:.2f} ({:.2f}–{:.2f})".format(
                         v["mean"], v["min"], v["max"]),
                     ", ".join("{:.1f} ({})".format(w, k)
                               for w, k in sorted(t3.items())) or "—"])
    out += md_table(["Configuration", "Valid", "Clean", "Left out",
                     "Real-time factor, mean (min)",
                     "Intruder speed in simulated time, m/s",
                     "T3 window, s (runs)"], rows)

    out.append("## Runs left out")
    out.append("")
    bad = [x for c in order for x in results[c] if not x.clean]
    out += ["- {} run {} (seed {}, attempt {} in `{}`): {}".format(
        x.attempt.configuration, x.run, x.attempt.seed, x.attempt.attempt,
        x.attempt.campaign, "; ".join(x.problems))
        for x in bad] or ["- none"]
    out.append("")
    out.append("## Runs repeated")
    out.append("")
    out += ["- " + r for r in repeated] or ["- none"]
    out.append("")
    out.append("## Runs without a valid attempt")
    out.append("")
    out += ["- " + m for m in missing] or ["- none"]
    out.append("")
    noted = [x for c in order for x in results[c] if x.notes]
    if noted:
        out.append("## Notes")
        out.append("")
        out += ["- {} run {}: {}".format(x.attempt.configuration, x.run,
                                         "; ".join(x.notes)) for x in noted]
        out.append("")
    return out


def write_csvs(out_dir: str, order: List[str],
               results: Dict[str, List[RunResult]]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    audit_fields = [f.name for f in fields(ChainRun)
                    if f.name not in ("bag", "configuration", "run", "clean",
                                      "problems", "notes")]

    def num(v):
        if v is None:
            return ""
        return "{:.6f}".format(v) if isinstance(v, float) else v

    with open(os.path.join(out_dir, "runs.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["configuration", "run", "seed", "campaign", "attempt",
                    "commit", "folder", "clean", "problems", "notes",
                    "modalities",
                    "threat_to_decision", "decision_to_mission",
                    "mission_to_task", "threat_confirmed_for",
                    "threat_valid_for", "threat_spans", "auth_meets_threat",
                    "t3_window", "eo_at_post", "eo_pass", "eo_tail", "eo_age",
                    "candidates_per_s"] + audit_fields)
        for c in order:
            for x in results[c]:
                a = x.attempt
                row = [a.configuration, x.run, a.seed, a.campaign, a.attempt,
                       a.commit, a.folder, x.clean, "; ".join(x.problems),
                       "; ".join(x.notes), x.modalities,
                       num(x.threat_to_decision), num(x.decision_to_mission),
                       num(x.mission_to_task), num(x.threat_confirmed_for),
                       num(x.threat_valid_for), x.threat_spans,
                       num(x.auth_meets_threat), num(x.t3_window),
                       num(x.eo_at_post), num(x.eo_pass), num(x.eo_tail),
                       num(x.eo_age), num(x.candidates_per_s)]
                row += [num(getattr(x.audit, n)) if x.audit else ""
                        for n in audit_fields]
                w.writerow(row)

    with open(os.path.join(out_dir, "outcomes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["configuration", "outcome", "successes", "runs", "rate",
                    "ci95_low", "ci95_high"])
        for c in order:
            clean = [x for x in results[c] if x.clean]
            for key, _, test in BINARY:
                k, n = binary(clean, test)
                if n == 0:
                    continue
                lo, hi = wilson(k, n)
                w.writerow([c, key, k, n, num(k / n), num(lo), num(hi)])
            got = [x.auth_meets_threat for x in clean
                   if x.auth_meets_threat is not None]
            if got:
                k, n = sum(got), len(got)
                lo, hi = wilson(k, n)
                w.writerow([c, "auth_meets_threat", k, n, num(k / n),
                            num(lo), num(hi)])

    with open(os.path.join(out_dir, "latencies.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["configuration", "quantity", "n", "mean", "sd", "median",
                    "min", "max"])
        for c in order:
            clean = [x for x in results[c] if x.clean]
            for key, _, get in TIMES:
                s = describe([get(x) for x in clean])
                if s is None:
                    continue
                w.writerow([c, key, s["n"], num(s["mean"]), num(s["sd"]),
                            num(s["median"]), num(s["min"]), num(s["max"])])


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description="Tables of a campaign of recorded runs (read-only).")
    ap.add_argument("campaigns", nargs="+",
                    help="campaign folders, e.g. bags/campaigns/full; the "
                         "next ones hold further attempts of its runs")
    ap.add_argument("--out", default=None,
                    help="output folder (default: results/<first campaign>)")
    ap.add_argument("--configurations", default=os.path.join(
        here, "..", "experiments", "configurations.conf"),
        help="configurations.conf, for the order of the tables and the "
             "T3_WINDOW_S of each configuration")
    args = ap.parse_args()

    dirs = [os.path.normpath(c) for c in args.campaigns]
    name = os.path.basename(dirs[0])
    attempts: List[Attempt] = []
    envs: Dict[str, Dict[str, str]] = {}
    for d in dirs:
        manifest = os.path.join(d, "manifest.csv")
        if not os.path.isfile(manifest):
            print("no manifest.csv in {}".format(d), file=sys.stderr)
            return 2
        attempts += read_manifest(manifest, d)
        envs[d] = read_env(os.path.join(d, "campaign.env"))

    # Attempts with the same configuration and seed are attempts of one run.
    runs: Dict[Tuple[str, int], List[Attempt]] = {}
    for a in attempts:
        runs.setdefault((a.configuration, a.seed), []).append(a)
    seen = []
    for a in attempts:
        if a.configuration not in seen:
            seen.append(a.configuration)
    order = [c for c in configuration_order(args.configurations) if c in seen]
    order += [c for c in seen if c not in order]
    conf_vars = configuration_vars(args.configurations)
    groups = sorted(runs.items(), key=lambda kv: (order.index(kv[0][0]),
                                                  kv[1][0].run))

    total = sum(1 for _, tries in groups if any(a.valid for a in tries))
    print("[analysis] {}: {} run(s) with a valid attempt ...".format(
        ", ".join(os.path.basename(d) for d in dirs), total), file=sys.stderr)
    results: Dict[str, List[RunResult]] = {c: [] for c in order}
    missing: List[str] = []
    repeated: List[str] = []
    for (c, seed), tries in groups:
        run = tries[0].run
        valid = [a for a in tries if a.valid]
        if not valid:
            missing.append("{} run {} (seed {}): {}".format(
                c, run, seed, ", ".join(
                    "attempt {} in `{}` {}".format(
                        a.attempt, a.campaign, a.outcome) for a in tries)))
            continue
        # The first valid attempt that is clean; if none is, the last one.
        t3 = conf_vars.get(c, {}).get("T3_WINDOW_S")
        analysed: List[RunResult] = []
        for a in valid:
            analysed.append(analyze_run(
                a, envs[a.campaign_dir].get("COMMIT", ""),
                t3_window=float(t3) if t3 else None))
            if analysed[-1].clean:
                break
        used = analysed[-1]
        used.run = run
        for x in analysed[:-1]:
            repeated.append(
                "{} run {} (seed {}): attempt {} in `{}` set aside ({}); "
                "attempt {} in `{}` used".format(
                    c, run, seed, x.attempt.attempt, x.attempt.campaign,
                    "; ".join(x.problems), used.attempt.attempt,
                    used.attempt.campaign))
        if len(valid) > len(analysed):
            used.notes.append("{} more valid attempt(s) not used".format(
                len(valid) - len(analysed)))
        results[c].append(used)
    if total == 0:
        print("no run with a valid attempt", file=sys.stderr)
        return 1

    lines = report(name, envs, attempts, order, results, missing, repeated)
    text = "\n".join(lines)
    print(text)
    out_dir = args.out or os.path.join("results", name)
    write_csvs(out_dir, order, results)
    with open(os.path.join(out_dir, "tables.md"), "w") as f:
        f.write(text + "\n")
    print("[analysis] tables.md, runs.csv, outcomes.csv and latencies.csv "
          "written to {}".format(out_dir), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
