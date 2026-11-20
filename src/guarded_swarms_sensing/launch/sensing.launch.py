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
Brings up the four consultant agents of the coastal surveillance scenario in
one command, each configured from its own YAML file under config/.
Every agent runs with use_sim_time (set in the YAML): the real-time factor is
below 1, so token timestamps and the latencies derived from them must be on the
simulation clock to be comparable between runs.
The agents synthesise observations from target ground truth using per-modality
coverage and error models. The coverage geometry is a simulation model, not
part of the architecture.
Each modality can be switched off independently (radar:=false, rf:=false,
acoustic:=false, eo:=false). This is what drives the loss-of-modality runs:
disabling one modality and measuring how the detection chain degrades.
eo:=false additionally reproduces the EO-absent limiting case of the stale-EO
counterfactual.
Random draws: the SEED environment variable sets the seed of the run, and each
agent gets its own seed derived from it (radar SEED+1, rf SEED+2, acoustic
SEED+3, eo SEED+4), so one number reproduces the noise of all four. Without
SEED, a seed is drawn at random and logged.
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
import random
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
PKG = "guarded_swarms_sensing"
# Each agent's seed is the seed of the run plus its offset, so the four noise
# sequences differ while one number reproduces them all. Agent seeds are 32-bit.
SEED_OFFSETS = {"radar": 1, "rf": 2, "acoustic": 3, "eo": 4}
MAX_SEED = 2**32 - 1 - max(SEED_OFFSETS.values())
def run_seed():
    """The seed of the run from SEED, or one drawn at random if SEED is unset."""
    raw = os.environ.get("SEED")
    if not raw:
        return random.SystemRandom().randint(1, 2**30), True
    try:
        seed = int(raw)
    except ValueError:
        raise ValueError(f"SEED must be an integer, got '{raw}'") from None
    if not 1 <= seed <= MAX_SEED:
        raise ValueError(f"SEED must be between 1 and {MAX_SEED}, got {seed}")
    return seed, False
def generate_launch_description():
    cfg = os.path.join(get_package_share_directory(PKG), "config")
    seed, drawn = run_seed()
    # Per-modality enable flags. Default true; set false to drop one modality
    # for the loss-of-modality runs.
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
        parameters=[os.path.join(cfg, "radar_agent.yaml"),
                    {"seed": seed + SEED_OFFSETS["radar"]}],
    )
    rf = Node(
        package=PKG, executable="rf_agent_node", name="rf_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("rf")),
        parameters=[os.path.join(cfg, "rf_agent.yaml"),
                    {"seed": seed + SEED_OFFSETS["rf"]}],
    )
    acoustic = Node(
        package=PKG, executable="acoustic_agent_node", name="acoustic_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("acoustic")),
        parameters=[os.path.join(cfg, "acoustic_agent.yaml"),
                    {"seed": seed + SEED_OFFSETS["acoustic"]}],
    )
    eo = Node(
        package=PKG, executable="eo_agent_node", name="eo_agent_node",
        output="screen", emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("eo")),
        parameters=[os.path.join(cfg, "eo_agent_uav0.yaml"),
                    {"seed": seed + SEED_OFFSETS["eo"]}],
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
        LogInfo(msg=f"Seed of the run: {seed} "
                    f"({'drawn at random' if drawn else 'from SEED'}); "
                    f"agents use seed+1 to seed+4"),
        LogInfo(msg="Monitor:  ros2 topic echo /obs_tokens --field source"),
        LogInfo(msg="============================================================"),
        radar,
        rf,
        acoustic,
        eo,
    ])