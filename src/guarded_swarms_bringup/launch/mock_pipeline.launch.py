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

@file mock_pipeline.launch.py

Analog Safety Board alone - no PX4, no Gazebo required.

Brings up the safety board in isolation from the digital layer. This is the
infrastructure the resilience tests run against: each test publishes its own
sensor streams and proposed actuator command, and checks the board's verdicts.

Launches:
  - safety_board_node    : OR-logic veto on actuator commands

For a standalone demo with generated sensor faults, use
`make demo-safety-sensors` (the mock_sensor_publisher) alongside it.

Monitor pipeline output:
  ros2 topic echo /actuator_cmd_safe   # cleared value, or 0.0 = vetoed
  ros2 topic echo /safety_status       # 1.0 = safe,    0.0 = unsafe

Usage:
  ros2 launch guarded_swarms_bringup mock_pipeline.launch.py
"""

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node


def generate_launch_description():

    # =========================================================================
    # Analog Safety Enforcement Layer
    # =========================================================================

    safety_board_node = Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board_node",
        output="screen",
        emulate_tty=True,
    )

    # =========================================================================
    # Launch Description
    # =========================================================================

    return LaunchDescription([
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - Safety Board (Mock Sensors)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Analog layer:   safety_board"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /safety_status"),
        LogInfo(msg="============================================================"),
        safety_board_node,
    ])