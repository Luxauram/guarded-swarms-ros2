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
@file safety_demo.launch.py

Launch file for the Phase 2 safety enforcement demo.

Starts the SafetyBoard node and the mock sensor publisher, which cycles
through scripted violation scenarios to exercise the OR-logic veto behavior
without requiring a running Gazebo instance.

Nodes launched:
    safety_board_node       : analog safety enforcement layer
    mock_sensor_publisher   : simulated sensors cycling through violation scenarios

Typical usage:
    ros2 launch guarded_swarms_safety safety_demo.launch.py

    With custom thresholds:
    ros2 launch guarded_swarms_safety safety_demo.launch.py \\
        min_proximity_m:=2.0 max_pitch_deg:=25.0 min_battery_percent:=20.0

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    """
    Builds and returns the LaunchDescription for the safety enforcement demo.

    Declares all safety threshold arguments with their default values and
    wires them into the SafetyBoard node parameters. The mock sensor publisher
    requires no external configuration.

    @return LaunchDescription containing all declared arguments and nodes.
    """
    args = [
        DeclareLaunchArgument("min_proximity_m", default_value="1.5"),
        DeclareLaunchArgument("max_pitch_deg", default_value="30.0"),
        DeclareLaunchArgument("max_roll_deg", default_value="30.0"),
        DeclareLaunchArgument("min_battery_percent", default_value="15.0"),
        DeclareLaunchArgument("min_altitude_m", default_value="0.3"),
        DeclareLaunchArgument("max_altitude_m", default_value="50.0"),
    ]

    safety_board = Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board",
        output="screen",
        parameters=[
            {
                "min_proximity_m": LaunchConfiguration("min_proximity_m"),
                "max_pitch_deg": LaunchConfiguration("max_pitch_deg"),
                "max_roll_deg": LaunchConfiguration("max_roll_deg"),
                "min_battery_percent": LaunchConfiguration("min_battery_percent"),
                "min_altitude_m": LaunchConfiguration("min_altitude_m"),
                "max_altitude_m": LaunchConfiguration("max_altitude_m"),
            }
        ],
    )

    mock_sensors = Node(
        package="guarded_swarms_safety",
        executable="mock_sensor_publisher",
        name="mock_sensor_publisher",
        output="screen",
    )

    return LaunchDescription(args + [safety_board, mock_sensors])
