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

Multi-vehicle pipeline: UAV (PX4 instance 0) + UGV (PX4 instance 1).

PX4 SITL assigns MAV_SYS_ID = instance + 1 and namespaces the uXRCE-DDS
topics per instance:

    instance 0  ->  MAV_SYS_ID 1  ->  /fmu/...
    instance 1  ->  MAV_SYS_ID 2  ->  /px4_1/fmu/...

All control nodes use relative topic paths, so a vehicle is selected by
setting the node namespace. The system ID must be set separately: it travels
inside VehicleCommand, not in the topic name, and a command addressed to the
wrong system is silently ignored by PX4.

Prereq: Gazebo and both PX4 instances already running (see 'make demo-swarm').
"""

from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node

UGV_NAMESPACE = "px4_1"
UGV_SYSTEM_ID = 2


def generate_launch_description():

    offboard_control_node = Node(
        package="guarded_swarms_control",
        executable="offboard_control_node",
        name="offboard_control_node",
        output="screen",
    )

    rover_control_node = Node(
        package="guarded_swarms_control",
        executable="rover_control_node",
        name="rover_control_node",
        namespace=UGV_NAMESPACE,
        parameters=[{"target_system": UGV_SYSTEM_ID}],
        output="screen",
    )

    return LaunchDescription([
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - Multi-Vehicle Pipeline"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="UAV: instance 0, MAV_SYS_ID 1, topics /fmu/..."),
        LogInfo(msg="UGV: instance 1, MAV_SYS_ID 2, topics /px4_1/fmu/..."),
        LogInfo(msg="============================================================"),
        offboard_control_node,
        rover_control_node,
    ])