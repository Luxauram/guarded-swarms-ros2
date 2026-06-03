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

@file uav_pipeline.launch.py

Guarded Swarms software pipeline for UAV (R1 from paper) - PX4 + Gazebo required.

This launch file starts the ROS 2 software layers only.
PX4 SITL and the micro-ROS agent must be started separately before this launch.

Prerequisites (start in order before launching this file):
  Terminal 1:
    __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia \\
      MESA_GL_VERSION_OVERRIDE=4.5 make px4-gui-uav
    # At pxh> prompt:
    #   param set COM_ARM_WO_GPS 1
    #   param set SYS_HAS_MAG 0
    #   param set COM_RC_IN_MODE 1
    #   param set NAV_RCL_ACT 0
    #   param set NAV_DLL_ACT 0
    #   param set COM_RCL_EXCEPT 4
    #   param save
    #   commander takeoff

  Terminal 2:
    make ros2-agent

  Terminal 3 (this launch):
    ros2 launch guarded_swarms_bringup uav_pipeline.launch.py

Nodes launched by this file:
  - offboard_control_node  : UAV hover control via PX4 offboard mode
  - px4_safety_bridge_node : reads IMU, battery, altitude from PX4 uORB
  - safety_board_node      : OR-logic veto (staleness=5s for PX4 latency)
  - command_bridge_node    : AuthToken -> actuator_cmd_raw
  - coordinator_node       : digital arbitration
  - agent_node x4          : agents A, B, C, D

Monitor:
  ros2 topic echo /actuator_cmd_safe
  ros2 topic echo /safety_status
  ros2 topic echo /drone/altitude

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
    # UAV Offboard Control
    # =========================================================================

    offboard_control_node = Node(
        package="guarded_swarms_control",
        executable="offboard_control_node",
        name="offboard_control_node",
        output="screen",
        emulate_tty=True,
    )

    # =========================================================================
    # PX4 Safety Bridge (reads real sensor data from PX4 uORB)
    # =========================================================================

    px4_safety_bridge_node = Node(
        package="guarded_swarms_control",
        executable="px4_safety_bridge_node",
        name="px4_safety_bridge_node",
        output="screen",
        parameters=[{
            "lidar_topic": "/world/default/model/x500_lidar_front_0/link/lidar_sensor_link/sensor/lidar/scan",
        }],
        emulate_tty=True,
    )

    # =========================================================================
    # Analog Safety Enforcement Layer (tuned for UAV - altitude check active)
    # =========================================================================

    safety_board_node = Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board_node",
        output="screen",
        parameters=[{
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
            {"coordinator_id": "coordinator_R1"},
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
        LogInfo(msg="Guarded Swarms - UAV Pipeline (R1 from paper)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereqs: PX4 SITL running + micro-ROS agent running"),
        LogInfo(msg="Sensor data: IMU + battery + altitude from PX4 uORB"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /drone/altitude"),
        LogInfo(msg="============================================================"),
        offboard_control_node,
        px4_safety_bridge_node,
        safety_board_node,
        command_bridge_node,
        coordinator_node,
        agent_A,
        agent_B,
        agent_C,
        agent_D,
    ])