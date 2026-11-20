# Resilience tests

Tests of the Safety Board alone, without PX4 or Gazebo. Each test publishes the
readings and the commands a vehicle would give its board, and checks the
verdicts of the board: that it vetoes when it must, and recovers when the cause
is gone. They run against the board of `mock_pipeline.launch.py`, with its
default parameters and on the wall clock (see
[`guarded_swarms_safety`](../packages/guarded_swarms_safety.md#on-its-own)).
The CI runs them on every push and pull request to `main` and `dev`.

| File                                                | Purpose                                                                            |
| --------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `scripts/resilience/test_runner.sh`                 | Runs the tests one after the other, and prints a summary                           |
| `scripts/resilience/tests/test_sensor_staleness.py` | The sensors stop: the board must veto, and recover when they resume                |
| `scripts/resilience/tests/test_sensor_spike.py`     | An obstacle appears for a moment: the board must veto, and recover when it is gone |
| `scripts/resilience/config/mock.yaml`               | The topics and limits of the board, and the timeouts of the tests                  |
| `scripts/resilience/framework/base_test.py`         | The base class of the tests, and their results                                     |
| `scripts/resilience/framework/reporter.py`          | The JSON report of a test                                                          |
| `scripts/resilience/results/`                       | The reports, one per test and run                                                  |

## Running them

```bash
make test-resilience-mock
```

The target starts the mock pipeline in the background, with its log in
`/tmp/mock_pipeline.log`, waits 8 s, runs the tests, and stops the pipeline
whatever their outcome. It exits with the code of the runner. By hand:

```bash
# terminal 1: the board
ros2 launch guarded_swarms_bringup mock_pipeline.launch.py
# terminal 2: the tests
./scripts/resilience/test_runner.sh mock
```

The argument of the runner is the scenario, the name of a file in `config/`:
`mock` is the only one, and the default. The runner sources ROS 2 and the
workspace, puts `scripts/resilience` on `PYTHONPATH`, and runs each test as
`python3 <test> <config>`, the second even if the first fails. It prints
`PASS` or `FAIL` for each and a summary, and exits with 0 if both pass, 1
otherwise. The two tests take less than a minute together.

## The tests

Both tests first wait `startup_s` of `mock.yaml`, 8 s, then go through three
phases. Each phase starts by discarding the verdicts already received, so an
assertion counts only those of its phase. Every wait is on the wall clock, as
is the board.

In a phase with readings the test publishes a set every 0.2 s, ten times, with
a proposed command in each set. The nominal readings are well within every
limit of the board:

| Reading             | Nominal value                  |
| ------------------- | ------------------------------ |
| `/drone/imu`        | Level: the identity quaternion |
| `/drone/proximity`  | 5.0 m                          |
| `/drone/altitude`   | 10.0 m                         |
| `/drone/battery`    | 0.8                            |
| `/actuator_cmd_raw` | 0.6                            |

The verdicts are read from `/safety_status`, `1.0` safe and `0.0` unsafe, and
from `/actuator_cmd_safe`, the command or `0.0` when vetoed.

### test_sensor_staleness.py

The sensors stop publishing, as when a sensor fails or its link is lost. Before
the first phase, a warm-up publishes nominal readings for 2 s.

| Phase    | Readings                                                        | Passes when                                                                         |
| -------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Nominal  | Nominal                                                         | `/safety_status` is `1.0` within 3 s, and `/actuator_cmd_safe` above 0.5 within 5 s |
| Dropout  | None for `staleness_timeout_s` + 1.5 s, 3.5 s, then one command | `/safety_status` is `0.0`, and `/actuator_cmd_safe` is `0.0`, each within 3 s       |
| Recovery | Nominal                                                         | `/safety_status` is `1.0` within 3 s                                                |

The board answers only a proposed command, so the dropout ends with one: its
answer is the veto.

### test_sensor_spike.py

An obstacle appears in front of the vehicle, then goes away.

| Phase    | Readings                                                      | Passes when                                                                    |
| -------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Nominal  | Nominal                                                       | `/safety_status` is `1.0` within 3 s                                           |
| Spike    | Nominal, with the proximity at half `min_proximity_m`, 0.75 m | `/safety_status` is `0.0`, and `/actuator_cmd_safe` is `0.0`, each within 3 s  |
| Recovery | Nominal                                                       | `/safety_status` is `1.0`, and `/actuator_cmd_safe` above 0.5, each within 3 s |

The nominal 5.0 m is above `proximity_release_m` of the board, 2.5 m, so the
proximity check releases in the recovery.

## mock.yaml

| Key                          | Value  | Use                                                                                                     |
| ---------------------------- | ------ | ------------------------------------------------------------------------------------------------------- |
| `scenario`                   | `mock` | In the names of the reports                                                                             |
| `description`                |        | A line for the reader                                                                                   |
| `safety.staleness_timeout_s` | `2.0`  | `sensor_staleness_s` of the board, for the dropout                                                      |
| `safety.min_proximity_m`     | `1.5`  | `min_proximity_m` of the board, for the spike                                                           |
| `topics`                     |        | The topics of the board: the four readings, `actuator_cmd_raw`, `actuator_cmd_safe` and `safety_status` |
| `timeouts.startup_s`         | `8.0`  | The wait before the first phase, s                                                                      |

The two limits must match the parameters of the board under test: they are its
defaults, which `mock_pipeline.launch.py` runs. The topics are absolute, for a
board in the root namespace.

## Reports

Each test writes a JSON report to `scripts/resilience/results/`, named
`resilience_<test>_<scenario>_<date>_<time>.json`, for example
`resilience_sensor_spike_mock_20261120_114111.json`. Git ignores the reports,
and nothing deletes them: every run adds two.

| Field                       | Content                                                                 |
| --------------------------- | ----------------------------------------------------------------------- |
| `scenario`                  | The test and the scenario, as `sensor_spike_mock`                       |
| `timestamp`                 | The time of the report, `YYYYmmdd_HHMMSS`                               |
| `total`, `passed`, `failed` | The number of assertions, and of those that passed and failed           |
| `all_passed`                | Whether every assertion passed                                          |
| `results`                   | Each assertion: `name`, `passed`, `message`, `duration_s` and `details` |

## The framework

A test is a ROS 2 node that subclasses `BaseResilienceTest`, in
`framework/base_test.py`:

| Member                                          | Purpose                                                                                                |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `config`, `topics`, `timeouts`                  | The configuration file, and two of its sections                                                        |
| `subscribe_capture(topic, type)`                | Subscribes to a topic and buffers what arrives, up to 1000 messages; best effort with `reliable=False` |
| `clear_captured(topic)`                         | Discards what a topic has buffered                                                                     |
| `wait_for_message(topic, timeout_s, condition)` | Waits for a buffered message that satisfies `condition`                                                |
| `assert_message_received(...)`                  | Passes when a message that satisfies `condition` arrives within the timeout                            |
| `assert_no_message(...)`                        | Passes when none arrives during the window                                                             |
| `assert_value_within(...)`                      | Passes when a numeric field comes within a tolerance of a value                                        |
| `sleep(seconds)`, `spin_for(seconds)`           | Wait while the node keeps receiving                                                                    |
| `safe_destroy()`                                | Destroys the node, ignoring the errors rclpy can raise on clean-up                                     |

Each assertion returns a `TestResult`; a `TestSuite` collects them, prints the
report on the terminal and says whether all passed. `save_report`, in
`framework/reporter.py`, writes the JSON report of a suite.

The tests publish with the default QoS, reliable, which the subscriptions of the
board require, and subscribe best effort, which also receives from the reliable
publishers of the board.

To add a test, follow the two that exist: a subclass with its publishers and
captures, a `run()` that returns its `TestSuite`, and a `main()` that saves the
report and exits with 0 if all passed. Then add it to the runner, with a line
`run_test "$TESTS_DIR/<test>.py"`.
