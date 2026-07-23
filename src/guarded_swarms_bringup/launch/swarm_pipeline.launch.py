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
@file swarm_pipeline.launch.py

Guarded Swarms - Multi-Vehicle Pipeline (UAV + UGV in one Gazebo world).

Architecture mapping
--------------------
The paper places the digital coordination layer centrally (one node hosts the
TB-CSPN orchestration and the supervisor agents) while every vehicle carries
its own independent analogue safety envelope. This launch file mirrors that:

  shared, no namespace   coordinator_node + agents A..D
  per vehicle            lidar bridge, control node, px4_safety_bridge,
                         safety_board, command_bridge

Each safety board therefore vetoes its own vehicle's actuator commands
without any knowledge of the other, which is exactly the decoupling the
architecture claims.

Namespacing
-----------
PX4 SITL namespaces its uXRCE-DDS topics per instance and assigns
MAV_SYS_ID = instance + 1:

    instance 0  ->  MAV_SYS_ID 1  ->  /fmu/...
    instance 1  ->  MAV_SYS_ID 2  ->  /px4_1/fmu/...

Instance 0 lives at the root, so the UAV stack runs unnamespaced and the UGV
stack runs under /px4_1. All nodes use relative topic names, so the namespace
alone separates the two vehicles' topics. The system ID is NOT carried in the
topic name: it travels inside VehicleCommand, so it must be set separately via
the target_system parameter, or PX4 silently ignores the command.

Lidar topics come from Gazebo and are absolute by construction: they embed the
world and model name, which already differ between vehicles.

Prerequisite: Gazebo, the uXRCE-DDS agent and both PX4 instances must already
be running. Use 'make demo-swarm', which starts everything in the right order
and then launches this file.

Monitor:
  ros2 topic echo /actuator_cmd_safe          # UAV: 0.0 = veto active
  ros2 topic echo /px4_1/actuator_cmd_safe    # UGV: 0.0 = veto active
  ros2 topic echo /drone/proximity            # UAV lidar distance
  ros2 topic echo /px4_1/drone/proximity      # UGV lidar distance

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

# =============================================================================
# Scenario constants
#
# Keep WORLD in sync with SWARM_WORLD in make/vars.mk. The model names are
# assigned by PX4 as <model>_<instance>, so they change if the launch order
# in 'make demo-swarm' changes. Verify with:
#     gz topic -l | grep -i lidar
# =============================================================================

WORLD = "urban_ugv"

UAV_MODEL = "x500_lidar_front_0"
UGV_MODEL = "r1_rover_1"

UGV_NAMESPACE = "px4_1"
UGV_SYSTEM_ID = 2

UAV_LIDAR_TOPIC = (
    f"/world/{WORLD}/model/{UAV_MODEL}"
    "/link/lidar_sensor_link/sensor/lidar/scan"
)

UGV_LIDAR_TOPIC = (
    f"/world/{WORLD}/model/{UGV_MODEL}"
    "/link/lidar_sensor_link/sensor/lidar/scan"
)

LASERSCAN_BRIDGE = "@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"


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
    # UAV stack - PX4 instance 0, root namespace
    # =========================================================================

    uav_lidar_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="uav_lidar_gz_bridge",
        output="screen",
        arguments=[UAV_LIDAR_TOPIC + LASERSCAN_BRIDGE],
        emulate_tty=True,
    )

    offboard_control_node = Node(
        package="guarded_swarms_control",
        executable="offboard_control_node",
        name="offboard_control_node",
        output="screen",
        emulate_tty=True,
    )

    uav_safety_bridge = Node(
        package="guarded_swarms_control",
        executable="px4_safety_bridge_node",
        name="px4_safety_bridge_node",
        output="screen",
        parameters=[{
            "lidar_topic": UAV_LIDAR_TOPIC,
        }],
        emulate_tty=True,
    )

    # Altitude check active: the UAV must stay within bounds.
    uav_safety_board = Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board_node",
        output="screen",
        parameters=[{
            "sensor_staleness_s": 5.0,
        }],
        emulate_tty=True,
    )

    uav_command_bridge = Node(
        package="guarded_swarms_control",
        executable="command_bridge_node",
        name="command_bridge_node",
        output="screen",
        emulate_tty=True,
    )

    # =========================================================================
    # UGV stack - PX4 instance 1, /px4_1 namespace
    # =========================================================================

    ugv_lidar_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="ugv_lidar_gz_bridge",
        namespace=UGV_NAMESPACE,
        output="screen",
        arguments=[UGV_LIDAR_TOPIC + LASERSCAN_BRIDGE],
        emulate_tty=True,
    )

    rover_control_node = Node(
        package="guarded_swarms_control",
        executable="rover_control_node",
        name="rover_control_node",
        namespace=UGV_NAMESPACE,
        output="screen",
        parameters=[{
            "target_system": UGV_SYSTEM_ID,
        }],
        emulate_tty=True,
    )

    ugv_safety_bridge = Node(
        package="guarded_swarms_control",
        executable="px4_safety_bridge_node",
        name="px4_safety_bridge_node",
        namespace=UGV_NAMESPACE,
        output="screen",
        parameters=[{
            "lidar_topic": UGV_LIDAR_TOPIC,
        }],
        emulate_tty=True,
    )

    # Altitude check disabled: a ground vehicle has no meaningful altitude
    # envelope, so only proximity, attitude and battery can veto.
    ugv_safety_board = Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board_node",
        namespace=UGV_NAMESPACE,
        output="screen",
        parameters=[{
            "min_altitude_m": -1.0,
            "max_altitude_m": 999.0,
            "sensor_staleness_s": 5.0,
        }],
        emulate_tty=True,
    )

    ugv_command_bridge = Node(
        package="guarded_swarms_control",
        executable="command_bridge_node",
        name="command_bridge_node",
        namespace=UGV_NAMESPACE,
        output="screen",
        emulate_tty=True,
    )

    # =========================================================================
    # Digital Coordination Layer - shared by the whole swarm
    # =========================================================================

    coordinator_node = Node(
        package="guarded_swarms_coordinator",
        executable="coordinator_node",
        name="coordinator_node",
        output="screen",
        parameters=[
            {"coordinator_id": "coordinator_swarm"},
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
        LogInfo(msg="Guarded Swarms - Multi-Vehicle Pipeline (UAV + UGV)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: make demo-swarm (Gazebo + agent + both PX4 instances)"),
        LogInfo(msg="UAV: instance 0, MAV_SYS_ID 1, topics /fmu/..."),
        LogInfo(msg="UGV: instance 1, MAV_SYS_ID 2, topics /px4_1/fmu/..."),
        LogInfo(msg="Coordination layer is shared; each vehicle vetoes on its own"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /px4_1/actuator_cmd_safe"),
        LogInfo(msg="============================================================"),
        # UAV
        uav_lidar_bridge,
        offboard_control_node,
        uav_safety_bridge,
        uav_safety_board,
        uav_command_bridge,
        # UGV
        ugv_lidar_bridge,
        rover_control_node,
        ugv_safety_bridge,
        ugv_safety_board,
        ugv_command_bridge,
        # Shared digital coordination layer
        coordinator_node,
        agent_A,
        agent_B,
        agent_C,
        agent_D,
    ])