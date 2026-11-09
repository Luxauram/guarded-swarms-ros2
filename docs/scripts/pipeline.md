# Pipeline run scripts

Three scripts drive one end-to-end run of the coastal pipeline against a
running scenario:

| Script                              | Role                                                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `scripts/pipeline/test_pipeline.sh` | Launches the run, waits for the threat and the supervisor's decision, and reports which vehicles moved  |
| `scripts/record/record_run.sh`      | Records the same run into a rosbag for the metric scripts; it drives the run through `test_pipeline.sh` |
| `scripts/pipeline/run_guards.sh`    | Checks shared by the two scripts; sourced, not executed                                                 |

## Quick start

```bash
make demo-coastal                               # terminal 1: the scenario, leave it running
./scripts/pipeline/test_pipeline.sh             # terminal 2: one run, with a verdict
./scripts/record/record_run.sh my-run           # terminal 2: one run, recorded to bags/my-run-<timestamp>/
```

Both scripts stay up after the result, so the vehicles can be watched. Ctrl-C
ends the run. With `STAY_UP=0` they end on their own once the report is
printed, as in the [campaigns](../experiments/campaigns.md).

## What a run does

1. **Pre-run checks.** The scenario must be up and no process of an earlier
   run may still be alive (see [Guards](#guards)). `record_run.sh` runs the
   same checks before it starts the recorder.
2. **Launch.** The intruder, the sensing layer, the TB-CSPN coordination layer
   (T1–T7) and, unless `MANUAL_AUTH=1`, the scripted supervisor.
3. **Ground-truth checks.** `/intruder/ground_truth` must have exactly one
   publisher, and its messages must arrive. The intruder publishes them on
   simulated time, so they show that `/clock` reaches the nodes of the run.
4. **First snapshot** of the vehicle positions, while no vehicle has a task.
5. **Wait for the first ConfirmedThreat**, up to `THREAT_TIMEOUT` seconds.
6. **Decision.** The scripted supervisor decides `AUTH_DELAY_S` simulated
   seconds after the first ConfirmedThreat; the script waits
   `AUTH_DELAY_S + REACT_S` seconds.
7. **End check.** The ground truth must still arrive: `/clock` reached the
   run through the decision and the reaction. A run without a ConfirmedThreat
   and the observation of `EXPECT_THREAT=no` end with the same check.
8. **Report.** Second snapshot, [verdict](#verdict), the supervisor's decision
   and the dispatch log.
9. **Teardown** on Ctrl-C, or right after the report with `STAY_UP=0` (see
   [Teardown](#teardown)).

## Configuration

Set the variables in front of the command; both scripts pass them on:

```bash
SEED=1000 DECISION=deny ./scripts/record/record_run.sh withheld
```

| Variable                                                        | Default                   | Meaning                                                                                                                  |
| --------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `ATTACK_VECTOR`                                                 | `frontal`                 | Intruder ingress: `frontal`, `east-deep`, `rear`, or `demo` (a demonstration path, not a measurement vector)             |
| `INTRUDER_DELAY`                                                | `8.0`                     | Seconds before the intruder starts moving                                                                                |
| `INTRUDER_SPEED`                                                | `6.0`                     | Intruder speed, m/s                                                                                                      |
| `SEED`                                                          | drawn and printed         | Seed of the run. The sensing agents use `SEED+1` (radar), `+2` (RF), `+3` (acoustic) and `+4` (EO)                       |
| `RADAR_ENABLED`, `RF_ENABLED`, `ACOUSTIC_ENABLED`, `EO_ENABLED` | `true`                    | Per-modality enables                                                                                                     |
| `EO_DELAY_S`                                                    | `0`                       | Delay of EO delivery, seconds                                                                                            |
| `RF_LABEL`                                                      | `LikelyDroneLink`         | Label emitted by T2                                                                                                      |
| `EXPECT_THREAT`                                                 | `yes`                     | `no`: do not wait for a ConfirmedThreat; let the pipeline run for `OBSERVE_S` seconds instead                            |
| `OBSERVE_S`                                                     | `90`                      | Observation time when `EXPECT_THREAT=no`, seconds                                                                        |
| `DECISION`                                                      | `authorise`               | Scripted supervisor: `authorise`, `deny` (explicit refusal) or `none` (no decision)                                      |
| `AUTH_DELAY_S`                                                  | `0`                       | Supervisor decision time after the first ConfirmedThreat, simulated seconds                                              |
| `AUTH_TTL_S`                                                    | `15`                      | Validity of the decision, seconds                                                                                        |
| `MANUAL_AUTH`                                                   | `0`                       | `1`: the supervisor decides from the console (`console/decision_panel.html`), and the scripted supervisor is not started |
| `THREAT_TIMEOUT`                                                | `60`                      | Seconds to wait for a ConfirmedThreat                                                                                    |
| `REACT_S`                                                       | `10`                      | Seconds to let the vehicles react after an automatic decision                                                            |
| `MOVE_THRESHOLD_M`                                              | `0.5`                     | Metres a vehicle must travel to count as moved                                                                           |
| `STAY_UP`                                                       | `1`                       | `0`: end the run once the report is printed, with exit code 0, instead of staying up until Ctrl-C                        |
| `BAG_DIR`                                                       | `bags/<name>-<timestamp>` | `record_run.sh` only: folder of the bag. rosbag2 refuses an existing folder                                              |

The counterfactual runs of the thesis use these variables:

| Counterfactual              | Setting                                                  |
| --------------------------- | -------------------------------------------------------- |
| EO confirmation unavailable | `EO_ENABLED=false`, or `EO_DELAY_S` above the threat TTL |
| Conflicting RF evidence     | `RF_LABEL=LikelyCivilianTraffic EXPECT_THREAT=no`        |
| Authorisation withheld      | `DECISION=deny`                                          |

**Seeds.** With the same seed, each sensing agent draws the same random
sequence. A run is still not identical bit for bit: the position an agent reads
at each scan depends on when the ground-truth messages arrive, so the same
draws can meet slightly different positions.

## Exit codes

| Code  | Meaning                                                                                                                                                                                   |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`   | The run ended on its own after the report (`STAY_UP=0`)                                                                                                                                   |
| `1`   | No ConfirmedThreat within `THREAT_TIMEOUT` (also: unknown `ATTACK_VECTOR`)                                                                                                                |
| `2`   | Refused to start: the scenario is down, or an earlier run left processes behind. Nothing of the run was started; `record_run.sh` checks before starting the recorder, so it writes no bag |
| `3`   | Stopped by a guard: the intruder's ground truth does not have exactly one source, or does not arrive. `record_run.sh` keeps the bag for inspection, but **the bag must not be analysed**  |
| `130` | Ended with Ctrl-C or SIGTERM: the normal end of a run with `STAY_UP=1`                                                                                                                    |

`record_run.sh` exits with the code of `test_pipeline.sh`.

## Guards

Defined in `run_guards.sh`. Each prints what is wrong; the calling script then
stops with the exit code above.

| Guard                        | When                                      | Fails if                                                                                                                                                                               |
| ---------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `guard_scenario_running`     | Before anything starts                    | No `/clock` message within 10 s                                                                                                                                                        |
| `guard_no_leftovers`         | Before anything starts                    | A process of an earlier run is alive; the guard lists them                                                                                                                             |
| `guard_single_ground_truth`  | After the launches                        | `/intruder/ground_truth` has not exactly one publisher. The guard waits up to 15 s for the first one, then 2 s for discovery to settle, and counts again                               |
| `guard_ground_truth_flowing` | After the launches, and before the result | No `/intruder/ground_truth` message within 15 s. The intruder publishes it on simulated time: without a message, the nodes of the run receive no `/clock`, or the intruder has stopped |

`stop_pipeline_processes` performs the teardown: SIGTERM to every process of
the run, then SIGKILL, with a warning that names them, for any still alive
after 5 s.

**Which processes belong to a run.** They are matched on their full command
line:

- the node executables, `install/<package>/lib/<package>/<node>`, for
  `radar_agent_node`, `rf_agent_node`, `acoustic_agent_node`, `eo_agent_node`,
  `interpretation_node`, `candidate_transition_node`,
  `mission_transition_node`, `dispatch_transition_node`,
  `scripted_supervisor_node` and `intruder_node`;
- the launch files `sensing.launch.py`, `tbcspn.launch.py`,
  `supervisor.launch.py` and `intruder.launch.py`.

Matching the executable path, not the bare node name, keeps an editor with a
node's source file open from being taken for the node. The scenario's own
nodes (vehicle workers, safety boards, bridges) belong to `make demo-coastal`.
They are not matched, and they stay up from one run to the next.

**Why the guards exist.** In two runs of the thesis campaign, an intruder left
over from an earlier run was still alive, and the bag recorded the ground truth
of two intruders at once. Nothing checked for it, and the mixed trajectories
went into the data. In a later campaign, the scenario check of one run
received `/clock`, but the nodes of the run did not: the chain published
nothing, and the run ended as a run without a ConfirmedThreat, which the
campaign counted as a valid result.

## Verdict

The script compares each vehicle's position before and after the decision:

```text
  UAV0: MOVED 88.6 m   (-23.991900,-23.954900,12.019400 -> -0.119792,61.279400,15.116100)
  UAV1: still (0.0 m)   24.024900,-24.018700,19.952600
  UGV : MOVED 3.6 m   (-18.252800,-14.258200,0.047100 -> -14.690700,-13.864500,0.047100)
```

A vehicle is `MOVED` if it travelled more than `MOVE_THRESHOLD_M` (0.5 m by
default; the hover alone jitters by about 0.1 m). It is `still` otherwise, and
`unknown` if Gazebo returned no position.

The verdict is a quick visual check, not a metric. It is meaningful for the
UAVs, which hold their hover until they get a task. The UGV patrols the shore,
so it normally reads `MOVED` with or without a task; its task shows in the
dispatch log. The metrics come from the bag.

## Recording

`record_run.sh` records these topics:

- the chain: `/obs_tokens`, `/interp_tokens`, `/mission_tokens`,
  `/vehicle_tasks`, `/supervisor_auth`;
- the intruder: `/intruder/ground_truth`, `/intruder/active`;
- the vehicles: `/fmu/out/vehicle_local_position_v1`,
  `/px4_1/fmu/out/vehicle_local_position_v1`,
  `/px4_2/fmu/out/vehicle_local_position_v1`;
- the safety layer of each vehicle (UAV0 in the root namespace, UAV1 in
  `/px4_1`, the UGV in `/px4_2`): `safety_status`, `actuator_cmd_safe` and
  `drone/proximity`, and for the two UAVs the setpoint before and after the
  safety gate, `trajectory_setpoint_proposed` and `fmu/in/trajectory_setpoint`;
- the simulation clock, `/clock`.

The recorder runs without `--use-sim-time`, which can stall it at startup.
`/clock` is recorded, so the analysis maps every message to simulated time.

```bash
ros2 bag info bags/my-run-<timestamp>
python3 scripts/metrics/audit_timing.py bags/my-run-*
```

## Teardown

- Ctrl-C or SIGTERM ends a run in any phase, including the wait for the
  ConfirmedThreat.
- The teardown runs once, on exit. A second Ctrl-C is ignored, so the teardown
  and the closing of the bag always complete.
- With `STAY_UP=0` the run ends after the report, through the same teardown.
- Only what the run started is stopped. The scenario stays up for the next run.

## Logs

Each run overwrites these files:

| File                     | Content                                         |
| ------------------------ | ----------------------------------------------- |
| `/tmp/gs_intruder.log`   | Intruder launch                                 |
| `/tmp/gs_sensing.log`    | Sensing layer, including the seed of each agent |
| `/tmp/gs_tbcspn.log`     | Coordination layer (T1–T7)                      |
| `/tmp/gs_supervisor.log` | Scripted supervisor                             |
| `/tmp/gs_missions.log`   | Released missions, with `MANUAL_AUTH=1`         |
| `/tmp/gs_rosbag.log`     | Recorder (`record_run.sh` only)                 |

## Troubleshooting

| Message                                                   | What to do                                                                                                                                                                                   |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[guard] no /clock within 10s`                            | Start `make demo-coastal` and wait until it is ready                                                                                                                                         |
| `[guard] processes of an earlier run are still alive`     | Stop the run that started them (Ctrl-C in its terminal), or `pkill -f <name>` for each listed process                                                                                        |
| `[guard] /intruder/ground_truth has 2 publisher(s)`       | Another intruder is running: stop it. If none is, the ROS 2 graph cache may still list a killed process: run `ros2 daemon stop` and retry                                                    |
| `[guard] no message on /intruder/ground_truth within 15s` | The nodes of the run receive no `/clock`, or the intruder has stopped (see `/tmp/gs_intruder.log`). A campaign repeats the attempt by itself; by hand, restart `make demo-coastal` and retry |
| `[guard] still alive after SIGTERM, killing:`             | A node did not exit within 5 s and was killed. The run is still valid, but the node's shutdown deserves a look                                                                               |
| `[record] WARNING: a guard stopped the run`               | The bag is kept for inspection. Do not analyse it                                                                                                                                            |
