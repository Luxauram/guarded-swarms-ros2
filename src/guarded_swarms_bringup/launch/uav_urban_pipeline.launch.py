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
@file uav_urban_pipeline.launch.py

Guarded Swarms - UAV Urban Pipeline (R1 scenario from paper).

Launches all ROS2 nodes for the UAV urban scenario:
  - ros_gz_bridge: Gazebo lidar -> ROS2
  - offboard_control_node: UAV hover control via PX4 offboard mode
  - px4_safety_bridge_node: PX4 sensors + lidar -> /drone/proximity
  - safety_board_node: OR-logic veto (altitude check active for UAV)
  - command_bridge_node: AuthToken -> /actuator_cmd_raw
  - coordinator_node + 4 agents: digital coordination layer

Prerequisites (start manually before this launch):
  Terminal 1: make px4-gui-uav-urban
              -> wait for pxh>, then run arming commands + commander takeoff
  Terminal 2: make ros2-agent
  Terminal 3: ros2 launch guarded_swarms_bringup uav_urban_pipeline.launch.py

Monitor:
  ros2 topic echo /actuator_cmd_safe   # 0.0 = proximity veto active
  ros2 topic echo /drone/proximity     # lidar distance reading
  ros2 topic echo /drone/altitude      # UAV altitude

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

LIDAR_TOPIC = (
    "/world/urban_uav/model/x500_lidar_front_0"
    "/link/lidar_sensor_link/sensor/lidar/scan"
)


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
    # Gazebo -> ROS2 lidar bridge
    # =========================================================================
    lidar_bridge_node = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="lidar_gz_bridge",
        output="screen",
        arguments=[
            LIDAR_TOPIC
            + "@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"
        ],
        emulate_tty=True,
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
    # PX4 Safety Bridge (reads from urban_uav lidar topic)
    # =========================================================================
    px4_safety_bridge_node = Node(
        package="guarded_swarms_control",
        executable="px4_safety_bridge_node",
        name="px4_safety_bridge_node",
        output="screen",
        parameters=[{
            "lidar_topic": LIDAR_TOPIC,
        }],
        emulate_tty=True,
    )

    # =========================================================================
    # Analog Safety Enforcement Layer
    # Altitude check active: UAV must stay within bounds
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
        LogInfo(msg="Guarded Swarms - UAV Urban Pipeline (R1 from paper)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereqs: make px4-gui-uav-urban + make ros2-agent"),
        LogInfo(msg="Safety: altitude ACTIVE, proximity ACTIVE (frontal lidar)"),
        LogInfo(msg="Expected: digital tokens approved, analog VETO on proximity"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /drone/proximity"),
        LogInfo(msg="          ros2 topic echo /drone/altitude"),
        LogInfo(msg="============================================================"),
        lidar_bridge_node,
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