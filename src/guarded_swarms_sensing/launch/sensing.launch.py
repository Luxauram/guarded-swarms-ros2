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
@file sensing.launch.py
Guarded Swarms - the sensor-driven layer.
Brings up the four consultant agents of the coastal surveillance scenario
(IET Section 5.1) in one command, each configured from its own YAML file under
config/. Replaces the six-terminal workflow used while developing the agents.
Every agent runs with use_sim_time (set in the YAML): the real-time factor is
below 1, so token timestamps and the latencies derived from them must be on the
simulation clock to be comparable between runs.
The agents synthesise observations from target ground truth using per-modality
coverage and error models. The coverage geometry is a simulation model, not
specified by the paper.
Each modality can be switched off independently (radar:=false, rf:=false,
acoustic:=false, eo:=false). This is what drives the loss-of-modality metric
(Group 4b): disabling one modality and measuring how the detection chain
degrades. eo:=false additionally reproduces the EO-absent limiting case of the
stale-EO counterfactual.
Prereq: the coastal world and at least one target must be running, i.e.
'make demo-coastal' and the intruder launch. The EO agent additionally needs
its carrier UAV airborne, since it points its camera from the live UAV pose.
Usage:
  ros2 launch guarded_swarms_sensing sensing.launch.py
  ros2 launch guarded_swarms_sensing sensing.launch.py eo:=false
  ros2 launch guarded_swarms_sensing sensing.launch.py radar:=false
@author Luca D'Aurizio
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
PKG = "guarded_swarms_sensing"
def generate_launch_description():
    cfg = os.path.join(get_package_share_directory(PKG), "config")
    # Per-modality enable flags. Default true; set false to drop one modality
    # for the loss-of-modality metric (Group 4b).
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
        description="Whether to launch the UAV-mounted EO agent. Set false to "
                    "run the fixed modalities only (e.g. before a UAV is up).")
    radar = Node(
        package=PKG, executable="radar_agent_node", name="radar_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("radar")),
        parameters=[os.path.join(cfg, "radar_agent.yaml")],
    )
    rf = Node(
        package=PKG, executable="rf_agent_node", name="rf_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("rf")),
        parameters=[os.path.join(cfg, "rf_agent.yaml")],
    )
    acoustic = Node(
        package=PKG, executable="acoustic_agent_node", name="acoustic_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("acoustic")),
        parameters=[os.path.join(cfg, "acoustic_agent.yaml")],
    )
    eo = Node(
        package=PKG, executable="eo_agent_node", name="eo_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("eo")),
        parameters=[os.path.join(cfg, "eo_agent_uav0.yaml")],
    )
    return LaunchDescription([
        radar_arg,
        rf_arg,
        acoustic_arg,
        eo_arg,
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - sensor-driven layer (4 consultant agents)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: coastal world + intruder running; UAV up for EO"),
        LogInfo(msg="Monitor:  ros2 topic echo /obs_tokens --field source"),
        LogInfo(msg="============================================================"),
        radar,
        rf,
        acoustic,
        eo,
    ])