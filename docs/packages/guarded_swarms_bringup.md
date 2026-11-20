# guarded_swarms_bringup

The launch files of the vehicles and of the intruder, and the fleet of the
coastal scenario. The package has no nodes of its own: it starts those of
`guarded_swarms_control` and `guarded_swarms_safety`. The sensing agents, the
coordination layer and the scripted supervisor have their own launch files, in
their packages.

| File                                | Purpose                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------ |
| `config/coastal_fleet.yaml`         | The vehicles of the coastal scenario                                     |
| `launch/coastal_pipeline.launch.py` | The nodes of every vehicle of the fleet, and the clock of the simulation |
| `launch/intruder.launch.py`         | The intruder and its two Gazebo bridges                                  |
| `launch/mock_pipeline.launch.py`    | A Safety Board alone, without PX4 or Gazebo                              |

## coastal_fleet.yaml

One entry per vehicle: its PX4 instance, its spawn point in world ENU and, for
a UAV, its hover altitude. A run flies the UGV and the first `N_UAVS` UAVs of
the list, 2 by default.

| Vehicle | Instance | Spawn x, y   | Hover |
| ------- | -------- | ------------ | ----- |
| UGV     | 2        | -60.0, -14.0 |       |
| UAV0    | 0        | -24.0, -24.0 | 12 m  |
| UAV1    | 1        | 24.0, -24.0  | 20 m  |
| UAV2    | 3        | 48.0, -24.0  | 12 m  |
| UAV3    | 4        | 72.0, -24.0  | 20 m  |
| UAV4    | 5        | 96.0, -24.0  | 12 m  |
| UAV5    | 6        | 120.0, -24.0 | 20 m  |
| UAV6    | 7        | 144.0, -24.0 | 12 m  |
| UAV7    | 8        | 168.0, -24.0 | 20 m  |

PX4 derives the rest from the instance `i`: the MAV*SYS_ID `i + 1`, the
namespace `px4*<i>`of its topics (the root for instance 0), the UDP port`8888 + i`of its uXRCE-DDS agent, and the Gazebo model`<model>\_<i>`. The UGV
is instance 2, started third; the UAVs past the first two follow it.

The UAVs stand on the launch pads along y = -24, 24 m apart, each at least 10 m
from any building or obstacle of the world. Neighbouring UAVs hover at 12 and
20 m, so that their volumes do not overlap, and both altitudes stay below the
34 m skyline of the town, so the proximity veto stays meaningful for them.

Three files read the fleet: `scripts/sim/coastal_up.sh`, which starts PX4 for
each vehicle; `coastal_pipeline.launch.py`; and `tbcspn.launch.py`, which gives
the UAVs to T7. `make demo-coastal` starts the UGV and the first two UAVs with
the poses of `make/vars.mk`, which must be kept in sync with this file.

## coastal_pipeline.launch.py

Starts the vehicle side of the coastal scenario: the clock of the simulation,
then the nodes of each vehicle, in the namespace of the vehicle and with
`use_sim_time`. Each Safety Board vetoes only its own vehicle, with no
knowledge of the others.

| Node                     | Started for  | Package                  | Documented in                                                                |
| ------------------------ | ------------ | ------------------------ | ---------------------------------------------------------------------------- |
| `clock_gz_bridge`        | The scenario | `ros_gz_bridge`          | Below                                                                        |
| `lidar_gz_bridge`        | Each vehicle | `ros_gz_bridge`          | Below                                                                        |
| `px4_safety_bridge_node` | Each vehicle | `guarded_swarms_control` | [`guarded_swarms_control`](guarded_swarms_control.md#px4_safety_bridge_node) |
| `safety_board_node`      | Each vehicle | `guarded_swarms_safety`  | [`guarded_swarms_safety`](guarded_swarms_safety.md#in-the-coastal-scenario)  |
| `uav_worker_node`        | Each UAV     | `guarded_swarms_control` | [`guarded_swarms_control`](guarded_swarms_control.md#uav_worker_node)        |
| `px4_safety_gate_node`   | Each UAV     | `guarded_swarms_control` | [`guarded_swarms_control`](guarded_swarms_control.md#px4_safety_gate_node)   |
| `ugv_worker_node`        | The UGV      | `guarded_swarms_control` | [`guarded_swarms_control`](guarded_swarms_control.md#ugv_worker_node)        |

- **Clock.** `clock_gz_bridge` brings the clock of Gazebo, `/clock`, into ROS 2.
  Every node of the scenario runs with `use_sim_time`, including those of the
  intruder, the sensing agents, the coordination layer and the scripted
  supervisor: without this bridge their clocks stay at zero.
- **Lidar.** `lidar_gz_bridge` brings the `LaserScan` of the vehicle's lidar,
  `/world/coastal/model/<model>_<i>/link/lidar_sensor_link/sensor/lidar/scan`,
  into ROS 2 under the same name, for the `px4_safety_bridge_node` of the
  vehicle. The models are `x500_lidar_front` for the UAVs and `r1_rover` for the
  UGV. The suffix is the PX4 instance, so the topic depends on the order in
  which the vehicles were started; `gz topic -l | grep -i lidar` lists them.
- **System ID.** The system ID does not appear in the names of the topics: it
  travels inside `VehicleCommand`, so each worker gets it as its `target_system`
  parameter. A command addressed to the wrong system is ignored, and the vehicle
  never arms.

| Argument    | Default  | Values             | Meaning                                                              |
| ----------- | -------- | ------------------ | -------------------------------------------------------------------- |
| `veto_by`   | `worker` | `worker`, `gate`   | Node that enforces the veto on the UAVs: the worker, or the gate     |
| `uav_fault` | `none`   | `none`, `obstacle` | Fault mode of the workers of UAV0 and UAV1, for fault-injection runs |

The `N_UAVS` environment variable sets the number of UAVs, from 2 to the number
in the fleet file, 2 by default; the launch file needs its value when it builds
the nodes. It must be the same as for PX4 and for `tbcspn.launch.py`.

| Constant                                         | Value                             | Use                                                      |
| ------------------------------------------------ | --------------------------------- | -------------------------------------------------------- |
| `WORLD`                                          | `coastal`                         | Name of the world, in the lidar topics                   |
| `UAV_MODEL`, `UGV_MODEL`                         | `x500_lidar_front`, `r1_rover`    | Gazebo models, without the instance suffix               |
| `INTERCEPT_ALTITUDE_M`                           | 15 m                              | `intercept_altitude` of the UAV workers                  |
| `UAV_MAX_TILT_DEG`                               | 60°                               | Attitude limits of the UAV boards                        |
| `UAV_MIN_PROXIMITY_M`, `UAV_PROXIMITY_RELEASE_M` | 10 m, 12 m                        | Proximity thresholds of the UAV boards                   |
| `PROPOSED_SETPOINT_TOPIC`                        | `trajectory_setpoint_proposed`    | `setpoint_topic` of the UAV workers, read by the gates   |
| `UAV0_FAULT_TARGET`, `UAV1_FAULT_TARGET`         | (17.88, -47.34), (-22.53, -47.07) | Fault targets, world ENU                                 |
| `UAV_FAULT_ALTITUDE_M`                           | 12 m                              | `fault_altitude` of the UAV workers                      |
| `UGV_WAYPOINTS`                                  | `[0.0, 0.0, 0.0, 46.0]`           | `waypoints` of the UGV worker: 46 m east along the shore |

The values of the Safety Boards are in
[`guarded_swarms_safety`](guarded_swarms_safety.md#in-the-coastal-scenario),
and the reasons for the fault targets in
[`guarded_swarms_control`](guarded_swarms_control.md#fault-mode).

The launch file needs Gazebo with the coastal world, and one uXRCE-DDS agent
and one PX4 instance per vehicle, already running: `make demo-coastal` starts
them for two UAVs. `scripts/sim/coastal_up.sh` starts them for any `N_UAVS`,
then this launch file, with `veto_by` and `uav_fault` from `VETO_BY` and
`UAV_FAULT`.

```bash
ros2 launch guarded_swarms_bringup coastal_pipeline.launch.py
N_UAVS=4 ros2 launch guarded_swarms_bringup coastal_pipeline.launch.py \
  veto_by:=gate
```

To watch the commands that pass each board:

```bash
ros2 topic echo /actuator_cmd_safe          # UAV0
ros2 topic echo /px4_1/actuator_cmd_safe    # UAV1
ros2 topic echo /px4_2/actuator_cmd_safe    # UGV
ros2 topic echo /px4_2/drone/proximity      # distance read by the UGV's lidar
```

## intruder.launch.py

Starts the intruder of `guarded_swarms_control` and the two bridges that move
its model in Gazebo and read its pose back. It is documented with the node, in
[`guarded_swarms_control`](guarded_swarms_control.md#intruderlaunchpy).

## mock_pipeline.launch.py

Starts a Safety Board alone, in the root namespace, with its default parameters
and on the wall clock: no PX4 and no Gazebo. `make test-resilience-mock` runs
the resilience tests against it (see
[`guarded_swarms_safety`](guarded_swarms_safety.md#on-its-own)).

```bash
ros2 launch guarded_swarms_bringup mock_pipeline.launch.py
```
