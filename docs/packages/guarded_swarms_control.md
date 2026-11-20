# guarded_swarms_control

The vehicle side of the system, and the intruder of the simulation. Each vehicle
has one worker, the only node that commands it: the worker arms the vehicle,
sends it its setpoints, proposes each command to the vehicle's Safety Board and
honours the board's veto. Around the workers, a bridge feeds the board the
readings of the vehicle, and on the UAVs a gate can enforce the veto in the
worker's place.

| Node                     | Role                                                                              | Instances       |
| ------------------------ | --------------------------------------------------------------------------------- | --------------- |
| `uav_worker_node`        | T8: flies a UAV: hover, intercept task, veto hold, fault mode                     | One per UAV     |
| `ugv_worker_node`        | T9: drives the rover: shore patrol, observe task, veto stop                       | One for the UGV |
| `px4_safety_bridge_node` | Turns the PX4 and lidar readings of a vehicle into the sensor topics of its board | One per vehicle |
| `px4_safety_gate_node`   | Sits between a UAV worker and PX4, and can enforce the veto                       | One per UAV     |
| `intruder_node`          | Flies the intruder along a scripted path and publishes its ground truth           | One             |

The vehicle-side topics are relative, so the namespace of the nodes selects the
vehicle: the root for PX4 instance 0, `px4_<i>` for instance `i`. For one UAV
in the coastal scenario:

| From                     | Topic                                                             | To                       |
| ------------------------ | ----------------------------------------------------------------- | ------------------------ |
| PX4, the lidar           | `fmu/out/...`, the lidar scan                                     | `px4_safety_bridge_node` |
| `px4_safety_bridge_node` | `drone/imu`, `drone/proximity`, `drone/battery`, `drone/altitude` | `safety_board_node`      |
| `uav_worker_node`        | `actuator_cmd_raw`                                                | `safety_board_node`      |
| `safety_board_node`      | `actuator_cmd_safe`                                               | `uav_worker_node`        |
| `safety_board_node`      | `safety_status`                                                   | `px4_safety_gate_node`   |
| `uav_worker_node`        | `trajectory_setpoint_proposed`                                    | `px4_safety_gate_node`   |
| `px4_safety_gate_node`   | `fmu/in/trajectory_setpoint`                                      | PX4                      |
| `uav_worker_node`        | `fmu/in/offboard_control_mode`, `fmu/in/vehicle_command`          | PX4                      |

The Safety Board is in [`guarded_swarms_safety`](guarded_swarms_safety.md), and
the tasks the workers receive are dispatched by T7 in
[`guarded_swarms_tbcspn`](guarded_swarms_tbcspn.md#dispatch_transition_node).

## uav_worker_node

T8, the worker of one UAV. It holds a hover until a task arrives, then flies an
interception at a stand-off altitude, following the target as the chain
updates it.

### Behaviour

- **Control loop.** A wall-clock timer runs the loop at 10 Hz. Each cycle the
  worker publishes the offboard control mode (position control), a trajectory
  setpoint, and a proposed command of `1.0` on `actuator_cmd_raw`. From the
  fiftieth cycle, 5 s after start, and every 20 cycles after that, it sends PX4
  the offboard mode and a forced arm, until PX4 reports the vehicle armed.
- **Hover.** Without a task, the worker holds the point above its spawn point at
  `hover_altitude`, facing north.
- **Task.** A `VehicleTask` of kind `uav` assigned to `target_system` locks the
  worker onto its target: the goal becomes the `target_position` of the task,
  converted from world ENU to the local frame of PX4, at `intercept_altitude`.
  A later task replaces it.
- **Track-lock.** Each `ConfirmedThreat` of the locked target on
  `/interp_tokens` moves the goal to the position of the threat. The worker
  follows what the chain believes, not the ground truth.
- **Expiry.** If neither the task nor a `ConfirmedThreat` has updated the target
  for longer than the `ttl_s` of the task, the worker drops the task and returns
  to its hover point.
- **Transit.** The setpoint is an approach point that moves towards the goal at
  5 m/s of simulated time, in steps of at most 0.5 s, so no transit is flown at
  the top speed of the autopilot. At 5 m/s the UAV brakes in about 6 m. The
  approach point restarts from the position of the UAV at each task, at the end
  of a hold and when a task expires.
- **Heading.** While the goal is more than 3 m away horizontally, the UAV faces
  it, so its forward lidar looks where it is going. Near a task goal it keeps
  its heading; over its hover point it faces north.
- **Setpoints.** Position and heading only: velocity, acceleration, jerk and yaw
  rate are left unset (NaN), so PX4 flies to the position.

A task position in world ENU becomes a local position with
`north = y − spawn_y` and `east = x − spawn_x`: PX4 measures its local frame
from the spawn point of the vehicle.

### The Safety Board veto

The board answers each proposed command on `actuator_cmd_safe`: a value below
0.01 is a veto.

- **Hold.** Under a veto, once airborne, the worker holds the position the UAV
  has when the veto begins, read from `fmu/out/vehicle_local_position_v1`, and
  the heading it last commanded. A multirotor cannot be stopped by cutting its
  throttle, so the hold is the aerial equivalent of the rover's stop.
- **Shortest hold.** A veto lasts at least 2 s: a safe answer clears it only
  2 s after the last veto, so the UAV does not resume, trip again and creep
  towards an obstacle.
- **Take-off.** The veto applies only once the UAV is airborne. On the ground
  the board is unsafe for its own reasons, its sensors not yet live and the
  altitude below its floor, and a hold there would keep the UAV from taking
  off. The UAV counts as airborne once it is armed and either climbs above half
  of `hover_altitude` or receives a safe answer from the board.

On the UAVs of the coastal scenario the safety gate can enforce the veto
instead of the worker (see [`px4_safety_gate_node`](#px4_safety_gate_node)).

### Fault mode

The fault mode turns a UAV worker into a faulty one, for fault-injection
runs. It is off by default.

| Parameter        | Type   | Default | Meaning                                                                          |
| ---------------- | ------ | ------- | -------------------------------------------------------------------------------- |
| `fault`          | string | `none`  | `none` or `obstacle`. Any other value is logged as a warning and taken as `none` |
| `fault_target_x` | double | `0.0`   | East coordinate of the fault target, world ENU, m                                |
| `fault_target_y` | double | `0.0`   | North coordinate of the fault target, world ENU, m                               |
| `fault_altitude` | double | `12.0`  | Altitude of the faulty flight, m                                                 |

With `fault` set to `obstacle`, the worker behaves normally until the first
task addressed to its vehicle. From then on, for the rest of the run, it:

- flies to the fault target at `fault_altitude`, instead of the designated
  target;
- ignores the Safety Board veto, later tasks, the updates of the target and
  the expiry of the mission.

The rest of the flight is unchanged: the transit at the bounded approach speed
(5 m/s), and the heading toward the goal, so the forward lidar looks where the
UAV is going. At start-up, and again at the first task, the worker logs a
warning with the fault target.

The launch argument `uav_fault` of `coastal_pipeline.launch.py` sets `fault`
for the workers of UAV0 and UAV1, so the fault acts on the one that receives
the task: `none` by default, and `scripts/sim/coastal_up.sh` takes it from
`UAV_FAULT`, with two UAVs only. In a larger fleet (`N_UAVS`, see
[Campaigns](../experiments/campaigns.md#the-fleet)) the other UAVs have no
fault target, and their workers run with `fault` set to `none`.
Each fault target is the centre of a building, at 12 m, 6 m below the lower
roof:

| UAV  | Spawn      | Fault target                     | Size           | Wall along the path |
| ---- | ---------- | -------------------------------- | -------------- | ------------------- |
| UAV0 | (-24, -24) | `building_0_5`, (17.88, -47.34)  | 16 × 16 × 18 m | 38.6 m              |
| UAV1 | (24, -24)  | `building_0_4`, (-22.53, -47.07) | 22 × 18 × 34 m | 39.6 m              |

The targets are crossed, so that each UAV has some 40 m of run-up and reaches
the proximity threshold of its board (10 m) at the full approach speed. No
other building lies on either path. At 5 m/s the UAV brakes in about 6 m,
which the 10 m threshold leaves room for.

```bash
VETO_BY=worker UAV_FAULT=obstacle ./scripts/sim/coastal_up.sh  # the veto is left to the faulty worker
VETO_BY=gate UAV_FAULT=obstacle ./scripts/sim/coastal_up.sh    # the safety gate enforces it
```

### Topics

Relative to the namespace of the UAV, except the two absolute topics of the
coordination layer.

| Topic                               | Type                                  | Direction  | QoS                                    |
| ----------------------------------- | ------------------------------------- | ---------- | -------------------------------------- |
| `/vehicle_tasks`                    | `guarded_swarms_msgs/msg/VehicleTask` | Subscribed | Reliable, volatile, depth 10           |
| `/interp_tokens`                    | `guarded_swarms_msgs/msg/InterpToken` | Subscribed | Reliable, volatile, depth 50           |
| `fmu/out/vehicle_status_v1`         | `px4_msgs/msg/VehicleStatus`          | Subscribed | Best effort, transient local, depth 10 |
| `fmu/out/vehicle_local_position_v1` | `px4_msgs/msg/VehicleLocalPosition`   | Subscribed | Best effort, transient local, depth 10 |
| `actuator_cmd_safe`                 | `std_msgs/msg/Float32`                | Subscribed | Reliable, volatile, depth 10           |
| `fmu/in/offboard_control_mode`      | `px4_msgs/msg/OffboardControlMode`    | Published  | Reliable, volatile, depth 10           |
| `setpoint_topic`                    | `px4_msgs/msg/TrajectorySetpoint`     | Published  | Reliable, volatile, depth 10           |
| `fmu/in/vehicle_command`            | `px4_msgs/msg/VehicleCommand`         | Published  | Reliable, volatile, depth 10           |
| `actuator_cmd_raw`                  | `std_msgs/msg/Float32`                | Published  | Reliable, volatile, depth 10           |

### Parameters

| Parameter              | Type    | Default                      | Meaning                                                          |
| ---------------------- | ------- | ---------------------------- | ---------------------------------------------------------------- |
| `target_system`        | integer | `1`                          | MAV_SYS_ID of the UAV: its commands, and the tasks it takes      |
| `hover_altitude`       | double  | `5.0`                        | Altitude of the hover point, m                                   |
| `intercept_altitude`   | double  | `15.0`                       | Altitude held on a task, m                                       |
| `spawn_x`, `spawn_y`   | double  | `-24.0`, `-24.0`             | Spawn point, world ENU, m, to convert the positions of the tasks |
| `setpoint_topic`       | string  | `fmu/in/trajectory_setpoint` | Topic of the trajectory setpoints                                |
| `fault` and its values |         |                              | See [Fault mode](#fault-mode)                                    |

The worker reads its parameters at start-up. Its timestamps for PX4 are the
time of the node clock, in microseconds.

### Fixed values

Constants in `src/uav_worker_node.cpp`.

| Constant                | Value     | Meaning                                                             |
| ----------------------- | --------- | ------------------------------------------------------------------- |
| `ARMING_DELAY_S`        | 5 s       | Wait before the first arming attempt                                |
| `ARMING_RETRY_CYCLES`   | 20 cycles | Between two arming attempts, 2 s at 10 Hz                           |
| `VETO_CMD_THRESHOLD`    | 0.01      | An `actuator_cmd_safe` below it is a veto                           |
| `VETO_MIN_HOLD_S`       | 2.0 s     | Shortest veto                                                       |
| `TAKEOFF_ALTITUDE_FRAC` | 0.5       | Fraction of `hover_altitude` above which the UAV counts as airborne |
| `APPROACH_SPEED_MPS`    | 5.0 m/s   | Speed of every transit, PX4's cruise speed (`MPC_XY_CRUISE`)        |
| `APPROACH_MAX_DT_S`     | 0.5 s     | Longest step of the approach point                                  |
| `HEADING_MIN_DIST_M`    | 3.0 m     | Distance from the goal beyond which the UAV faces it                |

### In the coastal scenario

`coastal_pipeline.launch.py` (in `guarded_swarms_bringup`) starts one worker for
each UAV, in the namespace of the UAV and with `use_sim_time`:

| Parameter            | Value                                                                         |
| -------------------- | ----------------------------------------------------------------------------- |
| `target_system`      | The PX4 instance of the UAV plus one                                          |
| `hover_altitude`     | The `hover_m` of the UAV in `coastal_fleet.yaml`                              |
| `intercept_altitude` | `15.0`                                                                        |
| `spawn_x`, `spawn_y` | The spawn point of the UAV in `coastal_fleet.yaml`                            |
| `setpoint_topic`     | `trajectory_setpoint_proposed`, so the setpoints pass through the safety gate |
| `fault`              | The `uav_fault` launch argument for UAV0 and UAV1, `none` for the others      |

## ugv_worker_node

T9, the worker of the rover. It patrols the shore road until a task arrives,
then drives to a point of the road abreast of the target and holds there.

### Behaviour

- **Control loop.** A wall-clock timer runs the loop at 10 Hz. Each cycle the
  worker proposes a command of `1.0` on `actuator_cmd_raw`. From 5 s after
  start, measured on the node clock, it sends PX4 a forced arm every cycle until
  PX4 reports the rover armed. It drives only once armed and once PX4 has
  published a position.
- **Patrol.** Without a task, the rover drives back and forth along its
  `waypoints`, local positions north and east of its spawn point: it moves on
  to the next waypoint within 0.8 m of the current one, and turns back at either
  end.
- **Task.** A `VehicleTask` of kind `ugv` assigned to `target_system` sends the
  rover to an observation point, where it holds. The target is over the water
  and the rover cannot leave the road, so the point stays on the patrol line:
  the north of the first waypoint, and the east of the target, `x − spawn_x`,
  clamped to the span of the waypoints. The task does not expire, and a later
  task replaces it.
- **Setpoints.** The rover drives to each point through PX4's rover position
  setpoint, at a cruising speed of 1.0 m/s and an arrival speed of 0.3 m/s.

### The Safety Board veto

The board answers each proposed command on `actuator_cmd_safe`: a value below
0.01 is a veto. Under a veto the worker sends a zero throttle, whatever it is
doing, and the rover stops. A veto lasts at least 2 s, as for the UAVs. On
patrol, a veto that lasts more than 6 s makes the rover give up its current
waypoint for the next one of its patrol: with the two waypoints of the coastal
scenario, it turns back. Under a task it waits.

### Topics

| Topic                               | Type                                  | Direction  | QoS                                    |
| ----------------------------------- | ------------------------------------- | ---------- | -------------------------------------- |
| `/vehicle_tasks`                    | `guarded_swarms_msgs/msg/VehicleTask` | Subscribed | Reliable, volatile, depth 10           |
| `fmu/out/vehicle_status_v1`         | `px4_msgs/msg/VehicleStatus`          | Subscribed | Best effort, transient local, depth 10 |
| `fmu/out/vehicle_local_position_v1` | `px4_msgs/msg/VehicleLocalPosition`   | Subscribed | Best effort, transient local, depth 10 |
| `actuator_cmd_safe`                 | `std_msgs/msg/Float32`                | Subscribed | Reliable, volatile, depth 10           |
| `fmu/in/rover_position_setpoint`    | `px4_msgs/msg/RoverPositionSetpoint`  | Published  | Reliable, volatile, depth 10           |
| `fmu/in/rover_throttle_setpoint`    | `px4_msgs/msg/RoverThrottleSetpoint`  | Published  | Reliable, volatile, depth 10           |
| `fmu/in/vehicle_command`            | `px4_msgs/msg/VehicleCommand`         | Published  | Reliable, volatile, depth 10           |
| `actuator_cmd_raw`                  | `std_msgs/msg/Float32`                | Published  | Reliable, volatile, depth 10           |

### Parameters

| Parameter            | Type     | Default                 | Meaning                                                       |
| -------------------- | -------- | ----------------------- | ------------------------------------------------------------- |
| `target_system`      | integer  | `3`                     | MAV_SYS_ID of the rover: its commands, and the tasks it takes |
| `spawn_x`, `spawn_y` | double   | `0.0`, `0.0`            | Spawn point, world ENU, m, to place the observation point     |
| `waypoints`          | double[] | `[0.0, 0.0, 0.0, 46.0]` | Patrol waypoints as north, east pairs from the spawn point, m |

`waypoints` needs at least two waypoints and an even number of values;
otherwise the worker uses the default.

| Constant             | Value   | Meaning                                           |
| -------------------- | ------- | ------------------------------------------------- |
| `WAYPOINT_RADIUS_M`  | 0.8 m   | Distance at which a waypoint counts as reached    |
| `CRUISING_SPEED_MS`  | 1.0 m/s | Cruising speed                                    |
| `ARRIVAL_SPEED_MS`   | 0.3 m/s | Arrival speed                                     |
| `ARM_DELAY_S`        | 5 s     | Wait before the first arming attempt              |
| `VETO_CMD_THRESHOLD` | 0.01    | An `actuator_cmd_safe` below it is a veto         |
| `VETO_MIN_HOLD_S`    | 2.0 s   | Shortest veto                                     |
| `VETO_GIVEUP_S`      | 6 s     | Veto after which the patrol gives up its waypoint |

In the coastal scenario `coastal_pipeline.launch.py` starts the worker in the
namespace of the rover, with `use_sim_time`, the system ID of its PX4 instance
plus one, its spawn point from `coastal_fleet.yaml` and the waypoints
`[0.0, 0.0, 0.0, 46.0]`: a patrol of 46 m eastward along the shore road.

## px4_safety_bridge_node

Feeds a Safety Board the readings of its vehicle. It translates the PX4 topics
of the vehicle, and the scan of its lidar, into the standard messages of the
board's sensor topics, so the board needs no PX4 message types.

| Source                              | Board topic       | Conversion                                                                                                                        |
| ----------------------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `fmu/out/vehicle_attitude`          | `drone/imu`       | The attitude quaternion, as the orientation of a `sensor_msgs/msg/Imu`                                                            |
| `fmu/out/battery_status_v1`         | `drone/battery`   | The remaining charge, in [0, 1], as the `percentage` of a `sensor_msgs/msg/BatteryState`                                          |
| `fmu/out/vehicle_local_position_v1` | `drone/altitude`  | The height above the spawn point, the down coordinate negated, as a `std_msgs/msg/Float32`; nothing while PX4 has no valid height |
| `lidar_topic`                       | `drone/proximity` | The shortest return of the scan, as the `range` of a `sensor_msgs/msg/Range`                                                      |

The lidar conversion keeps the two kinds of out-of-range return apart, since
they mean opposite things: a ray with no return within the maximum range,
`+inf`, sees nothing ahead, while a ray closer than the minimum range, `-inf`,
is in contact. The bridge ignores the first and counts the second as the
minimum range. A scan with no finite return gives the maximum range.

The PX4 topics are relative to the namespace of the vehicle, and subscribed best
effort, volatile, depth 10, as PX4 publishes them. The lidar topic and the
board topics use the default QoS: reliable, volatile, depth 10.

| Parameter     | Type   | Default                                                                            | Meaning                                            |
| ------------- | ------ | ---------------------------------------------------------------------------------- | -------------------------------------------------- |
| `lidar_topic` | string | `/world/default/model/x500_lidar_front_0/link/lidar_sensor_link/sensor/lidar/scan` | `sensor_msgs/msg/LaserScan` of the vehicle's lidar |

In the coastal scenario `coastal_pipeline.launch.py` starts one bridge for each
vehicle, in its namespace and with `use_sim_time`, with the lidar topic of its
Gazebo model, `/world/coastal/model/<model>_<i>/link/lidar_sensor_link/sensor/lidar/scan`.
A `parameter_bridge` of `ros_gz_bridge`, started alongside as `lidar_gz_bridge`,
brings that Gazebo topic into ROS 2.

## px4_safety_gate_node

The gate sits on the setpoint path of one UAV, between its worker and PX4. The
worker publishes its setpoints on `trajectory_setpoint_proposed`, and the gate
passes them on to PX4 on `fmu/in/trajectory_setpoint`.

The `veto_by` parameter chooses who enforces the Safety Board veto:

- `worker` (default): the gate forwards every setpoint unchanged, with a new
  timestamp, and the worker enforces the veto. The UAV flies as when the
  worker published to PX4 directly.
- `gate`: the gate also enforces the veto, whatever the worker proposes (see
  [Veto](#veto)).

The topology is the same in both modes: only the parameter changes.

**Why a separate node.** The worker plans the flight and also enforces the
veto, so a fault in the worker can disable the veto as well. With `veto_by` set
to `gate`, the veto is enforced by a node that does not plan the flight.

### Topics

Relative to the namespace of the UAV.

| Topic                               | Direction  | Type                                | QoS                                               | Content                                                            |
| ----------------------------------- | ---------- | ----------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------ |
| `trajectory_setpoint_proposed`      | Subscribed | `px4_msgs/msg/TrajectorySetpoint`   | Reliable, volatile                                | Setpoints proposed by the worker                                   |
| `safety_status`                     | Subscribed | `std_msgs/msg/Float32`              | Reliable, volatile                                | Status of the Safety Board, on its own timer: 1.0 safe, 0.0 unsafe |
| `fmu/out/vehicle_local_position_v1` | Subscribed | `px4_msgs/msg/VehicleLocalPosition` | Best effort, transient local, as PX4 publishes it | Position of the UAV, for the hold                                  |
| `fmu/in/trajectory_setpoint`        | Published  | `px4_msgs/msg/TrajectorySetpoint`   | Reliable, volatile                                | Setpoints to PX4, one for each proposed setpoint                   |

### Parameters

| Parameter | Type   | Default  | Meaning                                                                                                              |
| --------- | ------ | -------- | -------------------------------------------------------------------------------------------------------------------- |
| `veto_by` | string | `worker` | Who enforces the Safety Board veto: `worker` or `gate`. Any other value is logged as a warning and taken as `worker` |

The gate measures time on the node clock: in simulation, set `use_sim_time`.

### Fixed values

Constants in `src/px4_safety_gate_node.cpp`.

| Constant             | Value | Meaning                                                                            |
| -------------------- | ----- | ---------------------------------------------------------------------------------- |
| `SAFE_THRESHOLD`     | 0.5   | A `safety_status` below it is unsafe                                               |
| `STATUS_TIMEOUT_S`   | 0.5 s | A status older than this counts as unsafe                                          |
| `VETO_MIN_HOLD_S`    | 2.0 s | Shortest hold: the gate forwards again only this long after the last unsafe status |
| `TAKEOFF_ALTITUDE_M` | 3.0 m | Height, in the local position of PX4, at which the UAV counts as airborne          |

### Veto

With `veto_by` set to `gate`, the gate decides on every setpoint the worker
proposes and publishes one setpoint in reply, so PX4 receives setpoints at the
rate of the worker.

1. **Take-off.** Until the UAV is airborne, the gate forwards every setpoint.
   On the ground the board reports unsafe for its own reasons (stale sensors,
   the altitude floor), and a hold there would keep the UAV from taking off.
   The UAV counts as airborne once PX4 reports it 3 m up, well above the
   altitude floor of the board. The status of the board does not count: a
   single safe status on the ground would mark the UAV airborne, and the next
   unsafe one would hold it there, where the altitude floor keeps the board
   unsafe. From then on, a board that never reports safe holds the UAV.
2. **Hold.** Once the UAV is airborne, an unsafe status, or no status for more
   than 0.5 s, starts a hold. The gate replaces the setpoints of the worker
   with the position the UAV has at that moment, from
   `fmu/out/vehicle_local_position_v1` (the proposed position, while PX4 has
   no valid position), and the heading of the proposed setpoint. Velocity,
   acceleration, jerk and yaw rate are left unset (NaN), so PX4 holds the
   position.
3. **Release.** The gate forwards the setpoints of the worker again 2 s after
   the last unsafe status. A later veto takes a new hold position.

**Why `safety_status`.** The board publishes `safety_status` on its own timer,
and `actuator_cmd_safe` only in reply to the `actuator_cmd_raw` of the worker.
A gate that read `actuator_cmd_safe` would be left without a verdict by a
worker that stopped proposing commands.

**Time.** The age of the status and the hold are measured on the node clock,
which is simulated time in the coastal scenario: a paused simulation does not
make the status stale.

**Scope.** The gate acts on the trajectory setpoints only:
`offboard_control_mode` and `vehicle_command` go from the worker to PX4
directly.

### In the coastal scenario

`src/guarded_swarms_bringup/launch/coastal_pipeline.launch.py` starts one gate
for each UAV, in the namespace of the UAV and on simulated time, and sets the
`setpoint_topic` parameter of the UAV workers to `trajectory_setpoint_proposed`
(`PROPOSED_SETPOINT_TOPIC`). The launch argument `veto_by` sets `veto_by` for
every gate: `worker` by default, and `scripts/sim/coastal_up.sh` takes it from
`VETO_BY`. The rover has no gate.

To check the wiring with the scenario up (the first UAV has the root
namespace, the second `/px4_1`):

```bash
ros2 node list | grep px4_safety_gate_node      # one gate per UAV
ros2 topic info -v /fmu/in/trajectory_setpoint  # one publisher: the gate
ros2 param get /px4_safety_gate_node veto_by    # worker
```

## intruder_node

The intruder of the simulation. It is not part of the swarm: it plays the
target that the sensing and coordination layers react to. It flies a straight
ingress at constant speed and altitude, open loop, so that the same parameters
always give the same path.

A timer runs 20 times per simulated second. The node takes its start time at
the first tick with a valid clock, and then goes through three phases:

| Phase   | Until                                                             | Commanded velocity                                           |
| ------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| Idle    | `start_delay_s` have elapsed                                      | Zero: the target holds at its start                          |
| Ingress | It has travelled to within `arrival_radius_m` of the target point | `speed_mps`, from the ingress point towards the target point |
| Arrived | The end of the run                                                | Zero: the target holds station                               |

- **Open loop.** The velocity depends only on the time and the parameters, never
  on feedback from Gazebo. The distance travelled is integrated from the
  commanded velocity, starting at the ingress point, and decides the arrival.
- **Ground truth.** At each tick the node publishes the position of the target,
  in the world frame: the dead-reckoned position. The model moves
  kinematically, without gravity, so it follows the same path; only a collision
  in Gazebo would make the two differ.
- **Flags.** At each tick it also publishes whether the target is on its
  ingress, and whether it transmits, the `transmitting` parameter. A target that
  does not transmit is invisible to the RF agent (see
  [`guarded_swarms_sensing`](guarded_swarms_sensing.md#rf_agent_node)).

| Topic                   | Type                            | Direction | Content                                   |
| ----------------------- | ------------------------------- | --------- | ----------------------------------------- |
| `cmd_vel_topic`         | `geometry_msgs/msg/Twist`       | Published | Commanded linear velocity, world ENU, m/s |
| `intruder/ground_truth` | `geometry_msgs/msg/PoseStamped` | Published | Position of the target, world ENU         |
| `intruder/active`       | `std_msgs/msg/Bool`             | Published | True during the ingress                   |
| `intruder/transmitting` | `std_msgs/msg/Bool`             | Published | Whether the target transmits              |

The node runs in the root namespace, so its topics are `/intruder/...`. All use
the default QoS: reliable, volatile, depth 10.

| Parameter                             | Type   | Default                   | Meaning                                                  |
| ------------------------------------- | ------ | ------------------------- | -------------------------------------------------------- |
| `ingress_x`, `ingress_y`, `ingress_z` | double | `0.0`, `180.0`, `15.0`    | Start of the ingress, world ENU, m                       |
| `target_x`, `target_y`, `target_z`    | double | `0.0`, `10.0`, `15.0`     | End of the ingress, world ENU, m                         |
| `speed_mps`                           | double | `8.0`                     | Speed of the ingress, m/s                                |
| `start_delay_s`                       | double | `20.0`                    | Simulated time before the ingress starts, s              |
| `arrival_radius_m`                    | double | `3.0`                     | Distance from the target point that counts as arrived, m |
| `transmitting`                        | bool   | `true`                    | Whether the target transmits a radio link                |
| `cmd_vel_topic`                       | string | `/model/intruder/cmd_vel` | Topic of the velocity command                            |

### intruder.launch.py

`intruder.launch.py` (in `guarded_swarms_bringup`) starts the node with
`use_sim_time`, and `intruder_cmd_bridge`, a bridge of `ros_gz_bridge` that
carries the velocity command from ROS 2 to Gazebo, since the intruder is moved
by Gazebo rather than by PX4. Each parameter of the node above, except the
topic, is a launch argument with the same default. Started on its own, the
intruder can be stopped and set up again without touching the swarm.

```bash
ros2 launch guarded_swarms_bringup intruder.launch.py
ros2 launch guarded_swarms_bringup intruder.launch.py \
  speed_mps:=14.0 start_delay_s:=5.0
ros2 launch guarded_swarms_bringup intruder.launch.py transmitting:=false
```

`scripts/pipeline/test_pipeline.sh` starts it with the ingress and target
points of the attack vector of the run, its delay and its speed (see
[Pipeline run scripts](../scripts/pipeline.md)).
