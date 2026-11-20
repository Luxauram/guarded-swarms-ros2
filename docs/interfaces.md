# Interfaces

The topics of a run of the coastal scenario: the type of each, the nodes that
publish and subscribe to it, and the QoS they use. The behaviour of each node
is in the page of its package, and the path of a detection through the layers
in [Architecture](architecture.md).

The tables give the short names of the types: those of the coordination layer
are in `guarded_swarms_msgs/msg`, those of PX4 in `px4_msgs/msg`. T1 to T7 are
the transitions of [`guarded_swarms_tbcspn`](packages/guarded_swarms_tbcspn.md),
and the sensing agents those of
[`guarded_swarms_sensing`](packages/guarded_swarms_sensing.md).

## Namespaces

The topics of the coordination layer, of the intruder and of Gazebo are
absolute. The topics of a vehicle are relative to its namespace, where its
nodes run, and the namespace follows the PX4 instance of the vehicle (see
[`guarded_swarms_bringup`](packages/guarded_swarms_bringup.md#coastal_fleetyaml)):

| Vehicle      | PX4 instance | Namespace            | MAV_SYS_ID |
| ------------ | ------------ | -------------------- | ---------- |
| UAV0         | 0            | The root             | 1          |
| UAV1         | 1            | `/px4_1`             | 2          |
| UGV          | 2            | `/px4_2`             | 3          |
| UAV2 to UAV7 | 3 to 8       | `/px4_3` to `/px4_8` | 4 to 9     |

So `fmu/out/vehicle_local_position_v1` is `/fmu/out/vehicle_local_position_v1`
for UAV0, `/px4_1/fmu/out/vehicle_local_position_v1` for UAV1 and
`/px4_2/fmu/out/vehicle_local_position_v1` for the UGV.

## Coordination layer

| Topic              | Type             | Published by                                       | Subscribed by                                                                      |
| ------------------ | ---------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `/obs_tokens`      | `ObsToken`       | The four sensing agents                            | T1, T2 and T4                                                                      |
| `/interp_tokens`   | `InterpToken`    | T1 to T5                                           | T3, T5, T6, the scripted supervisor, the console bridge and each `uav_worker_node` |
| `/supervisor_auth` | `SupervisorAuth` | The scripted supervisor, or the supervisor console | T6                                                                                 |
| `/mission_tokens`  | `MissionToken`   | T6                                                 | T7                                                                                 |
| `/vehicle_tasks`   | `VehicleTask`    | T7                                                 | Each `uav_worker_node`, and the `ugv_worker_node`                                  |
| `/console/threat`  | `InterpToken`    | The console bridge                                 | The supervisor console                                                             |

- **Decisions.** `scripts/pipeline/test_pipeline.sh` starts the scripted
  supervisor of
  [`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md), unless
  `MANUAL_AUTH=1`, in which case the supervisor console decides. A decision can
  also be published by hand (see
  [`guarded_swarms_tbcspn`](packages/guarded_swarms_tbcspn.md#mission_transition_node)).
- **The console.** The supervisor console, `console/decision_panel.html`,
  reaches ROS 2 through rosbridge. The console bridge,
  `console/console_bridge_node.py`, republishes the `ConfirmedThreat`s of
  `/interp_tokens` on `/console/threat`, which the console subscribes to in its
  place (see [QoS](#qos)).
- **The workers.** Each worker takes only the tasks of its kind of vehicle
  assigned to its system, and a UAV worker only the `ConfirmedThreat`s of the
  target it is locked on (see
  [`guarded_swarms_control`](packages/guarded_swarms_control.md)).

## Intruder

| Topic                     | Type                            | Published by    | Subscribed by                                     |
| ------------------------- | ------------------------------- | --------------- | ------------------------------------------------- |
| `/intruder/ground_truth`  | `geometry_msgs/msg/PoseStamped` | `intruder_node` | The four sensing agents                           |
| `/intruder/transmitting`  | `std_msgs/msg/Bool`             | `intruder_node` | `rf_agent_node`                                   |
| `/intruder/active`        | `std_msgs/msg/Bool`             | `intruder_node` | No node                                           |
| `/model/intruder/cmd_vel` | `geometry_msgs/msg/Twist`       | `intruder_node` | `intruder_cmd_bridge`, which carries it to Gazebo |

The sensing agents subscribe to the ground truth of each target in their
`ground_truth_topics`, and the RF agent to the topics in its
`transmitting_topics`: in the coastal scenario the intruder is the only target.
`/intruder/active` is recorded by `scripts/record/record_run.sh`, and
`scripts/metrics/audit_timing.py` reads the start of the ingress from it.

## Gazebo

Three kinds of `parameter_bridge` of `ros_gz_bridge` connect Gazebo and ROS 2:

| Bridge                             | Direction       | Topic                         | ROS 2 type                  | Gazebo type         |
| ---------------------------------- | --------------- | ----------------------------- | --------------------------- | ------------------- |
| `clock_gz_bridge`                  | Gazebo to ROS 2 | `/clock`                      | `rosgraph_msgs/msg/Clock`   | `gz.msgs.Clock`     |
| `lidar_gz_bridge`, one per vehicle | Gazebo to ROS 2 | The lidar scan of the vehicle | `sensor_msgs/msg/LaserScan` | `gz.msgs.LaserScan` |
| `intruder_cmd_bridge`              | ROS 2 to Gazebo | `/model/intruder/cmd_vel`     | `geometry_msgs/msg/Twist`   | `gz.msgs.Twist`     |

- **Clock.** The nodes of the vehicles, the intruder, the sensing agents, the
  transitions and the scripted supervisor run with `use_sim_time`, and read
  the time from `/clock`.
- **Lidar.** The scan of a vehicle keeps its Gazebo name in ROS 2,
  `/world/coastal/model/<model>_<i>/link/lidar_sensor_link/sensor/lidar/scan`,
  with `x500_lidar_front` or `r1_rover` as `<model>` and the PX4 instance as
  `<i>`. The `px4_safety_bridge_node` of the vehicle subscribes to it.
- **Intruder.** The odometry of the intruder model, on
  `/model/intruder/odometry` and `/model/intruder/pose`, stays in Gazebo: no
  bridge brings it into ROS 2 (see
  [`guarded_swarms_gz`](packages/guarded_swarms_gz.md#intruder)).

## Vehicles

Relative to the namespace of the vehicle. Each vehicle has its own uXRCE-DDS
agent, which carries the PX4 topics between PX4 and ROS 2. "The worker" is the
`uav_worker_node` of a UAV, or the `ugv_worker_node` of the UGV.

### Safety layer

| Topic                          | Type                           | Published by             | Subscribed by                    |
| ------------------------------ | ------------------------------ | ------------------------ | -------------------------------- |
| `drone/imu`                    | `sensor_msgs/msg/Imu`          | `px4_safety_bridge_node` | `safety_board_node`              |
| `drone/proximity`              | `sensor_msgs/msg/Range`        | `px4_safety_bridge_node` | `safety_board_node`              |
| `drone/battery`                | `sensor_msgs/msg/BatteryState` | `px4_safety_bridge_node` | `safety_board_node`              |
| `drone/altitude`               | `std_msgs/msg/Float32`         | `px4_safety_bridge_node` | `safety_board_node`              |
| `actuator_cmd_raw`             | `std_msgs/msg/Float32`         | The worker               | `safety_board_node`              |
| `actuator_cmd_safe`            | `std_msgs/msg/Float32`         | `safety_board_node`      | The worker                       |
| `safety_status`                | `std_msgs/msg/Float32`         | `safety_board_node`      | `px4_safety_gate_node`, on a UAV |
| `trajectory_setpoint_proposed` | `TrajectorySetpoint`           | `uav_worker_node`        | `px4_safety_gate_node`           |

The sensor topics keep the `drone/` prefix on every vehicle, the UGV included.

### To PX4

| Topic                            | Type                    | Published by           |
| -------------------------------- | ----------------------- | ---------------------- |
| `fmu/in/offboard_control_mode`   | `OffboardControlMode`   | `uav_worker_node`      |
| `fmu/in/trajectory_setpoint`     | `TrajectorySetpoint`    | `px4_safety_gate_node` |
| `fmu/in/vehicle_command`         | `VehicleCommand`        | The worker             |
| `fmu/in/rover_position_setpoint` | `RoverPositionSetpoint` | `ugv_worker_node`      |
| `fmu/in/rover_throttle_setpoint` | `RoverThrottleSetpoint` | `ugv_worker_node`      |

In the coastal scenario a UAV worker publishes its setpoints on
`trajectory_setpoint_proposed`, and the gate passes them on to PX4. With the
default of its `setpoint_topic` parameter, the worker publishes on
`fmu/in/trajectory_setpoint` itself.

### From PX4

| Topic                               | Type                   | Subscribed by                                                                                                                      |
| ----------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `fmu/out/vehicle_status_v1`         | `VehicleStatus`        | The worker                                                                                                                         |
| `fmu/out/vehicle_local_position_v1` | `VehicleLocalPosition` | The worker, `px4_safety_bridge_node` and, on a UAV, `px4_safety_gate_node`; T7, for each UAV of the run; `eo_agent_node`, for UAV0 |
| `fmu/out/vehicle_attitude`          | `VehicleAttitude`      | `px4_safety_bridge_node`                                                                                                           |
| `fmu/out/battery_status_v1`         | `BatteryStatus`        | `px4_safety_bridge_node`                                                                                                           |

T7 and the EO agent run in the root namespace and subscribe by absolute name: T7
to the topics of its `uav_pose_topics`, the EO agent to the one of its
`uav_pose_topic`.

## QoS

| Profile                                | Used by                                                                                                                                                        |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reliable, volatile, depth 10           | Every publisher and subscription not listed below                                                                                                              |
| Reliable, volatile, depth 50           | The subscriptions of T1 to T6, of the scripted supervisor and of the UAV workers to `/obs_tokens` and `/interp_tokens`, and the publishers of `/interp_tokens` |
| Reliable, transient local, depth 10    | `/supervisor_auth`, at the scripted supervisor and at T6                                                                                                       |
| Best effort, transient local, depth 10 | The subscriptions of the workers, the gates, T7 and the EO agent to PX4                                                                                        |
| Best effort, volatile, depth 10        | The subscriptions of `px4_safety_bridge_node` to PX4                                                                                                           |

Three rules decide whether a publisher and a subscription connect:

- **PX4.** PX4 publishes its `fmu/out` topics best effort, and a subscription
  that requests reliable delivery receives nothing from a best-effort
  publisher: every subscription to them is best effort. The `fmu/in` topics
  take the default profile.
- **Decisions.** T6 requests transient local durability on `/supervisor_auth`,
  so that a decision published before T6 matched its publisher is not lost. A
  publisher that offers only volatile durability does not connect to it: the
  scripted supervisor offers transient local, and a decision published by hand
  needs `--qos-durability transient_local`.
- **The console.** rosbridge chooses the QoS of the subscriptions it makes for
  the console, and on `/interp_tokens` its choice receives nothing from the
  publishers of the transitions. The console bridge subscribes with their
  profile, and publishes `/console/threat` with the default one, which
  rosbridge receives.

## Outside a run

Some tools publish on these topics without the scenario, or in its place:

| Publisher                                  | Topics                                                                                         | Use                                                                                                                                               |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mock_sensor_publisher`                    | `/drone/imu`, `/drone/proximity`, `/drone/battery`, `/drone/altitude`                          | `make demo-safety-sensors`, a demo of the board alone (see [`guarded_swarms_safety`](packages/guarded_swarms_safety.md#mock_sensor_publisher))    |
| The resilience tests                       | The sensor topics and `/actuator_cmd_raw`; they read `/actuator_cmd_safe` and `/safety_status` | `make test-resilience-mock`, against the board of `mock_pipeline.launch.py` (see [Resilience tests](scripts/resilience.md))                       |
| `scripts/pipeline/publish_clock.py`        | `/clock`                                                                                       | The clock-denial bench (see [Clock-denial bench](experiments/clock.md))                                                                           |
| `scripts/pipeline/publish_sensors.py`      | The sensor topics and `/actuator_cmd_raw`                                                      | The clock-denial bench                                                                                                                            |
| `scripts/pipeline/publish_observations.py` | `/obs_tokens`                                                                                  | `FORGE_OBS=ghost` in `test_pipeline.sh`: forged observations, with the agents off (see [Pipeline run scripts](scripts/pipeline.md#configuration)) |
| `scripts/pipeline/publish_mission.py`      | `/mission_tokens`                                                                              | `FORGE_MISSION=obstacle` in `test_pipeline.sh`: a mission that no authorisation released                                                          |

All of them use absolute names, so they address a board in the root namespace,
or the coordination layer.
