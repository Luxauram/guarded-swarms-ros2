#!/usr/bin/env python3
"""
Copyright 2026 Luca D'Aurizio
Licensed under the Apache License, Version 2.0

@file mock_pipeline.launch.py

Full Guarded Swarms pipeline with mock sensors - no PX4, no Gazebo required.

Launches all software layers simultaneously:
  - coordinator_node    : digital arbitration (4 agents, priority mode)
  - agent_node x4       : agents A, B, C, D publishing geometry tokens
  - command_bridge_node : converts approved AuthTokens to actuator commands
  - safety_board_node   : OR-logic veto on actuator commands
  - mock_sensor_publisher: cycles through 6 sensor fault scenarios (10s each)

The two layers are deliberately decoupled:
  - The safety board has no knowledge of tokens
  - The coordinator has no knowledge of sensor readings

Monitor pipeline output:
  ros2 topic echo /actuator_cmd_raw    # 0.6 when token approved
  ros2 topic echo /actuator_cmd_safe   # 0.6 = cleared, 0.0 = vetoed
  ros2 topic echo /safety_status       # 1.0 = safe,    0.0 = unsafe

Usage:
  ros2 launch guarded_swarms_bringup mock_pipeline.launch.py
  ros2 launch guarded_swarms_bringup mock_pipeline.launch.py arbitration_mode:=fcfs
  ros2 launch guarded_swarms_bringup mock_pipeline.launch.py priority_A:=10 priority_B:=3
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
        "num_agents",
        default_value="4",
        description="Number of agents to launch (1-4)",
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
    # Command Bridge (digital → analog interface)
    # =========================================================================

    command_bridge_node = Node(
        package="guarded_swarms_control",
        executable="command_bridge_node",
        name="command_bridge_node",
        output="screen",
        emulate_tty=True,
    )

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

    mock_sensor_publisher = Node(
        package="guarded_swarms_safety",
        executable="mock_sensor_publisher",
        name="mock_sensor_publisher",
        output="screen",
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
        LogInfo(msg="Guarded Swarms - Full Pipeline (Mock Sensors)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Digital layer:  coordinator + 4 agents"),
        LogInfo(msg="Analog layer:   safety_board + mock_sensor_publisher"),
        LogInfo(msg="Bridge:         command_bridge (AuthToken -> actuator_cmd_raw)"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /safety_status"),
        LogInfo(msg="============================================================"),
        coordinator_node,
        agent_A,
        agent_B,
        agent_C,
        agent_D,
        command_bridge_node,
        safety_board_node,
        mock_sensor_publisher,
    ])