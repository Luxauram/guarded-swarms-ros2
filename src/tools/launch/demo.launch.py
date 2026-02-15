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
@file demo.launch.py

ROS 2 launch file for guarded swarms coordination system demonstration.

This launch file orchestrates a complete multi-agent coordination demo by
launching all necessary nodes in a single command. It provides configurable
parameters for testing different coordination scenarios and arbitration policies.

Components launched:
- 1 coordinator node (spatial arbitration and token validation)
- 4 agent nodes (A, B, C, D) publishing geometry tokens
- All nodes with configurable parameters for various test scenarios

Launch Examples:
    # Default configuration (priority mode, 4 agents)
    ros2 launch guarded_swarms_coordinator demo.launch.py

    # FCFS arbitration mode
    ros2 launch guarded_swarms_coordinator demo.launch.py \\
        arbitration_mode:=fcfs

    # Custom priorities (emergency scenario)
    ros2 launch guarded_swarms_coordinator demo.launch.py \\
        priority_A:=10 priority_B:=5 priority_C:=5 priority_D:=3

    # Hybrid mode with custom threshold
    ros2 launch guarded_swarms_coordinator demo.launch.py \\
        arbitration_mode:=hybrid

    # Subset of agents
    ros2 launch guarded_swarms_coordinator demo.launch.py \\
        num_agents:=2

Available Parameters:
    arbitration_mode   - Coordination policy: fcfs | priority | hybrid (default: priority)
    coordinator_id     - Coordinator identifier (default: coordinator_R1)
    num_agents         - Number of agents to launch: 2-4 (default: 4)
    priority_A/B/C/D   - Agent priority levels: 0-10 (default: 5)

Note: To launch the dashboard, run separately:
    ros2 run guarded_swarms_coordinator dashboard

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    """
    Generates launch description for guarded swarms coordination demo.

    Creates a multi-agent system with configurable arbitration policies
    and priority levels for testing various coordination scenarios.

    @return LaunchDescription object for ROS 2 launch system
    """

    # ========================================================================
    # Launch Arguments - Arbitration Configuration
    # ========================================================================

    arbitration_mode_arg = DeclareLaunchArgument(
        "arbitration_mode",
        default_value="priority",
        description="Arbitration mode: fcfs | priority | hybrid",
    )

    coordinator_id_arg = DeclareLaunchArgument(
        "coordinator_id",
        default_value="coordinator_R1",
        description="Unique identifier for the coordinator node",
    )

    num_agents_arg = DeclareLaunchArgument(
        "num_agents", default_value="4", description="Number of agents to launch (2-4)"
    )

    # ========================================================================
    # Launch Arguments - Agent Priorities
    # ========================================================================

    priority_A_arg = DeclareLaunchArgument(
        "priority_A",
        default_value="5",
        description="Priority level for agent_A (0-10, higher = more important)",
    )

    priority_B_arg = DeclareLaunchArgument(
        "priority_B",
        default_value="5",
        description="Priority level for agent_B (0-10, higher = more important)",
    )

    priority_C_arg = DeclareLaunchArgument(
        "priority_C",
        default_value="5",
        description="Priority level for agent_C (0-10, higher = more important)",
    )

    priority_D_arg = DeclareLaunchArgument(
        "priority_D",
        default_value="5",
        description="Priority level for agent_D (0-10, higher = more important)",
    )

    # ========================================================================
    # Nodes - Coordinator
    # ========================================================================

    coordinator_node = Node(
        package="guarded_swarms_coordinator",
        executable="coordinator_node.py",
        name="coordinator_node",
        output="screen",
        parameters=[
            {"coordinator_id": LaunchConfiguration("coordinator_id")},
            {"arbitration_mode": LaunchConfiguration("arbitration_mode")},
        ],
        emulate_tty=True,
    )

    # ========================================================================
    # Nodes - Agents
    # ========================================================================

    agent_A = Node(
        package="guarded_swarms_coordinator",
        executable="agent_node.py",
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
        executable="agent_node.py",
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
        executable="agent_node.py",
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
        executable="agent_node.py",
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

    # ========================================================================
    # Launch Description Assembly
    # ========================================================================

    return LaunchDescription(
        [
            arbitration_mode_arg,
            coordinator_id_arg,
            num_agents_arg,
            priority_A_arg,
            priority_B_arg,
            priority_C_arg,
            priority_D_arg,
            LogInfo(msg="========================================"),
            LogInfo(msg="Guarded Swarms Coordination System"),
            LogInfo(msg="========================================"),
            LogInfo(msg="Launching coordinator and agent nodes..."),
            coordinator_node,
            agent_A,
            agent_B,
            agent_C,
            agent_D,
            LogInfo(msg="All nodes launched successfully"),
            LogInfo(msg="Run 'ros2 run guarded_swarms_coordinator dashboard' for visualization"),
        ]
    )
