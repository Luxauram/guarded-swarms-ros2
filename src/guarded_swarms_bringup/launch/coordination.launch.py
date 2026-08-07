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
@file coordination.launch.py
Guarded Swarms - the coordination and scenario layer, over already-running
vehicles.

This is the second half of the coastal case study. coastal_pipeline.launch.py
brings up the physical/safety layer (per-vehicle bridges, safety boards and
worker agents); this file brings up everything that turns those vehicles into a
mission-driven swarm:

  sensing   the four consultant agents (radar, RF, acoustic, EO) that
            synthesise observations from the target ground truth (IET Sec 5.1)
  tbcspn    the TB-CSPN transition chain T1-T7 that turns observations into an
            authorised, dispatched mission
  intruder  the hostile aerial target the whole chain reacts to

WHY A SEPARATE LAYER
====================
The physical layer and this coordination layer are kept in two launches, and
started in two steps, on purpose. The vehicles must be up, armed and holding
their patrol state before the scenario begins, so that the first observation
reaches a fully-initialised transition chain on a settled simulation clock.
Folding everything into one launch would hide that ordering; keeping it explicit
makes the run reproducible, which is the property the evaluation depends on.

STARTUP ORDER WITHIN THIS LAYER
===============================
sensing and tbcspn are passive on startup: they subscribe and wait, so they are
started immediately and do no harm before data arrives. The intruder is the only
active element, and it holds at its spawn point for `start_delay_s` before
ingress (its own parameter, not a launch-level timer). That delay is what lets
sensing and the transition chain finish initialising before the first
observation is produced. The EO agent reads its carrier UAV's live pose from a
PX4 topic that is published from spawn, so it needs no airborne UAV to start; by
the time the intruder is in range the UAV is already at altitude.

PARAMETRIC BY DESIGN
====================
The counterfactual trajectories of the paper (IET Sec 5.3) are meant to be
different invocations of this one file, not different code. The arguments below
expose the knobs those counterfactuals turn:

  - loss of modality (Group 4b): radar:=false | rf:=false | acoustic:=false |
    eo:=false drops one consultant and lets the chain degrade.
  - fusion window sweep: sync_threshold_s:= widens or narrows the joins.
  - ingress variation: speed_mps:= and start_delay_s:= reshape the approach.

The conflicting-interpretation counterfactual is driven by the RF_LABEL
environment variable, not a launch argument: tbcspn.launch.py reads it at import
time (a launch-argument substitution does not reliably resolve inside a node's
parameter dict, which is why the environment variable exists). Set it on the
command line, e.g.  RF_LABEL=LikelyCivilianTraffic make demo-coordination.

Prereq: the physical layer must already be running, i.e.
  make demo-coastal
Then, in a second terminal:
  make demo-coordination

Usage (direct):
  ros2 launch guarded_swarms_bringup coordination.launch.py
  ros2 launch guarded_swarms_bringup coordination.launch.py eo:=false
  ros2 launch guarded_swarms_bringup coordination.launch.py \\
      speed_mps:=14.0 start_delay_s:=10.0
  RF_LABEL=LikelyCivilianTraffic \\
      ros2 launch guarded_swarms_bringup coordination.launch.py

Monitor:
  ros2 topic echo /obs_tokens     --field source     observations by modality
  ros2 topic echo /interp_tokens  --field label      interpretations / threats
  ros2 topic echo /mission_tokens                    released missions
  ros2 topic echo /vehicle_tasks                     dispatched tasks

@author Luca D'Aurizio
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            LogInfo)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

SENSING_PKG = "guarded_swarms_sensing"
TBCSPN_PKG = "guarded_swarms_tbcspn"
BRINGUP_PKG = "guarded_swarms_bringup"


def _include(pkg, launch_file, launch_arguments=None):
    """Include another package's launch file, forwarding launch arguments.

    launch_arguments is a dict of name -> substitution, passed through so this
    layer's arguments reach the included files unchanged.
    """
    path = os.path.join(
        get_package_share_directory(pkg), "launch", launch_file)
    items = None
    if launch_arguments is not None:
        items = [(k, v) for k, v in launch_arguments.items()]
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(path),
        launch_arguments=items,
    )


def generate_launch_description():
    # -------------------------------------------------------------------------
    # Sensing arguments: per-modality enable flags (loss-of-modality metric)
    # and the RF interpretation label (conflicting-interpretation counterfactual).
    # -------------------------------------------------------------------------
    radar_arg = DeclareLaunchArgument(
        "radar", default_value="true",
        description="Launch the coastal radar agent.")
    rf_arg = DeclareLaunchArgument(
        "rf", default_value="true",
        description="Launch the RF monitoring agent.")
    acoustic_arg = DeclareLaunchArgument(
        "acoustic", default_value="true",
        description="Launch the acoustic buoy agent.")
    eo_arg = DeclareLaunchArgument(
        "eo", default_value="true",
        description="Launch the UAV-mounted EO agent.")

    # -------------------------------------------------------------------------
    # TB-CSPN temporal arguments (fusion window and token validities). Forwarded
    # to tbcspn.launch.py, which documents each one.
    # -------------------------------------------------------------------------
    sync_threshold_arg = DeclareLaunchArgument(
        "sync_threshold_s", default_value="3.0",
        description="Fusion-window half-width shared by T3, T5 and T6.")
    threat_ttl_arg = DeclareLaunchArgument(
        "threat_ttl_s", default_value="10.0",
        description="Validity (seconds) of an emitted ConfirmedThreat.")
    mission_ttl_arg = DeclareLaunchArgument(
        "mission_ttl_s", default_value="10.0",
        description="Validity (seconds) of a released InterceptMission.")

    # -------------------------------------------------------------------------
    # Intruder arguments: ingress trajectory and the start delay that lets the
    # coordination chain come up before the target moves.
    # -------------------------------------------------------------------------
    speed_arg = DeclareLaunchArgument(
        "speed_mps", default_value="8.0",
        description="Intruder cruise speed along the ingress leg.")
    start_delay_arg = DeclareLaunchArgument(
        "start_delay_s", default_value="20.0",
        description="Quiet hold before ingress, so sensing and TB-CSPN are up "
                    "before the first observation is produced.")

    # -------------------------------------------------------------------------
    # Included layers
    # -------------------------------------------------------------------------
    sensing = _include(SENSING_PKG, "sensing.launch.py", {
        "radar": LaunchConfiguration("radar"),
        "rf": LaunchConfiguration("rf"),
        "acoustic": LaunchConfiguration("acoustic"),
        "eo": LaunchConfiguration("eo"),
    })

    tbcspn = _include(TBCSPN_PKG, "tbcspn.launch.py", {
        "sync_threshold_s": LaunchConfiguration("sync_threshold_s"),
        "threat_ttl_s": LaunchConfiguration("threat_ttl_s"),
        "mission_ttl_s": LaunchConfiguration("mission_ttl_s"),
    })

    intruder = _include(BRINGUP_PKG, "intruder.launch.py", {
        "speed_mps": LaunchConfiguration("speed_mps"),
        "start_delay_s": LaunchConfiguration("start_delay_s"),
    })

    return LaunchDescription([
        radar_arg,
        rf_arg,
        acoustic_arg,
        eo_arg,
        sync_threshold_arg,
        threat_ttl_arg,
        mission_ttl_arg,
        speed_arg,
        start_delay_arg,
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - Coordination + Scenario layer"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: make demo-coastal (vehicles up, armed, patrolling)"),
        LogInfo(msg="Sensing + TB-CSPN start now; intruder ingresses after "
                    "start_delay_s"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /interp_tokens --field label"),
        LogInfo(msg="          ros2 topic echo /mission_tokens"),
        LogInfo(msg="          ros2 topic echo /vehicle_tasks"),
        LogInfo(msg="============================================================"),
        sensing,
        tbcspn,
        intruder,
    ])
