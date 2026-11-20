# Veto recording

A recording of the Safety Board alone, with no coordination layer, no Gazebo
and no PX4 running, so that its verdicts can depend on nothing but its
sensors. `scripts/record/record_veto.sh` drives one board through the six
scripted scenarios of `mock_sensor_publisher`, proposes a command throughout,
and records a bag of the readings and of the verdicts.
`scripts/metrics/audit_recordings.py` then measures the reaction time of the
board from the bag (see [Analysis](analysis.md#auditing-recordings)).

## Running it

From the root of the repository, with nothing else running:

```bash
./scripts/record/record_veto.sh            # bag in bags/veto-<date>-<time>
./scripts/record/record_veto.sh veto-ugv   # another tag
```

The argument is the tag of the bag, `veto` by default. The bag is written to
`bags/<tag>-<YYYYmmdd-HHMMSS>` under the working directory, which git ignores.
A run takes about 70 s.

## What a run does

1. It starts `ros2 bag record` on the topics below, and waits 2 s.
2. It starts `safety_board_node`, with the arguments in `SAFETY_ARGS`, and waits
   2 s.
3. It starts `mock_sensor_publisher`, and waits 1 s.
4. It publishes `RAW_THRUST` on `/actuator_cmd_raw` at 10 Hz, with
   `ros2 topic pub`.
5. It waits `DURATION_S`, then stops the four processes. It stops them also on
   Ctrl-C.

The board runs in the root namespace, on the wall clock. The mock publisher
cycles through six scenarios of 10 s each (see
[`guarded_swarms_safety`](../packages/guarded_swarms_safety.md#mock_sensor_publisher)),
so the 66 s of the default cover one full pass, closing recovery included. The
constant command makes the veto visible on `/actuator_cmd_safe`, where the
board answers each proposed command, as well as on `/safety_status`.

The bag holds seven topics: the command before and after the board,
`/actuator_cmd_raw` and `/actuator_cmd_safe`; the four readings that can trip
it, `/drone/proximity`, `/drone/imu`, `/drone/battery` and `/drone/altitude`;
and its verdict, `/safety_status`.

## Configuration

| Variable      | Default | Meaning                                                      |
| ------------- | ------- | ------------------------------------------------------------ |
| `DURATION_S`  | `66`    | How long the board is driven, s                              |
| `RAW_THRUST`  | `0.7`   | The command proposed to the board                            |
| `SAFETY_ARGS` | empty   | Arguments of `safety_board_node`, appended to its `ros2 run` |

With the default parameters of the board, four scenarios trip it: proximity,
attitude, battery and altitude, since the 60 m of the altitude scenario is above
the default `max_altitude_m` of 50 m. With the altitude limits of the rover the
altitude scenario no longer trips it, and proximity, attitude and battery
remain:

```bash
SAFETY_ARGS="--ros-args -p min_altitude_m:=-1.0 -p max_altitude_m:=999.0" \
  ./scripts/record/record_veto.sh veto-ugv
```

## Logs

| Log                      | Content                              |
| ------------------------ | ------------------------------------ |
| `/tmp/gs_veto_board.log` | The board, with a line for each veto |
| `/tmp/gs_veto_mock.log`  | The mock publisher                   |
| `/tmp/gs_veto_bag.log`   | The recorder                         |
| `/tmp/gs_veto_raw.log`   | The command stream                   |

When it stops, the script kills every `safety_board_node` and
`mock_sensor_publisher` on the machine, and every process with
`actuator_cmd_raw` on its command line, not only its own: run it with no
scenario and no other board running.
