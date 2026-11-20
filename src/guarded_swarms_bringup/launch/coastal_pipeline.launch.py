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

Guarded Swarms - Coastal Surveillance Pipeline (N UAV + 1 UGV).

Implements the swarm composition of the coastal scenario: two UAV platforms
responsible for aerial interception and one UGV positioned near the shoreline
for ground observation and target recovery.

The fleet is described in config/coastal_fleet.yaml. A run flies its first
N_UAVS UAVs, an environment variable: 2 by default, the composition above,
and up to the number in the file for the scaling runs. The UAVs past the
first two are interceptors only, with the same per-vehicle nodes: the sensing
layer, and with it the EO camera carried by UAV 0, is the same for every
fleet.

Architecture mapping
--------------------
The architecture places the digital coordination layer centrally (the TB-CSPN
chain, brought up separately by tbcspn.launch.py) while every platform carries
its own independent analogue safety envelope. This file brings up the
per-vehicle side:

  per vehicle   lidar bridge, px4_safety_bridge, safety_board, worker
                (uav_worker or ugv_worker)

Each safety board vetoes only its own vehicle's actuator command, with no
knowledge of the others. That decoupling is the point of the architecture, so
it is expressed structurally here rather than by configuration. The worker is
the single command source per vehicle, which the board gates.

Instance mapping
----------------
PX4 SITL assigns MAV_SYS_ID = instance + 1 and namespaces its uXRCE-DDS topics
per instance. Instance 0 lives at the root:

  instance 0  MAV_SYS_ID 1  /fmu/...        UAV 0, model x500_lidar_front_0
  instance 1  MAV_SYS_ID 2  /px4_1/fmu/...  UAV 1, model x500_lidar_front_1
  instance 2  MAV_SYS_ID 3  /px4_2/fmu/...  UGV,   model r1_rover_2
  instance 3  MAV_SYS_ID 4  /px4_3/fmu/...  UAV 2, model x500_lidar_front_3
  ...         and so on, one instance per UAV past the first two

The system ID is not carried in the topic name: it travels inside
VehicleCommand, so it must be set through the target_system parameter. A
command addressed to the wrong system is silently ignored and the vehicle
never arms.

Gazebo model names carry the instance suffix, so the lidar bridge topics do
too. If the launch order in 'make demo-coastal' changes, the suffixes change
with it. Verify with:  gz topic -l | grep -i lidar

Prerequisite: Gazebo, and one uXRCE-DDS agent and one PX4 instance per
vehicle, already running. Use 'make demo-coastal' for the two UAVs, or
scripts/sim/coastal_up.sh with the same N_UAVS.

Monitor:
  ros2 topic echo /actuator_cmd_safe          UAV 0
  ros2 topic echo /px4_1/actuator_cmd_safe    UAV 1
  ros2 topic echo /px4_2/actuator_cmd_safe    UGV
  ros2 topic echo /px4_2/drone/proximity      UGV lidar distance

@author Luca D'Aurizio
"""

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

# =============================================================================
# Scenario constants
#
# Keep WORLD in sync with COASTAL_WORLD in make/vars.mk, and the model names
# in sync with the launch order of 'make demo-coastal'.
# =============================================================================

WORLD = "coastal"

# Gazebo models, without the instance suffix.
UAV_MODEL = "x500_lidar_front"
UGV_MODEL = "r1_rover"

# The fleet: PX4 instance, spawn pose (world ENU, Gazebo) and, for a UAV, hover
# altitude of every vehicle. The spawn pose is for the workers' ENU->NED
# conversion of a task target. A run flies the UGV and the first N_UAVS UAVs.
FLEET_FILE = os.path.join(get_package_share_directory("guarded_swarms_bringup"),
                          "config", "coastal_fleet.yaml")
DEFAULT_N_UAVS = 2

# Interception altitude held by a UAV once it has a task, so it closes on the
# target's horizontal position without descending onto it.
INTERCEPT_ALTITUDE_M = 15.0

# Attitude limit of the UAV safety boards, degrees. To accelerate, the
# autopilot tilts a multirotor up to its own limit (PX4 MPC_TILTMAX_AIR, 45
# deg by default), so a lower board limit vetoes normal flight. 60 deg is the
# attitude-failure threshold of PX4's own failure detector (FD_FAIL_P,
# FD_FAIL_R): above the tilts the autopilot commands, below a loss of control.
UAV_MAX_TILT_DEG = 60.0

# Proximity veto thresholds of the UAV safety boards, metres. The workers fly
# every transit at 5 m/s (APPROACH_SPEED_MPS in uav_worker_node), which brakes
# in ~6 m; with up to ~0.3 s from the lidar return to the hold setpoint (~1.5
# m at 5 m/s) the UAV stops within ~8 m, so tripping at 10 m leaves ~2 m of
# clearance. The rover keeps the board default (1.5 / 2.5 m). Trip below the
# first, release above the second (hysteresis).
UAV_MIN_PROXIMITY_M = 10.0
UAV_PROXIMITY_RELEASE_M = 12.0

# The UAV worker publishes its setpoint here; the safety gate forwards it to
# fmu/in/trajectory_setpoint, holding position when the board is unsafe (see
# px4_safety_gate_node). Relative, so each UAV namespace gets its own gate.
PROPOSED_SETPOINT_TOPIC = "trajectory_setpoint_proposed"

# Which node enforces the veto on the UAVs, and the fault mode of the UAV
# workers, are launch arguments (see generate_launch_description), so that
# scripts/sim/coastal_up.sh can set them for the fault-injection runs:
#   veto_by    "worker" (default: the worker holds position itself, and the
#              gate is transparent) or "gate" (the gate holds, so a worker
#              that ignores the board cannot bypass it)
#   uav_fault  "none" (default) or "obstacle": at its first task a UAV worker
#              flies to its fault target and ignores the veto (see
#              uav_worker_node)
#
# Fault targets, world ENU: the centre of a building, crossed so that each UAV
# has some 40 m of run-up from its spawn point and reaches the proximity
# threshold at the full approach speed. No other building lies on either path.
#   UAV0 (-24, -24) -> building_0_5 (16 x 16 x 18 m): wall at 38.6 m
#   UAV1 ( 24, -24) -> building_0_4 (22 x 18 x 34 m): wall at 39.6 m
UAV0_FAULT_TARGET = (17.88, -47.34)
UAV1_FAULT_TARGET = (-22.53, -47.07)
# By UAV, in fleet order. The other UAVs have no faulty flight, whatever
# uav_fault says: scripts/sim/coastal_up.sh runs the faults with two UAVs.
FAULT_TARGETS = [UAV0_FAULT_TARGET, UAV1_FAULT_TARGET]
# Altitude of the faulty flight, 6 m below the lower roof (18 m), so the
# forward lidar hits the wall even with the UAV pitched.
UAV_FAULT_ALTITUDE_M = 12.0

# Rover patrol, NED relative to spawn, flattened as north,east,north,east...
# NED East = Gazebo X, so varying the second value drives along the shore.
# From X = -60 eastward, the road barrier at X = -8 triggers the veto.
UGV_WAYPOINTS = [0.0, 0.0, 0.0, 46.0]

LASERSCAN_BRIDGE = "@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"


def lidar_topic(model_name):
    return (f"/world/{WORLD}/model/{model_name}"
            "/link/lidar_sensor_link/sensor/lidar/scan")


def read_fleet():
    """The UGV and the first N_UAVS UAVs of FLEET_FILE.

    N_UAVS is read from the environment, as tbcspn.launch.py reads RF_LABEL:
    it sets how many nodes this file brings up, so it is needed as a value
    when the launch description is built.
    """
    with open(FLEET_FILE) as f:
        fleet = yaml.safe_load(f)
    uavs = fleet["uavs"]
    count = os.environ.get("N_UAVS", "").strip() or str(DEFAULT_N_UAVS)
    if not count.isdigit() or not 2 <= int(count) <= len(uavs):
        raise RuntimeError(f"N_UAVS must be a whole number from 2 to "
                           f"{len(uavs)}, not '{count}'")
    return fleet["ugv"], uavs[:int(count)]


def namespace_of(instance):
    """The namespace PX4 gives the topics of an instance: None for 0, the root."""
    return None if instance == 0 else f"px4_{instance}"


def describe(name, instance, role):
    """One line of the launch banner."""
    topics = "/fmu/..." if instance == 0 else f"/px4_{instance}/fmu/..."
    return f"{name}: instance {instance}, sys {instance + 1}, {topics}, {role}"


def vehicle_stack(namespace, model_name, system_id, is_ground,
                  hover_altitude=None, waypoints=None, spawn=None,
                  fault_target=None):
    """Build the per-vehicle node set.

    namespace of None means the root namespace, used by PX4 instance 0.
    fault_target of None means a UAV with no faulty flight, whatever the
    uav_fault launch argument says.
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
            parameters=[{"use_sim_time": True}],
            emulate_tty=True,
            **ns,
        ),
        Node(
            package="guarded_swarms_control",
            executable="px4_safety_bridge_node",
            name="px4_safety_bridge_node",
            output="screen",
            parameters=[{"lidar_topic": scan, "use_sim_time": True}],
            emulate_tty=True,
            **ns,
        ),
    ]

    # Altitude bounds are meaningful for an aircraft and not for a rover, so
    # the ground vehicle keeps only proximity, attitude and battery vetoes.
    # The aircraft get an attitude limit above the tilts of normal flight (see
    # UAV_MAX_TILT_DEG); the rover keeps the board default.
    safety_params = {"sensor_staleness_s": 5.0, "use_sim_time": True}
    if is_ground:
        safety_params.update({"min_altitude_m": -1.0, "max_altitude_m": 999.0})
    else:
        safety_params.update({"max_pitch_deg": UAV_MAX_TILT_DEG,
                              "max_roll_deg": UAV_MAX_TILT_DEG,
                              "min_proximity_m": UAV_MIN_PROXIMITY_M,
                              "proximity_release_m": UAV_PROXIMITY_RELEASE_M})

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
                "use_sim_time": True,
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
                "setpoint_topic": PROPOSED_SETPOINT_TOPIC,
                "fault": (ParameterValue(LaunchConfiguration("uav_fault"),
                                         value_type=str)
                          if fault_target is not None else "none"),
                "fault_target_x": (fault_target or spawn)[0],
                "fault_target_y": (fault_target or spawn)[1],
                "fault_altitude": UAV_FAULT_ALTITUDE_M,
                "use_sim_time": True,
            }],
            emulate_tty=True,
            **ns,
        ))
        nodes.append(Node(
            package="guarded_swarms_control",
            executable="px4_safety_gate_node",
            name="px4_safety_gate_node",
            output="screen",
            parameters=[{
                "veto_by": ParameterValue(LaunchConfiguration("veto_by"),
                                          value_type=str),
                "use_sim_time": True,
            }],
            emulate_tty=True,
            **ns,
        ))

    return nodes


def generate_launch_description():

    # =========================================================================
    # Per-vehicle stacks
    # =========================================================================

    ugv, uavs = read_fleet()

    uav_nodes = []
    banner = []
    for k, uav in enumerate(uavs):
        i = uav["instance"]
        hover = float(uav["hover_m"])
        uav_nodes += vehicle_stack(
            namespace_of(i), f"{UAV_MODEL}_{i}", i + 1,
            is_ground=False, hover_altitude=hover,
            spawn=(float(uav["x"]), float(uav["y"])),
            fault_target=FAULT_TARGETS[k] if k < len(FAULT_TARGETS) else None)
        banner.append(describe(f"UAV {k}", i, f"hover {hover:g} m"))

    i = ugv["instance"]
    ugv_nodes = vehicle_stack(
        namespace_of(i), f"{UGV_MODEL}_{i}", i + 1,
        is_ground=True, waypoints=UGV_WAYPOINTS,
        spawn=(float(ugv["x"]), float(ugv["y"])))
    banner.append(describe("UGV", i, "shore patrol"))

    # =========================================================================
    # Launch Description
    # =========================================================================

    return LaunchDescription([
        DeclareLaunchArgument(
            "veto_by", default_value="worker", choices=["worker", "gate"],
            description="Node that enforces the Safety Board veto on the "
                        "UAVs: the worker, or the safety gate"),
        DeclareLaunchArgument(
            "uav_fault", default_value="none", choices=["none", "obstacle"],
            description="Fault mode of the UAV workers, for fault-injection "
                        "runs"),
        LogInfo(msg="============================================================"),
        LogInfo(msg=f"Guarded Swarms - Coastal Pipeline ({len(uavs)} UAV + "
                    "1 UGV)"),
        LogInfo(msg="============================================================"),
        LogInfo(msg=f"Prereq: Gazebo, {len(uavs) + 1} DDS agents, "
                    f"{len(uavs) + 1} PX4 (make demo-coastal or coastal_up.sh)"),
        *[LogInfo(msg=line) for line in banner],
        LogInfo(msg="Coordination is shared; each vehicle vetoes on its own"),
        LogInfo(msg=["UAV veto by: ", LaunchConfiguration("veto_by"),
                     "; UAV fault: ", LaunchConfiguration("uav_fault")]),
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
            parameters=[{"use_sim_time": True}],
            emulate_tty=True,
        ),
        *uav_nodes,
        *ugv_nodes,
    ])