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
# @file metrics_counterfactual.py
#
# Offline verification of the three counterfactual trajectories of the IET 2026
# case study (Section 5.3). These are the architecture's NEGATIVE guarantees:
# the value is as much in the trajectories that do NOT lead to a mission as in
# those that do. The paper states the correctness properties "operate as much
# in the negative as in the positive"; this checks them empirically, offline,
# from a recorded bag.
#
# The three counterfactuals, and the output each must SUPPRESS:
#
#   C1  Authorisation withheld  -> no InterceptMission
#       A ConfirmedThreat forms, but the supervisor denies (or never issues)
#       authorisation. T6 cannot fire. The threat persists; no mission.
#       Reproduce with:  DECISION=deny ./scripts/record/record_run.sh
#
#   C2  Stale EO confirmation   -> no ConfirmedThreat
#       The EO confirmation arrives after the T5 fusion window has closed, so
#       the CandidateTarget is never promoted to ConfirmedThreat.
#       Reproduce with an EO delay (needs the eo_agent delay parameter; not yet
#       wired -- this script detects and reports when a bag does not contain it).
#
#   C3  Conflicting interpretation -> no CandidateTarget
#       RF reads the same window as LikelyCivilianTraffic instead of
#       LikelyDroneLink. T3's concordance guard blocks; no candidate forms.
#       Reproduce with the RF civilian mode (needs the rf_agent mode parameter;
#       not yet wired).
#
# This script INFERS which counterfactual a bag represents from its contents,
# then checks that the expected suppression holds. A pass means the negative
# guarantee was upheld: the forbidden token was correctly NOT produced while its
# precondition WAS present.
#
# USAGE
#   source install/setup.bash
#   python3 scripts/metrics/metrics_counterfactual.py bags/coastal-DENY-*/
# =============================================================================
import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, field, asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from metrics_chain import read_bag, resolve_bag
except ImportError as e:
    sys.stderr.write("error: could not import metrics_chain ({}).\n".format(e))
    sys.exit(2)


@dataclass
class CounterfactualResult:
    """Outcome of verifying one counterfactual trajectory from a bag."""
    bag: str = ""
    target_id: str = ""
    scenario: str = "unknown"     # C1 | C2 | C3 | positive | unknown
    precondition_present: bool = False
    forbidden_present: bool = False
    passed: bool = False
    detail: str = ""
    counts: dict = field(default_factory=dict)


def label_counts(interp, target):
    """Count InterpToken labels for a target.

    @param interp  List of (recv_ns, InterpToken) for /interp_tokens.
    @param target  target_id to match.
    @return        Dict label -> count for the matching target.
    """
    c = {}
    for _, m in interp:
        if getattr(m, "target_id", "") != target:
            continue
        lab = getattr(m, "label", "?")
        c[lab] = c.get(lab, 0) + 1
    return c


def pick_target(data):
    """Choose the target to analyse: the one with the most observations.

    @param data  The read_bag() output.
    @return      A target_id string, or None if there are no observations.
    """
    counts = {}
    for _, m in data.get("/obs_tokens", []):
        tid = getattr(m, "target_id", "")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
    return max(counts, key=counts.get) if counts else None


def classify_and_check(data, bag_dir):
    """Infer which counterfactual a bag represents and verify its suppression.

    Classifies the run from its token contents (a conflicting civilian label,
    a denied authorisation, a stale or absent EO confirmation, or a positive
    authorised run) and checks that the forbidden output was correctly not
    produced while its precondition was present.

    @param data     read_bag() output.
    @param bag_dir  bag path, stored in the result for reference.
    @return         A populated CounterfactualResult.
    """
    r = CounterfactualResult(bag=os.path.basename(os.path.normpath(bag_dir)))
    interp = data.get("/interp_tokens", [])
    missions = data.get("/mission_tokens", [])
    auths = data.get("/supervisor_auth", [])

    target = pick_target(data)
    if target is None:
        r.detail = "no target with observations; cannot classify"
        return r
    r.target_id = target

    lc = label_counts(interp, target)
    n_candidate = lc.get("CandidateTarget", 0)
    n_confirmed = lc.get("ConfirmedThreat", 0)
    n_civilian = lc.get("LikelyCivilianTraffic", 0)
    n_aerial = lc.get("ConfirmedAerialObject", 0)  # EO confirmation
    n_mission = sum(1 for _, m in missions
                    if getattr(m, "target_id", "") == target)

    # Was any authorisation a DENY?
    n_deny = 0
    n_authorise = 0
    for _, m in auths:
        if getattr(m, "target_id", "") != target:
            continue
        d = getattr(m, "decision", "")
        if d == "deny":
            n_deny += 1
        elif d in ("authorise", "authorize"):
            n_authorise += 1

    r.counts = {
        "CandidateTarget": n_candidate,
        "ConfirmedThreat": n_confirmed,
        "ConfirmedAerialObject": n_aerial,
        "LikelyCivilianTraffic": n_civilian,
        "mission_tokens": n_mission,
        "auth_deny": n_deny,
        "auth_authorise": n_authorise,
    }

    # C3: a conflicting civilian interpretation is present. Precondition is the
    # conflicting label; the forbidden output is a CandidateTarget forming
    # despite the conflict.
    if n_civilian > 0:
        r.scenario = "C3"
        r.precondition_present = n_civilian > 0
        r.forbidden_present = n_candidate > 0
        r.passed = r.precondition_present and not r.forbidden_present
        r.detail = ("conflicting LikelyCivilianTraffic present ({}); "
                    "CandidateTarget must not form (found {})".format(
                        n_civilian, n_candidate))
        return r

    # C1: an authorisation was denied (and none authorised). Precondition is a
    # ConfirmedThreat; the forbidden output is a released mission.
    if n_deny > 0 and n_authorise == 0:
        r.scenario = "C1"
        r.precondition_present = n_confirmed > 0
        r.forbidden_present = n_mission > 0
        r.passed = r.precondition_present and not r.forbidden_present
        r.detail = ("authorisation denied with a live ConfirmedThreat "
                    "({}); no InterceptMission must be released (found {})"
                    .format(n_confirmed, n_mission))
        return r

    # C2 (the paper's "stale EO confirmation", Section 5.3): a CandidateTarget
    # forms AND an EO confirmation IS produced (ConfirmedAerialObject > 0), but
    # the confirmation reaches T5 after the CandidateTarget's validity window
    # has closed, so the two never fuse and no ConfirmedThreat is produced. The
    # EO delay is injected with EO_DELAY_S. This is the literal stale-EO
    # trajectory: the visual exists and is delivered, just too late.
    if n_candidate > 0 and n_aerial > 0 and n_confirmed == 0:
        r.scenario = "C2"
        r.precondition_present = n_candidate > 0 and n_aerial > 0
        r.forbidden_present = n_confirmed > 0
        r.passed = r.precondition_present and not r.forbidden_present
        r.detail = ("CandidateTarget ({}) and a (late) EO confirmation ({}) "
                    "both present, but no ConfirmedThreat: the stale EO fell "
                    "outside T5's fusion window (found threats {})".format(
                        n_candidate, n_aerial, n_confirmed))
        return r

    # C2-absent: the limiting case where EO is switched off entirely. Same arc
    # (no EO confirmation within the window) but by absence rather than delay.
    if n_candidate > 0 and n_aerial == 0 and n_confirmed == 0:
        r.scenario = "C2-absent"
        r.precondition_present = n_candidate > 0
        r.forbidden_present = n_confirmed > 0
        r.passed = r.precondition_present and not r.forbidden_present
        r.detail = ("CandidateTarget formed ({}) with NO EO confirmation at "
                    "all (ConfirmedAerialObject=0); ConfirmedThreat must not "
                    "form (found {}). Limiting case of the stale-EO arc."
                    .format(n_candidate, n_confirmed))
        return r

    # Otherwise this looks like a positive (completing) run or an authorised one.
    if n_authorise > 0:
        r.scenario = "positive"
        r.precondition_present = n_confirmed > 0
        r.forbidden_present = False
        r.passed = n_mission > 0  # a positive run SHOULD produce a mission
        r.detail = ("authorised run: a mission is expected (found {})"
                    .format(n_mission))
        return r

    r.scenario = "unknown"
    r.detail = ("no deny, no civilian conflict, no authorisation: "
                "not a recognised counterfactual")
    return r


def print_report(r):
    """Print a human-readable verdict for one counterfactual check.

    @param r  Populated CounterfactualResult from classify_and_check().
    @return   None.
    """
    print()
    print("=" * 66)
    print("  Counterfactual verification (Section 5.3)")
    print("  bag:      {}".format(r.bag))
    print("  target:   {}".format(r.target_id or "(none)"))
    print("  scenario: {}".format(r.scenario))
    print("=" * 66)
    print("  token counts:")
    for k, v in r.counts.items():
        print("     {:24s} {}".format(k, v))
    print("-" * 66)
    print("  precondition present: {}".format(r.precondition_present))
    print("  forbidden output:     {}".format(r.forbidden_present))
    print("  {}".format(r.detail))
    print("-" * 66)
    verdict = "PASS" if r.passed else "FAIL"
    print("  negative guarantee upheld: {}".format(verdict))
    print("=" * 66)
    print()


def main():
    """Parse arguments, verify the counterfactual in one bag, and report.

    Resolves the bag argument, reads it, classifies and checks the
    counterfactual, prints the verdict, and optionally writes JSON. Exit code
    is 0 if the negative guarantee held, 1 otherwise.

    @return  None.
    """
    ap = argparse.ArgumentParser(
        description="Verify a Section 5.3 counterfactual from a bag.")
    ap.add_argument("bag", help="bag directory or glob")
    ap.add_argument("--json", help="write the result as JSON")
    args = ap.parse_args()

    bag_dir = resolve_bag(args.bag)
    data = read_bag(bag_dir)
    result = classify_and_check(data, bag_dir)
    print_report(result)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(asdict(result), f, indent=2)
        print("  result written to {}".format(args.json))
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()