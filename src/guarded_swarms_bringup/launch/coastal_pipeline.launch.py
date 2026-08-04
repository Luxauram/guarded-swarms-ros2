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
@file coastal_pipeline.launch.py

Guarded Swarms - Coastal Surveillance Pipeline (2 UAV + 1 UGV).

Implements the swarm composition of Borghoff, Bottoni and Pareschi (2026),
IET Radar, Sonar and Navigation, Section 5.1: two UAV platforms responsible
for aerial interception and one UGV positioned near the shoreline for ground
observation and target recovery.

Architecture mapping
--------------------
The paper places the digital coordination layer centrally (a coordination node
hosts the TB-CSPN orchestration and the supervisor agents) while every platform
carries its own independent analogue safety envelope. This file mirrors that:

  shared, no namespace   coordinator_node + agents A..D
  per vehicle            lidar bridge, control node, px4_safety_bridge,
                         safety_board, command_bridge

Each safety board vetoes only its own vehicle's actuator command, with no
knowledge of the others. That decoupling is the point of the architecture, so
it is expressed structurally here rather than by configuration.

Instance mapping
----------------
PX4 SITL assigns MAV_SYS_ID = instance + 1 and namespaces its uXRCE-DDS topics
per instance. Instance 0 lives at the root:

  instance 0  MAV_SYS_ID 1  /fmu/...        UAV 0, model x500_lidar_front_0
  instance 1  MAV_SYS_ID 2  /px4_1/fmu/...  UAV 1, model x500_lidar_front_1
  instance 2  MAV_SYS_ID 3  /px4_2/fmu/...  UGV,   model r1_rover_2

The system ID is not carried in the topic name: it travels inside
VehicleCommand, so it must be set through the target_system parameter. A
command addressed to the wrong system is silently ignored and the vehicle
never arms.

Gazebo model names carry the instance suffix, so the lidar bridge topics do
too. If the launch order in 'make demo-coastal' changes, the suffixes change
with it. Verify with:  gz topic -l | grep -i lidar

Prerequisite: Gazebo, three uXRCE-DDS agents and three PX4 instances already
running. Use 'make demo-coastal'.

Monitor:
  ros2 topic echo /actuator_cmd_safe          UAV 0
  ros2 topic echo /px4_1/actuator_cmd_safe    UAV 1
  ros2 topic echo /px4_2/actuator_cmd_safe    UGV
  ros2 topic echo /px4_2/drone/proximity      UGV lidar distance

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node

# =============================================================================
# Scenario constants
#
# Keep WORLD in sync with COASTAL_WORLD in make/vars.mk, and the model names
# in sync with the launch order of 'make demo-coastal'.
# =============================================================================

WORLD = "coastal"

UAV0_MODEL = "x500_lidar_front_0"
UAV1_MODEL = "x500_lidar_front_1"
UGV_MODEL = "r1_rover_2"

UAV1_NAMESPACE = "px4_1"
UGV_NAMESPACE = "px4_2"

UAV0_SYSTEM_ID = 1
UAV1_SYSTEM_ID = 2
UGV_SYSTEM_ID = 3

# The two interceptors are stacked vertically so their patrol volumes do not
# overlap. Both stay below the 34 m town skyline, so the proximity veto stays
# meaningful for them as well.
UAV0_HOVER_M = 12.0
UAV1_HOVER_M = 20.0

# UAV spawn poses in world ENU (Gazebo), for the worker's ENU->NED conversion
# of a task target. Must match the spawn poses in make/px4.mk.
UAV0_SPAWN = (-24.0, -24.0)
UAV1_SPAWN = (24.0, -24.0)

# UGV spawn pose in world ENU (Gazebo), for the worker's ENU->NED conversion.
UGV_SPAWN = (-60.0, -14.0)

# Interception altitude held by a UAV once it has a task, so it closes on the
# target's horizontal position without descending onto it.
INTERCEPT_ALTITUDE_M = 15.0

# Rover patrol, NED relative to spawn, flattened as north,east,north,east...
# NED East = Gazebo X, so varying the second value drives along the shore.
# From X = -60 eastward, the road barrier at X = -8 triggers the veto.
UGV_WAYPOINTS = [0.0, 0.0, 0.0, 46.0]

LASERSCAN_BRIDGE = "@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"


def lidar_topic(model_name):
    return (f"/world/{WORLD}/model/{model_name}"
            "/link/lidar_sensor_link/sensor/lidar/scan")


def vehicle_stack(namespace, model_name, system_id, is_ground,
                  hover_altitude=None, waypoints=None, spawn=None):
    """Build the per-vehicle node set.

    namespace of None means the root namespace, used by PX4 instance 0.
    """
    ns = {} if namespace is None else {"namespace": namespace}
    scan = lidar_topic(model_name)

    nodes = [
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="lidar_gz_bridge",
            output="screen",
            arguments=[scan + LASERSCAN_BRIDGE],
            emulate_tty=True,
            **ns,
        ),
        Node(
            package="guarded_swarms_control",
            executable="px4_safety_bridge_node",
            name="px4_safety_bridge_node",
            output="screen",
            parameters=[{"lidar_topic": scan}],
            emulate_tty=True,
            **ns,
        ),
    ]

    # Altitude bounds are meaningful for an aircraft and not for a rover, so
    # the ground vehicle keeps only proximity, attitude and battery vetoes.
    safety_params = {"sensor_staleness_s": 5.0}
    if is_ground:
        safety_params.update({"min_altitude_m": -1.0, "max_altitude_m": 999.0})

    nodes.append(Node(
        package="guarded_swarms_safety",
        executable="safety_board_node",
        name="safety_board_node",
        output="screen",
        parameters=[safety_params],
        emulate_tty=True,
        **ns,
    ))

    if is_ground:
        nodes.append(Node(
            package="guarded_swarms_control",
            executable="ugv_worker_node",
            name="ugv_worker_node",
            output="screen",
            parameters=[{
                "target_system": system_id,
                "waypoints": waypoints,
                "spawn_x": spawn[0],
                "spawn_y": spawn[1],
            }],
            emulate_tty=True,
            **ns,
        ))
    else:
        nodes.append(Node(
            package="guarded_swarms_control",
            executable="uav_worker_node",
            name="uav_worker_node",
            output="screen",
            parameters=[{
                "target_system": system_id,
                "hover_altitude": hover_altitude,
                "intercept_altitude": INTERCEPT_ALTITUDE_M,
                "spawn_x": spawn[0],
                "spawn_y": spawn[1],
            }],
            emulate_tty=True,
            **ns,
        ))

    return nodes


def generate_launch_description():

    # =========================================================================
    # Per-vehicle stacks
    # =========================================================================

    uav0 = vehicle_stack(None, UAV0_MODEL, UAV0_SYSTEM_ID,
                         is_ground=False, hover_altitude=UAV0_HOVER_M,
                         spawn=UAV0_SPAWN)
    uav1 = vehicle_stack(UAV1_NAMESPACE, UAV1_MODEL, UAV1_SYSTEM_ID,
                         is_ground=False, hover_altitude=UAV1_HOVER_M,
                         spawn=UAV1_SPAWN)
    ugv = vehicle_stack(UGV_NAMESPACE, UGV_MODEL, UGV_SYSTEM_ID,
                        is_ground=True, waypoints=UGV_WAYPOINTS,
                        spawn=UGV_SPAWN)

    # =========================================================================
    # Launch Description
    # =========================================================================

    return LaunchDescription([
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - Coastal Pipeline (2 UAV + 1 UGV)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: make demo-coastal (Gazebo, 3 DDS agents, 3 PX4)"),
        LogInfo(msg="UAV 0: instance 0, sys 1, /fmu/...,       hover 12 m"),
        LogInfo(msg="UAV 1: instance 1, sys 2, /px4_1/fmu/..., hover 20 m"),
        LogInfo(msg="UGV:   instance 2, sys 3, /px4_2/fmu/..., shore patrol"),
        LogInfo(msg="Coordination is shared; each vehicle vetoes on its own"),
        LogInfo(msg="------------------------------------------------------------"),
        LogInfo(msg="Monitor:  ros2 topic echo /px4_2/actuator_cmd_safe"),
        LogInfo(msg="          ros2 topic echo /px4_2/drone/proximity"),
        LogInfo(msg="============================================================"),
        # ---------------------------------------------------------------
        # Simulation clock bridge (Gazebo -> ROS).
        # Every node runs with use_sim_time=true and subscribes to /clock.
        # Without this bridge no one publishes /clock, sim time is frozen at
        # zero, and every token's `t` field (and the time-windowed joins of
        # T3/T5) operate on a stopped clock. This must come up first so the
        # chain nodes have a valid clock before they emit their first tokens.
        # ---------------------------------------------------------------
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="clock_gz_bridge",
            output="screen",
            arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
            emulate_tty=True,
        ),
        *uav0,
        *uav1,
        *ugv,
    ])