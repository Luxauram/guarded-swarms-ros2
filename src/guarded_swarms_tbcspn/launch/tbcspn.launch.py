#!/usr/bin/env python3
"""
Copyright 2026 Luca D'Aurizio

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
"""
@file tbcspn.launch.py

Guarded Swarms - the TB-CSPN coordination layer.

Brings up all the transitions of Figure 4 in one command: the interpretation
transitions (T1, T2, T4), the time-windowed joins (T3, T5), the mission-release
transition (T6, human-in-the-loop) and the dispatch transition (T7). Replaces
the one-terminal-per-transition workflow used while developing them.

  T1  interpretation_node   radar -> PossibleUAV
  T2  interpretation_node   rf    -> LikelyDroneLink
  T4  interpretation_node   eo    -> ConfirmedAerialObject
  T3  candidate_transition  PossibleUAV + LikelyDroneLink -> CandidateTarget
  T5  candidate_transition  CandidateTarget + ConfirmedAerialObject
                              -> ConfirmedThreat
  T6  mission_transition    ConfirmedThreat + SupervisorAuth -> InterceptMission
  T7  dispatch_transition   InterceptMission -> VehicleTask (per vehicle)

TEMPORAL PARAMETERS OF THE COORDINATION LAYER
=============================================
All the time constants that govern the token algebra are collected below, so
the experiment's configuration is visible and reproducible in one place rather
than scattered across node defaults. They follow the paper's token model
(Borghoff, Bottoni and Pareschi 2026, Sec. 3.2-3.3): a token is valid until
t0 + ttl, and two tokens fuse when abs((t0'+ttl') - (t0+ttl)) <= sync_threshold.

  SYNC_THRESHOLD_S   the paper's `ths`: the half-width of the fusion window
                     shared by the joins (T3, T5) and the mission release (T6).

  T3_WINDOW_S        an environment variable: when set, the window of T3
                     alone, in seconds, so the CandidateTarget join can be
                     varied while T5 and T6 keep SYNC_THRESHOLD_S. Unset by
                     default: T3 then shares SYNC_THRESHOLD_S.

  THREAT_TTL_S       how long a ConfirmedThreat stays valid once emitted. A
                     confirmed threat is a consolidated inference over several
                     modalities, not a raw instantaneous reading, so it is
                     given a longer life than a raw observation (radar/rf/
                     acoustic ~3 s, EO ~2 s, set in the sensing configs). This
                     also sets how long a threat waits in T6 for an
                     authorisation before it must be re-confirmed: too short and
                     an authorisation that arrives a moment later finds no live
                     threat to release against.

  MISSION_TTL_S      how long a released InterceptMission stays valid; a mission
                     that outlives its target's track should expire rather than
                     be flown blind.

Raw-observation TTLs are deliberately NOT here: they belong to the sensing
model and live in src/guarded_swarms_sensing/config/*.yaml.

Prereq: the sensing layer must be producing /obs_tokens (the coastal world, the
intruder and sensing.launch.py already running).

Monitor:
  ros2 topic echo /interp_tokens  --field label
  ros2 topic echo /mission_tokens

Authorise:
  - automated runs: the scripted supervisor decides on its own
    (ros2 launch guarded_swarms_supervisor supervisor.launch.py);
  - interactive runs: the supervisor console, or by hand:
      ros2 topic pub --once --keep-alive 5 \\
        --qos-durability transient_local /supervisor_auth \\
        guarded_swarms_msgs/msg/SupervisorAuth \\
        "{target_id: 'intruder', authorised_by: 'supervisor_luca', \\
          decision: 'authorise', ttl_s: 15.0}"
    T6 subscribes with TRANSIENT_LOCAL durability, so the publisher must
    offer it too; --keep-alive keeps the message available while T6 matches.

@author Luca D'Aurizio
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = "guarded_swarms_tbcspn"

# -----------------------------------------------------------------------------
# Temporal parameters of the coordination layer (see the module docstring).
# Exposed as launch arguments so a metric campaign can sweep them without a
# rebuild, and so the experiment configuration is documented in one place.
# -----------------------------------------------------------------------------
# The label T2 emits for an RF detection. Normally LikelyDroneLink. Set to
# LikelyCivilianTraffic to reproduce the "conflicting interpretation"
# counterfactual: T3 needs PossibleUAV + LikelyDroneLink to form a
# CandidateTarget, so a civilian label -- concordant with nothing -- blocks the
# candidate, and no threat and no mission follow.
# The RF interpretation label. Read from the RF_LABEL environment variable so a
# counterfactual run (RF_LABEL=LikelyCivilianTraffic) can override it without a
# launch-argument substitution, which does not reliably resolve when passed as
# a value inside a node's parameter dict. Falls back to the concordant label.
DEFAULT_RF_INTERP_LABEL = os.environ.get("RF_LABEL", "LikelyDroneLink")
DEFAULT_SYNC_THRESHOLD_S = "3.0"
DEFAULT_THREAT_TTL_S = "10.0"    # was 4.0; raised so a confirmed threat waits
                                 # long enough for the human authorisation
DEFAULT_MISSION_TTL_S = "10.0"

# The window of T3 alone, in seconds. Read from the T3_WINDOW_S environment
# variable, as RF_LABEL is, so a run can vary the CandidateTarget join without
# touching T5 and T6. Passed to the node as a float, so a whole number such as
# 4 reaches it as a double, the type it declares. Unset or empty: None, and T3
# shares sync_threshold_s with T5 and T6.
T3_WINDOW_ENV = os.environ.get("T3_WINDOW_S", "").strip()
T3_WINDOW_S = float(T3_WINDOW_ENV) if T3_WINDOW_ENV else None


def interp(name, source, label):
    """One first-level interpretation transition (T1/T2/T4)."""
    return Node(
        package=PKG, executable="interpretation_node", name=name,
        output="screen", emulate_tty=True,
        parameters=[{
            "accept_source": source,
            "emit_label": label,
            "use_sim_time": True,
        }],
    )


def join(name, label_a, label_b, emit_label, emit_ttl=None, sync_s=None):
    """One time-windowed join transition (T3/T5).

    emit_ttl is optional: T5 (the ConfirmedThreat) gets the tunable threat TTL;
    T3 (the intermediate CandidateTarget) omits it and keeps the node default,
    which is adequate for a step that is immediately consumed by T5.
    sync_s is optional too: a window of this join alone, in seconds; without
    it the join uses the shared sync_threshold_s.
    """
    params = {
        "label_a": label_a,
        "label_b": label_b,
        "emit_label": emit_label,
        "sync_threshold_s": (LaunchConfiguration("sync_threshold_s")
                             if sync_s is None else sync_s),
        "use_sim_time": True,
    }
    if emit_ttl is not None:
        params["emit_ttl_s"] = emit_ttl
    return Node(
        package=PKG, executable="candidate_transition_node", name=name,
        output="screen", emulate_tty=True,
        parameters=[params],
    )


def generate_launch_description():
    sync_arg = DeclareLaunchArgument(
        "sync_threshold_s", default_value=DEFAULT_SYNC_THRESHOLD_S,
        description="Fusion-window half-width `ths` shared by T3, T5 and T6 "
                    "(T3 has its own when T3_WINDOW_S is set).")
    threat_ttl_arg = DeclareLaunchArgument(
        "threat_ttl_s", default_value=DEFAULT_THREAT_TTL_S,
        description="Validity (seconds) of an emitted ConfirmedThreat.")
    mission_ttl_arg = DeclareLaunchArgument(
        "mission_ttl_s", default_value=DEFAULT_MISSION_TTL_S,
        description="Validity (seconds) of a released InterceptMission.")

    return LaunchDescription([
        sync_arg,
        threat_ttl_arg,
        mission_ttl_arg,
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - TB-CSPN coordination layer (T1-T7)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: sensing layer producing /obs_tokens"),
        LogInfo(msg="Monitor:  ros2 topic echo /interp_tokens --field label"),
        LogInfo(msg="          ros2 topic echo /mission_tokens"),
        LogInfo(msg="Authorise: scripted supervisor (supervisor.launch.py),"),
        LogInfo(msg="  the console, or by hand:"),
        LogInfo(msg="  ros2 topic pub --once --keep-alive 5 \\"),
        LogInfo(msg="  --qos-durability transient_local /supervisor_auth \\"),
        LogInfo(msg="  guarded_swarms_msgs/msg/SupervisorAuth \\"),
        LogInfo(msg="  \"{target_id: 'intruder', authorised_by: 'sup', \\"),
        LogInfo(msg="    decision: 'authorise', ttl_s: 15.0}\""),
        LogInfo(msg="T3 window: " + (
            "sync_threshold_s, shared with T5 and T6" if T3_WINDOW_S is None
            else "{:g} s, from T3_WINDOW_S".format(T3_WINDOW_S))),
        LogInfo(msg="============================================================"),

        # First-level interpretations (T1, T2, T4)
        interp("t1_radar", "radar", "PossibleUAV"),
        interp("t2_rf", "rf", DEFAULT_RF_INTERP_LABEL),
        interp("t4_eo", "eo", "ConfirmedAerialObject"),

        # Time-windowed joins (T3, T5). T5 emits the ConfirmedThreat, whose TTL
        # is the tunable one; T3's intermediate CandidateTarget keeps the node
        # default, which is adequate for an internal step. T3 gets its own
        # window when T3_WINDOW_S is set.
        join("t3_candidate", "PossibleUAV", "LikelyDroneLink",
             "CandidateTarget", sync_s=T3_WINDOW_S),
        join("t5_threat", "CandidateTarget", "ConfirmedAerialObject",
             "ConfirmedThreat", emit_ttl=LaunchConfiguration("threat_ttl_s")),

        # Mission release, human-in-the-loop (T6)
        Node(
            package=PKG, executable="mission_transition_node",
            name="t6_mission", output="screen", emulate_tty=True,
            parameters=[{
                "sync_threshold_s": LaunchConfiguration("sync_threshold_s"),
                "mission_ttl_s": LaunchConfiguration("mission_ttl_s"),
                "use_sim_time": True,
            }],
        ),

        # Dispatch: mission -> vehicle tasks (T7)
        Node(
            package=PKG, executable="dispatch_transition_node",
            name="t7_dispatch", output="screen", emulate_tty=True,
            parameters=[{"use_sim_time": True}],
        ),
    ])