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
@file supervisor.launch.py

Guarded Swarms - the scripted supervisor.

Stands in for the human supervisor of T6 in automated runs: at the first
ConfirmedThreat of each target it waits AUTH_DELAY_S seconds of simulated time,
then issues one decision on /supervisor_auth. Interactive runs use the
supervisor console instead and do not start this launch.

CONFIGURATION
=============
Read from environment variables, like the other scenario knobs (RF_LABEL,
EO_DELAY_S, ...), so that a batch script can set them run by run:

  DECISION      authorise | deny | none                      default authorise
                deny is an explicit refusal (the "authorisation withheld"
                counterfactual); none issues no decision at all.
  AUTH_DELAY_S  supervisor decision time, simulated seconds   default 0.0
  AUTH_TTL_S    validity of the decision, seconds             default 15.0

An unset or empty variable takes the default.

Prereq: the scenario running (it provides /clock) and the coordination layer
(tbcspn.launch.py), whose T6 consumes the decisions.

Monitor:
  ros2 topic echo --qos-durability transient_local /supervisor_auth

@author Luca D'Aurizio
"""

import os

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node

PKG = "guarded_swarms_supervisor"

DECISIONS = ("authorise", "deny", "none")
DEFAULT_DECISION = "authorise"
DEFAULT_AUTH_DELAY_S = "0.0"
DEFAULT_AUTH_TTL_S = "15.0"


def env_text(name, default):
    """An environment variable, or the default when it is unset or empty."""
    return os.environ.get(name) or default


def env_seconds(name, default):
    """A numeric environment variable, in seconds, or the default."""
    raw = env_text(name, default)
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be a number of seconds, got '{raw}'") from None


def generate_launch_description():
    decision = env_text("DECISION", DEFAULT_DECISION)
    if decision not in DECISIONS:
        raise ValueError(
            f"DECISION must be one of {', '.join(DECISIONS)}, got '{decision}'")
    delay_s = env_seconds("AUTH_DELAY_S", DEFAULT_AUTH_DELAY_S)
    ttl_s = env_seconds("AUTH_TTL_S", DEFAULT_AUTH_TTL_S)

    return LaunchDescription([
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - scripted supervisor (decisions for T6)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg=f"Decision: {decision}, {delay_s:.2f} s (sim) after the "
                    f"first ConfirmedThreat, valid {ttl_s:.1f} s"),
        LogInfo(msg="Monitor:  ros2 topic echo --qos-durability transient_local "
                    "/supervisor_auth"),
        LogInfo(msg="============================================================"),

        Node(
            package=PKG, executable="scripted_supervisor_node",
            name="scripted_supervisor", output="screen", emulate_tty=True,
            parameters=[{
                "decision": decision,
                "decision_delay_s": delay_s,
                "ttl_s": ttl_s,
                "use_sim_time": True,
            }],
        ),
    ])