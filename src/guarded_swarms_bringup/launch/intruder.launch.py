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
@file intruder.launch.py

Guarded Swarms - hostile aerial target for the coastal scenario.

Kept in its own launch file rather than folded into coastal_pipeline so that
the adversary can be started, stopped and re-parameterised independently of the
swarm. The counterfactual trajectories of the paper (IET Section 5.3) are meant
to be different invocations of this file, not different code.

Two bridges are needed because the intruder is driven kinematically rather
than by PX4:

  ROS -> GZ   /model/intruder/cmd_vel     commanded velocity
  GZ  -> ROS  /model/intruder/odometry    ground truth for the consultant agents

Prereq: 'make demo-coastal' (or at least scripts/sim/gz_launch.sh coastal).

Usage:
  ros2 launch guarded_swarms_bringup intruder.launch.py
  ros2 launch guarded_swarms_bringup intruder.launch.py speed_mps:=14.0 \\
      start_delay_s:=5.0

@author Luca D'Aurizio
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

CMD_VEL_TOPIC = "/model/intruder/cmd_vel"
POSE_TOPIC = "/model/intruder/pose"


def generate_launch_description():

    # Ingress from the open sea, straight run toward the shoreline.
    # Defaults place the target well outside the town skyline so the approach
    # is unobstructed and the sensing layer sees a clean track.
    args = [
        DeclareLaunchArgument("ingress_x", default_value="0.0"),
        DeclareLaunchArgument("ingress_y", default_value="180.0"),
        DeclareLaunchArgument("ingress_z", default_value="15.0"),
        DeclareLaunchArgument("target_x", default_value="0.0"),
        DeclareLaunchArgument("target_y", default_value="10.0"),
        DeclareLaunchArgument("target_z", default_value="15.0"),
        DeclareLaunchArgument(
            "speed_mps", default_value="8.0",
            description="Cruise speed along the ingress leg"),
        DeclareLaunchArgument(
            "start_delay_s", default_value="20.0",
            description="Quiet period before ingress begins, so the swarm has "
                        "reached its patrol state first"),
        DeclareLaunchArgument("arrival_radius_m", default_value="3.0"),
    ]

    # ROS -> GZ. The ']' suffix marks the direction: without it the bridge
    # would subscribe on the Gazebo side and the model would never move.
    cmd_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="intruder_cmd_bridge",
        output="screen",
        arguments=[CMD_VEL_TOPIC + "@geometry_msgs/msg/Twist]gz.msgs.Twist"],
        emulate_tty=True,
    )

    # GZ -> ROS, ground truth.
    pose_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="intruder_pose_bridge",
        output="screen",
        arguments=[POSE_TOPIC + "@geometry_msgs/msg/PoseStamped[gz.msgs.Pose"],
        emulate_tty=True,
    )

    intruder_node = Node(
        package="guarded_swarms_control",
        executable="intruder_node",
        name="intruder_node",
        output="screen",
        parameters=[{
            "ingress_x": LaunchConfiguration("ingress_x"),
            "ingress_y": LaunchConfiguration("ingress_y"),
            "ingress_z": LaunchConfiguration("ingress_z"),
            "target_x": LaunchConfiguration("target_x"),
            "target_y": LaunchConfiguration("target_y"),
            "target_z": LaunchConfiguration("target_z"),
            "speed_mps": LaunchConfiguration("speed_mps"),
            "start_delay_s": LaunchConfiguration("start_delay_s"),
            "arrival_radius_m": LaunchConfiguration("arrival_radius_m"),
            "cmd_vel_topic": CMD_VEL_TOPIC,
            "pose_topic": POSE_TOPIC,
        }],
        emulate_tty=True,
    )

    return LaunchDescription([
        *args,
        LogInfo(msg="============================================================"),
        LogInfo(msg="Guarded Swarms - Intruder (hostile aerial target)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg="Prereq: the coastal world must already be running"),
        LogInfo(msg="Ingress begins after start_delay_s, then a straight run"),
        LogInfo(msg="Monitor:  ros2 topic echo /intruder/ground_truth"),
        LogInfo(msg="          ros2 topic echo /intruder/active"),
        LogInfo(msg="============================================================"),
        cmd_bridge,
        pose_bridge,
        intruder_node,
    ])
