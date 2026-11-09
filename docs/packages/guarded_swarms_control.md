# guarded_swarms_control

`guarded_swarms_control` holds the vehicle-side nodes of the system and the
intruder of the simulation. This page documents `px4_safety_gate_node` and
the fault mode of `uav_worker_node`; the rest of `uav_worker_node` and the
other nodes of the package (`ugv_worker_node`, `px4_safety_bridge_node`,
`intruder_node`, `rover_control_node`, `offboard_control_node`,
`command_bridge_node`) are added as the documentation is completed.

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
both gates: `worker` by default, and `scripts/sim/coastal_up.sh` takes it from
`VETO_BY`. The rover has no gate.

To check the wiring with the scenario up (the first UAV has the root
namespace, the second `/px4_1`):

```bash
ros2 node list | grep px4_safety_gate_node      # one gate per UAV
ros2 topic info -v /fmu/in/trajectory_setpoint  # one publisher: the gate
ros2 param get /px4_safety_gate_node veto_by    # worker
```

## uav_worker_node: fault mode

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

### In the coastal scenario

The launch argument `uav_fault` of `coastal_pipeline.launch.py` sets `fault`
for both UAV workers, so the fault acts on the UAV that receives the task:
`none` by default, and `scripts/sim/coastal_up.sh` takes it from `UAV_FAULT`.
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
