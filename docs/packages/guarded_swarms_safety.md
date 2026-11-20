# guarded_swarms_safety

The analogue safety layer. Every vehicle carries its own Safety Board, which
checks the readings of the vehicle's sensors against fixed limits and vetoes
the vehicle's actuator command while any limit is violated. A board knows
nothing of the coordination layer or of the other vehicles: its verdict depends
only on its own sensors. Its place in the architecture is described in
[Architecture](../architecture.md#the-safety-layer).

| Item                    | Purpose                                                               |
| ----------------------- | --------------------------------------------------------------------- |
| `safety_board_node`     | The Safety Board of one vehicle                                       |
| `mock_sensor_publisher` | Scripted sensor readings that violate each limit of the board in turn |

## safety_board_node

### Behaviour

The board keeps the latest reading of each sensor and evaluates its checks
against them:

- for each command proposed on `actuator_cmd_raw`: a command proposed while the
  board is safe is forwarded unchanged on `actuator_cmd_safe`; one proposed
  while it is unsafe is replaced by `0.0`, the veto, and logged with the reason;
- at 10 Hz, to publish its verdict on `safety_status`: `1.0` safe, `0.0`
  unsafe.

Every 20 status ticks, about every 2 s, it logs its readings, or the reason it
is unsafe, with the number of commands cleared and vetoed.

### Checks

The checks run in this order and stop at the first violation, which is the
reason the board reports:

| Check     | Unsafe when                                                                                                            |
| --------- | ---------------------------------------------------------------------------------------------------------------------- |
| Staleness | The IMU, the proximity or the battery has never sent a reading, or its last reading is older than `sensor_staleness_s` |
| Proximity | The range falls below `min_proximity_m`, until it rises above `proximity_release_m`                                    |
| Attitude  | The absolute pitch exceeds `max_pitch_deg`, or the absolute roll exceeds `max_roll_deg`                                |
| Battery   | The charge is below `min_battery_percent`                                                                              |
| Altitude  | The altitude is below `min_altitude_m` or above `max_altitude_m`                                                       |

- **Fail-safe start.** Until the IMU, the proximity and the battery have each
  sent a reading, the board is unsafe and vetoes every command.
- **Altitude.** The altitude is not part of the staleness check: the board keeps
  the last altitude it received. Its initial value, 0 m, is below the default
  `min_altitude_m`, so with the default limits the board is also unsafe until
  the first altitude reading.
- **Hysteresis.** The proximity check trips below `min_proximity_m` and releases
  only above `proximity_release_m`. With a single threshold a vehicle stopped by
  the veto would resume as soon as it stopped, trip again, and creep towards
  the obstacle. The board updates this state each time it evaluates past the
  staleness check, so the state is kept while a sensor is stale.
- **Readings.** Pitch and roll come from the orientation quaternion of the IMU,
  the charge from the `percentage` of the battery message, in [0, 1], and the
  distance from the `range` field alone of the proximity message.

The staleness check uses the clock of the node, simulated time when the node
runs with `use_sim_time`. The status is published on a wall-clock timer.

### Topics

The topic names are relative, so the namespace of the node selects the vehicle.

| Topic               | Type                           | Direction  | Content                             |
| ------------------- | ------------------------------ | ---------- | ----------------------------------- |
| `drone/imu`         | `sensor_msgs/msg/Imu`          | Subscribed | Orientation, for pitch and roll     |
| `drone/proximity`   | `sensor_msgs/msg/Range`        | Subscribed | Distance to the nearest obstacle, m |
| `drone/battery`     | `sensor_msgs/msg/BatteryState` | Subscribed | State of charge                     |
| `drone/altitude`    | `std_msgs/msg/Float32`         | Subscribed | Altitude above the ground, m        |
| `actuator_cmd_raw`  | `std_msgs/msg/Float32`         | Subscribed | Command proposed for the vehicle    |
| `actuator_cmd_safe` | `std_msgs/msg/Float32`         | Published  | The command, or `0.0` when vetoed   |
| `safety_status`     | `std_msgs/msg/Float32`         | Published  | `1.0` safe, `0.0` unsafe, at 10 Hz  |

Every subscription and publisher uses the default QoS: reliable, volatile,
depth 10.

### Parameters

| Parameter             | Type   | Default | Meaning                                                 |
| --------------------- | ------ | ------- | ------------------------------------------------------- |
| `min_proximity_m`     | double | `1.5`   | Range below which the proximity check trips, m          |
| `proximity_release_m` | double | `2.5`   | Range above which a tripped proximity check releases, m |
| `max_pitch_deg`       | double | `30.0`  | Largest absolute pitch, degrees                         |
| `max_roll_deg`        | double | `30.0`  | Largest absolute roll, degrees                          |
| `min_battery_percent` | double | `15.0`  | Lowest state of charge, percent                         |
| `min_altitude_m`      | double | `0.3`   | Lowest altitude, m                                      |
| `max_altitude_m`      | double | `50.0`  | Highest altitude, m                                     |
| `sensor_staleness_s`  | double | `2.0`   | Age beyond which a reading is stale, s                  |

The parameters are read at start-up: changing them on a running node has no
effect.

### In the coastal scenario

`coastal_pipeline.launch.py` (in `guarded_swarms_bringup`) starts one board for
each vehicle, in the namespace of the vehicle and with `use_sim_time`. The
`px4_safety_bridge_node` of the same vehicle publishes its sensor readings, and
the worker of the vehicle proposes its commands (see
[`guarded_swarms_control`](guarded_swarms_control.md)).

| Parameter                       | UAV                 | UGV                 |
| ------------------------------- | ------------------- | ------------------- |
| `sensor_staleness_s`            | `5.0`               | `5.0`               |
| `min_proximity_m`               | `10.0`              | `1.5`, the default  |
| `proximity_release_m`           | `12.0`              | `2.5`, the default  |
| `max_pitch_deg`, `max_roll_deg` | `60.0`              | `30.0`, the default |
| `min_altitude_m`                | `0.3`, the default  | `-1.0`              |
| `max_altitude_m`                | `50.0`, the default | `999.0`             |
| `min_battery_percent`           | `15.0`, the default | `15.0`, the default |

- **UAV attitude.** To accelerate, PX4 tilts a multirotor up to its own limit
  (`MPC_TILTMAX_AIR`, 45° by default), so a board limit below it would veto
  normal flight. 60° is the attitude-failure threshold of PX4's failure
  detector (`FD_FAIL_P`, `FD_FAIL_R`): above the tilts the autopilot commands,
  below a loss of control.
- **UAV proximity.** The UAV workers fly every transit at 5 m/s, which takes
  about 6 m to brake. With up to about 0.3 s from the lidar return to the hold,
  about 1.5 m at that speed, a UAV stops within about 8 m, so tripping at 10 m
  leaves about 2 m of clearance.
- **UGV altitude.** Altitude bounds are meaningless for a ground vehicle, so
  the rover's are set beyond any reading it can give.

On the UAVs the veto is enforced either by the worker or by the safety gate
between the worker and PX4, as chosen by the `veto_by` launch argument (see
[`guarded_swarms_control`](guarded_swarms_control.md)).

### On its own

`mock_pipeline.launch.py` (in `guarded_swarms_bringup`) starts the board alone,
in the root namespace and with the default parameters. The resilience tests run
against it: each test publishes its own sensor readings and commands, and checks
the verdicts of the board.

```bash
make test-resilience-mock
```

## mock_sensor_publisher

Publishes scripted readings on `/drone/imu`, `/drone/proximity`,
`/drone/battery` and `/drone/altitude` at 10 Hz, for a demo of the board
without a simulation. It cycles through six scenarios of 10 s each, then starts
again:

| Scenario              | Proximity | Pitch | Roll | Battery | Altitude | Board, default limits |
| --------------------- | --------- | ----- | ---- | ------- | -------- | --------------------- |
| `NOMINAL`             | 5.0 m     | 5°    | 3°   | 80 %    | 10 m     | Safe                  |
| `PROXIMITY VIOLATION` | 0.8 m     | 5°    | 3°   | 80 %    | 10 m     | Unsafe, proximity     |
| `ATTITUDE VIOLATION`  | 5.0 m     | 45°   | 3°   | 80 %    | 10 m     | Unsafe, attitude      |
| `BATTERY LOW`         | 5.0 m     | 5°    | 3°   | 10 %    | 10 m     | Unsafe, battery       |
| `ALTITUDE TOO HIGH`   | 5.0 m     | 5°    | 3°   | 80 %    | 60 m     | Unsafe, altitude      |
| `NOMINAL (RECOVERY)`  | 5.0 m     | 5°    | 3°   | 80 %    | 10 m     | Safe                  |

The topics are absolute, so the publisher drives a board in the root namespace.
It proposes no command: to see the veto, publish one on `/actuator_cmd_raw` and
watch `/actuator_cmd_safe`.

```bash
# terminal 1: the board, with the default parameters
make demo-safety-board
# terminal 2: the scripted readings
make demo-safety-sensors
# terminal 3: a proposed command, ten times a second
ros2 topic pub -r 10 /actuator_cmd_raw std_msgs/msg/Float32 "{data: 0.6}"
# terminal 4: 0.6 while the board is safe, 0.0 while it vetoes
ros2 topic echo /actuator_cmd_safe
```

`make demo-safety` prints these steps and the scenarios.
