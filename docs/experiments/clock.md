# Clock denial

The Safety Board judges one thing on the clock: sensor freshness. A reading is
stale when the board's simulated clock has advanced past its arrival by more
than the staleness window (5 s), and a stale sensor vetoes. A sensor that has
never been received is stale too, so before it has a clock the board holds
everything: it fails safe. Every other check - proximity, attitude, battery,
altitude - compares the latest reading to a threshold and reads no clock. This
bench denies the board its clock and measures the effect.

The board reads its clock from `/clock` (`use_sim_time`), so an attacker who
controls that stream controls the board's sense of time. Hold it at zero - the
stall already seen under `use_sim_time` when `/clock` does not advance - and the
board can no longer vouch for any reading's freshness: it treats every healthy
sensor as never-received and vetoes every command. The vehicle is blocked
although nothing is wrong with it. That is the denial of service.

The board is exercised in isolation, as the thesis measures it - no Gazebo, no
PX4, no coordination layer - with permissive value limits, so freshness, the
clock-dependent check, is the only thing that can make it veto.

| File                                     | Role                                                                       |
| ---------------------------------------- | -------------------------------------------------------------------------- |
| `scripts/pipeline/publish_clock.py`      | The board's simulated-clock source; advances `/clock`, or holds it at zero |
| `scripts/pipeline/publish_sensors.py`    | Feeds the four sensors, healthy and safe, and a constant command           |
| `scripts/experiments/run_clock_bench.sh` | Runs the arms below, RUNS each, and records every run to its own bag       |
| `scripts/metrics/analyze_clock.py`       | Reads the bags and writes the outcome tables                               |

## The arms

The sensors are healthy and safe in every run; only the clock differs.

| Arm         | Clock                 | Expected                                                     |
| ----------- | --------------------- | ------------------------------------------------------------ |
| `clock-ok`  | advances normally     | the board clears the command: the vehicle operates           |
| `clock-dos` | denied (held at zero) | the board fails safe and vetoes every command: it is blocked |

## Running it

The bench starts no scenario, so nothing else needs to run first. Commit the
code first: the manifest records the commit of every run.

```bash
RUNS=10 ./scripts/experiments/run_clock_bench.sh clock
```

Each run records every topic to `bags/clock-bench/clock/<arm>/run-NN/bag/`,
with its logs beside it, and appends a line to `manifest.csv`. A run lasts
`DURATION` seconds (40 by default); the two arms over ten runs take about
fifteen minutes. Ctrl-C stops after the run in progress; the same command
continues the ones still missing.

## Reading it

```bash
source /opt/ros/humble/setup.bash && source install/setup.bash
python3 scripts/metrics/analyze_clock.py bags/clock-bench/clock
```

Over a steady window (the first ten seconds, start-up, are skipped), it measures
for each run how much of the time the board denies the command - clamps
`actuator_cmd_safe` to zero - and reports unsafe, and whether the simulated
clock advanced at all. It reports, per arm, the share of runs that met the
expected outcome with its 95% Wilson interval, the mean share of the window the
command was denied and the board was unsafe, and how many runs saw the clock
advance. The tables are written to `results/clock-bench/clock/` as `clock.md`
and `clock.csv`.

## What it shows

Denying the board its clock denies the service: the board, unable to vouch for
any reading, vetoes every command and the vehicle is blocked, though the sensors
are healthy and the situation safe. It is the block already seen under
`use_sim_time` when the clock does not advance, reproduced on purpose and
measured as the fraction of commands refused. The board fails safe, which is the
right direction to fail, but an attacker who reaches its clock can hold a healthy
vehicle on the ground at will. A board exposed to this should take its time from
a source an attacker on the data bus cannot stall.
