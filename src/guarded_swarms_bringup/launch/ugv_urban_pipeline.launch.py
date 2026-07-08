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

@file ugv_urban_pipeline.launch.py

Guarded Swarms - UGV Urban Pipeline (R2 scenario from paper).

Launches all ROS2 nodes for the UGV urban scenario:
  - ros_gz_bridge: Gazebo lidar -> ROS2
  - rover_control_node: autonomous waypoint patrol (arms + moves the rover)
  - px4_safety_bridge_node: PX4 sensors + lidar -> /drone/proximity
  - safety_board_node: OR-logic veto (altitude disabled for rover)
  - command_bridge_node: AuthToken -> /actuator_cmd_raw
  - coordinator_node + 4 agents: digital coordination layer

Prerequisites (start manually before this launch):
  Terminal 1: make px4-gui-ugv-urban
              -> wait for pxh>, no manual arming needed (rover_control_node
                 force-arms automatically 5s after this launch starts)
  Terminal 2: make ros2-agent
  Terminal 3: ros2 launch guarded_swarms_bringup ugv_urban_pipeline.launch.py

Monitor:
  ros2 topic echo /actuator_cmd_safe   # 0.0 = proximity veto active
  ros2 topic echo /drone/proximity     # lidar distance reading
Model: PX4's stock r1_rover with frontal lidar overlaid via 'make setup-ugv'.
Airframe: PX4's original 4009_gz_r1_rover (unchanged).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
LIDAR_TOPIC = (
    "/world/urban_ugv/model/r1_rover_0"
    "/link/lidar_sensor_link/sensor/lidar/scan"
)
def generate_launch_description():
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

    rover_control_node = Node(
        package="guarded_swarms_control",
        executable="rover_control_node",
        name="rover_control_node",
        output="screen",
        emulate_tty=True,
    )

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

    command_bridge_node = Node(
        package="guarded_swarms_control",
        executable="command_bridge_node",
        name="command_bridge_node",
        output="screen",
        emulate_tty=True,
    )

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

    return LaunchDescription([
        arbitration_mode_arg,
        num_agents_arg,
        priority_A_arg,
        priority_B_arg,
        priority_C_arg,
        priority_D_arg,
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - UGV Urban Pipeline (R2 from paper)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereqs: make px4-gui-ugv-urban + make ros2-agent"),
        LogInfo(msg="Rover will auto-arm and start patrol in ~5s"),
        LogInfo(msg="Safety: altitude DISABLED (rover), proximity ACTIVE"),
        LogInfo(msg="Expected: digital tokens approved, analog VETO on proximity"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /drone/proximity"),
        LogInfo(msg="============================================================"),
        lidar_bridge_node,
        rover_control_node,
        px4_safety_bridge_node,
        safety_board_node,
        command_bridge_node,
        coordinator_node,
        agent_A,
        agent_B,
        agent_C,
        agent_D,
    ])