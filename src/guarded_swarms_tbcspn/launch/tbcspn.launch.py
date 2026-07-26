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

Brings up all the transitions of Figure 4 in one command: the five detection
transitions (T1-T5) plus the mission-release transition (T6). Replaces the
one-terminal-per-transition workflow used while developing them.

The transitions are the same two generic nodes, instantiated with different
parameters, plus the mission node:
  T1  interpretation_node   radar -> PossibleUAV
  T2  interpretation_node   rf    -> LikelyDroneLink
  T4  interpretation_node   eo    -> ConfirmedAerialObject
  T3  candidate_transition  PossibleUAV + LikelyDroneLink -> CandidateTarget
  T5  candidate_transition  CandidateTarget + ConfirmedAerialObject
                              -> ConfirmedThreat
  T6  mission_transition     ConfirmedThreat + SupervisorAuth -> InterceptMission

All read/write the single shared /interp_tokens marking; T6 additionally reads
/auth_tokens and publishes /mission_tokens.

Prereq: the sensing layer must be producing /obs_tokens, i.e. the coastal
world, the intruder, and sensing.launch.py are already running.

Monitor:
  ros2 topic echo /interp_tokens  --field label
  ros2 topic echo /mission_tokens

Authorise (from a supervisor, or by hand for now):
  ros2 topic pub --once /auth_tokens guarded_swarms_msgs/msg/SupervisorAuth \\
    "{target_id: 'intruder', authorised_by: 'supervisor_luca', \\
      decision: 'authorise', ttl_s: 10.0}"

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node

PKG = "guarded_swarms_tbcspn"


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


def join(name, label_a, label_b, emit_label):
    """One time-windowed join transition (T3/T5)."""
    return Node(
        package=PKG, executable="candidate_transition_node", name=name,
        output="screen", emulate_tty=True,
        parameters=[{
            "label_a": label_a,
            "label_b": label_b,
            "emit_label": emit_label,
            "use_sim_time": True,
        }],
    )


def generate_launch_description():
    return LaunchDescription([
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - TB-CSPN coordination layer (T1-T6)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: sensing layer producing /obs_tokens"),
        LogInfo(msg="Monitor:  ros2 topic echo /interp_tokens --field label"),
        LogInfo(msg="          ros2 topic echo /mission_tokens"),
        LogInfo(msg="Authorise: ros2 topic pub --once /auth_tokens \\"),
        LogInfo(msg="  guarded_swarms_msgs/msg/SupervisorAuth \\"),
        LogInfo(msg="  \"{target_id: 'intruder', authorised_by: 'sup', \\"),
        LogInfo(msg="    decision: 'authorise', ttl_s: 10.0}\""),
        LogInfo(msg="============================================================"),

        # First-level interpretations
        interp("t1_radar", "radar", "PossibleUAV"),
        interp("t2_rf", "rf", "LikelyDroneLink"),
        interp("t4_eo", "eo", "ConfirmedAerialObject"),

        # Time-windowed joins
        join("t3_candidate", "PossibleUAV", "LikelyDroneLink", "CandidateTarget"),
        join("t5_threat", "CandidateTarget", "ConfirmedAerialObject",
             "ConfirmedThreat"),

        # Mission release, human-in-the-loop
        Node(
            package=PKG, executable="mission_transition_node",
            name="t6_mission", output="screen", emulate_tty=True,
            parameters=[{"use_sim_time": True}],
        ),

        # Dispatch: mission -> vehicle tasks
        Node(
            package=PKG, executable="dispatch_transition_node",
            name="t7_dispatch", output="screen", emulate_tty=True,
            parameters=[{"use_sim_time": True}],
        ),
    ])
