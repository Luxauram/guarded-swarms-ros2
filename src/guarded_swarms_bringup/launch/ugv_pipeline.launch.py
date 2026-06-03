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

@file ugv_pipeline.launch.py

Guarded Swarms software pipeline for UGV (R2 from paper) - PX4 + Gazebo required.

This is the R2 scenario from the paper: the rover meets all digital coordination
conditions but is BLOCKED by the analog safety board due to a proximity violation
when an obstacle is detected within the lidar range threshold.

Differences from UAV pipeline:
  - No offboard_control_node (rover is controlled by PX4 directly)
  - safety_board_node has altitude check disabled (rover stays on ground)
  - px4_safety_bridge reads from rover lidar topic

Prerequisites (start in order before launching this file):
  Terminal 1:
    make setup-ugv  (run once)
    __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia \\
      MESA_GL_VERSION_OVERRIDE=4.5 make px4-gui-ugv

  Terminal 2:
    make ros2-agent

  Terminal 3 (this launch):
    ros2 launch guarded_swarms_bringup ugv_pipeline.launch.py

Monitor:
  ros2 topic echo /actuator_cmd_safe   # 0.0 when proximity veto active
  ros2 topic echo /drone/proximity     # lidar distance reading

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():

    # =========================================================================
    # Launch Arguments
    # =========================================================================

    arbitration_mode_arg = DeclareLaunchArgument(
        "arbitration_mode",
        default_value="priority",
        description="Arbitration mode: fcfs | priority | hybrid",
    )
    num_agents_arg = DeclareLaunchArgument(
        "num_agents", default_value="4", description="Number of agents (1-4)"
    )
    priority_A_arg = DeclareLaunchArgument(
        "priority_A", default_value="5", description="Priority for agent_A (0-10)"
    )
    priority_B_arg = DeclareLaunchArgument(
        "priority_B", default_value="5", description="Priority for agent_B (0-10)"
    )
    priority_C_arg = DeclareLaunchArgument(
        "priority_C", default_value="5", description="Priority for agent_C (0-10)"
    )
    priority_D_arg = DeclareLaunchArgument(
        "priority_D", default_value="5", description="Priority for agent_D (0-10)"
    )

    # =========================================================================
    # PX4 Safety Bridge (reads from rover lidar topic)
    # =========================================================================

    px4_safety_bridge_node = Node(
        package="guarded_swarms_control",
        executable="px4_safety_bridge_node",
        name="px4_safety_bridge_node",
        output="screen",
        parameters=[{
            "lidar_topic": "/world/rover/model/rover_differential_lidar_0/link/lidar_sensor_link/sensor/lidar/scan",
        }],
        emulate_tty=True,
    )

    # =========================================================================
    # Analog Safety Enforcement Layer
    # Altitude check disabled: rover operates at ground level (altitude ~ 0m)
    # Proximity check active: frontal lidar detects obstacles
    # =========================================================================

    safety_board_node = Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board_node",
        output="screen",
        parameters=[{
            "min_altitude_m": -1.0,
            "max_altitude_m": 999.0,
            "sensor_staleness_s": 5.0,
        }],
        emulate_tty=True,
    )

    # =========================================================================
    # Command Bridge
    # =========================================================================

    command_bridge_node = Node(
        package="guarded_swarms_control",
        executable="command_bridge_node",
        name="command_bridge_node",
        output="screen",
        emulate_tty=True,
    )

    # =========================================================================
    # Digital Coordination Layer
    # =========================================================================

    coordinator_node = Node(
        package="guarded_swarms_coordinator",
        executable="coordinator_node",
        name="coordinator_node",
        output="screen",
        parameters=[
            {"coordinator_id": "coordinator_R2"},
            {"arbitration_mode": LaunchConfiguration("arbitration_mode")},
        ],
        emulate_tty=True,
    )

    agent_A = Node(
        package="guarded_swarms_coordinator",
        executable="agent_node",
        name="agent_A_node",
        output="screen",
        parameters=[
            {"agent_id": "agent_A"},
            {"priority": LaunchConfiguration("priority_A")},
        ],
        emulate_tty=True,
    )
    agent_B = Node(
        package="guarded_swarms_coordinator",
        executable="agent_node",
        name="agent_B_node",
        output="screen",
        parameters=[
            {"agent_id": "agent_B"},
            {"priority": LaunchConfiguration("priority_B")},
        ],
        condition=IfCondition(
            PythonExpression(["int('", LaunchConfiguration("num_agents"), "') >= 2"])
        ),
        emulate_tty=True,
    )
    agent_C = Node(
        package="guarded_swarms_coordinator",
        executable="agent_node",
        name="agent_C_node",
        output="screen",
        parameters=[
            {"agent_id": "agent_C"},
            {"priority": LaunchConfiguration("priority_C")},
        ],
        condition=IfCondition(
            PythonExpression(["int('", LaunchConfiguration("num_agents"), "') >= 3"])
        ),
        emulate_tty=True,
    )
    agent_D = Node(
        package="guarded_swarms_coordinator",
        executable="agent_node",
        name="agent_D_node",
        output="screen",
        parameters=[
            {"agent_id": "agent_D"},
            {"priority": LaunchConfiguration("priority_D")},
        ],
        condition=IfCondition(
            PythonExpression(["int('", LaunchConfiguration("num_agents"), "') >= 4"])
        ),
        emulate_tty=True,
    )

    # =========================================================================
    # Launch Description
    # =========================================================================

    return LaunchDescription([
        arbitration_mode_arg,
        num_agents_arg,
        priority_A_arg,
        priority_B_arg,
        priority_C_arg,
        priority_D_arg,
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - UGV Pipeline (R2 from paper)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereqs: PX4 rover SITL running + micro-ROS agent running"),
        LogInfo(msg="Safety board: altitude check DISABLED (rover on ground)"),
        LogInfo(msg="Safety board: proximity check ACTIVE (frontal lidar)"),
        LogInfo(msg="Expected: digital tokens approved, analog VETO on proximity"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /drone/proximity"),
        LogInfo(msg="============================================================"),
        px4_safety_bridge_node,
        safety_board_node,
        command_bridge_node,
        coordinator_node,
        agent_A,
        agent_B,
        agent_C,
        agent_D,
    ])