# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Versions 0.x are development snapshots; 1.0.0 will be the first public,
reproducible release.

## [Unreleased]

### Added

- `scripts/metrics/audit_recordings.py`: checks that recorded runs are clean
  (one intruder ground-truth source, a `/clock` that never goes back, one
  producer per token stream, one target, no stray supervisor decision, every
  token in simulated time) and recomputes their time figures on the token
  stamps and on the recorder receive time. For the Safety Board runs of
  `scripts/record/record_veto.sh` it measures the reaction time message by
  message. Documented in `docs/experiments/analysis.md`.
- `scripts/metrics/analyze_campaign.py`: the tables of a campaign of
  `scripts/experiments/run_campaign.sh`, from its manifest and bags: outcomes
  with their 95% Wilson interval, the times of the chain in simulated time,
  the authorisation, the detection by modality and the quality of the runs,
  as Markdown and CSV. Every run is checked as in `audit_recordings.py`; a
  run that is not clean is left out and listed, and can be repeated in a
  later campaign with the same configuration and seed. Documented in
  `docs/experiments/analysis.md`.
- `px4_safety_gate_node`, in `guarded_swarms_control`: a node on the setpoint
  path of a UAV, between its worker and PX4. With `veto_by` set to `worker`,
  the default, it forwards the setpoints of the worker unchanged. With
  `gate`, it enforces the Safety Board veto whatever the worker proposes:
  once the UAV is 3 m up, it holds it at its position while
  `safety_status` reports unsafe or stops arriving for more than 0.5 s, and
  forwards again 2 s after the last unsafe status. Documented in
  `docs/packages/guarded_swarms_control.md`.
- Fault mode of `uav_worker_node`, for fault-injection runs. With the new
  parameter `fault` set to `obstacle`, the worker flies its first task to a
  fault target (`fault_target_x`, `fault_target_y`, `fault_altitude`) instead
  of the designated target, and from then on ignores the Safety Board veto,
  later tasks, the updates of the target and the expiry of the mission. Off
  by default (`none`). Documented in `docs/packages/guarded_swarms_control.md`.
- Launch arguments `veto_by` (`worker` or `gate`) and `uav_fault` (`none` or
  `obstacle`) in `src/guarded_swarms_bringup/launch/coastal_pipeline.launch.py`,
  which `scripts/sim/coastal_up.sh` sets from `VETO_BY` and `UAV_FAULT`. The
  fault targets of the coastal scenario are the centres of two buildings, one
  per UAV.
- Three configurations for a faulty UAV worker in
  `scripts/experiments/configurations.conf`: `fault-worker` (the veto is left
  to the faulty worker), `fault-gate` (the safety gate enforces it) and
  `nominal-gate` (the gate enforces it, and no worker is faulty). They record
  30 s after the decision instead of 10. `scripts/metrics/audit_recordings.py`
  expects of them the outcome of the nominal chain.
- `scripts/metrics/analyze_faults.py`: the tables of the faulty-UAV-worker
  configurations of a campaign, on the runs that
  `scripts/metrics/analyze_campaign.py` uses. Impact rate with its 95% Wilson
  interval, impact speed, closest distance to the wall, the intervention of
  the safety layer message by message in simulated time, the commands that
  reached PX4 while the board reported unsafe, and the holds of the gate on
  the UAVs without a fault. Documented in `docs/experiments/analysis.md`.
- `scripts/pipeline/publish_mission.py`: a small command-line node that
  publishes one `MissionToken` to `/mission_tokens`, with the fields given on
  the command line, to place a mission on the dispatch topic directly. It
  republishes and watches `/vehicle_tasks` until the dispatch transition turns
  the mission into a task, and exits non-zero if that does not happen within a
  timeout, so `scripts/pipeline/test_pipeline.sh` stops the run (exit 3) and the
  campaign repeats it with the same seed.
- Two configurations for a forged-mission test in
  `scripts/experiments/configurations.conf`: `forge-worker` and `forge-gate`.
  Both run with the authorisation withheld (`DECISION=deny`) and, through the
  new `FORGE_MISSION=obstacle` of `scripts/pipeline/test_pipeline.sh`, publish
  one unauthorised `MissionToken` after the decision, to check that the safety
  layer holds the UAV it is dispatched to. `forge-worker` leaves the veto to
  the worker, `forge-gate` to the safety gate.
  `scripts/metrics/analyze_faults.py` covers them alongside the faulty-worker
  configurations.

### Changed

- `uav_worker_node` publishes its setpoints on the topic of the new
  `setpoint_topic` parameter, `fmu/in/trajectory_setpoint` by default. In the
  coastal scenario the UAV workers publish on `trajectory_setpoint_proposed`,
  and one `px4_safety_gate_node` per UAV passes the setpoints on to PX4
  (`src/guarded_swarms_bringup/launch/coastal_pipeline.launch.py`). Both
  gates have `veto_by` set to `worker` by default, so the UAVs fly as before.
- `scripts/record/record_run.sh` also records the safety layer of each
  vehicle: `safety_status`, `actuator_cmd_safe` and `drone/proximity`, and for
  the two UAVs the setpoint before and after the safety gate.
- `scripts/experiments/run_campaign.sh` accepts `VETO_BY`, `UAV_FAULT` and
  `FORGE_MISSION` in a configuration, and passes the variables of the
  configuration to `scripts/sim/coastal_up.sh` as well as to
  `scripts/record/record_run.sh`.
- `scripts/pipeline/test_pipeline.sh` accepts `FORGE_MISSION` (`none` or
  `obstacle`): with `obstacle` it publishes one unauthorised `MissionToken`
  after the supervisor's decision, to exercise the safety layer. Off by
  default, so every other run is unchanged.

### Fixed

- `scripts/pipeline/test_pipeline.sh` stops a run with exit code 3 when no
  message of the intruder's ground truth arrives within 15 s, after the
  launch or before the result. The intruder publishes it on simulated time,
  so the check fails when the nodes of the run receive no `/clock`. Such a
  run published nothing of the chain and ended as a run without a
  ConfirmedThreat, which `scripts/experiments/run_campaign.sh` counted as
  valid; a campaign now repeats it. The check is
  `guard_ground_truth_flowing`, in `scripts/pipeline/run_guards.sh`.
- `uav_worker_node` holds the UAV in place under a Safety Board veto. It
  re-sent its last setpoint, which during a task is the goal, so the UAV kept
  flying toward it; it now holds the position and heading it has when the
  veto begins, read from `fmu/out/vehicle_local_position_v1`. The veto
  applies once the UAV is airborne (first safe verdict, or half the hover
  altitude): on the ground the board vetoes for stale sensors and for the
  altitude floor, and holding the position there would keep the UAV from
  taking off.
- `uav_worker_node` faces the direction of travel while its setpoint is more
  than 3 m away, on a task and on the way back to its hover point, so the
  single-ray forward lidar of its Safety Board looks ahead. Near a task goal
  it keeps its heading; in hover over its spawn point it faces north, as
  before.
- The Safety Boards of the UAVs veto attitudes beyond 60° instead of 30°
  (`src/guarded_swarms_bringup/launch/coastal_pipeline.launch.py`). The
  autopilot tilts a multirotor up to 45° (PX4 `MPC_TILTMAX_AIR`) to
  accelerate, so the 30° limit vetoed the interceptor as it accelerated
  toward its target. 60° is the attitude-failure threshold of PX4's failure
  detector (`FD_FAIL_P`, `FD_FAIL_R`). The rover keeps 30°.
- The UAV workers fly every transit, to a task goal and back to the hover
  point, at a bounded speed instead of the autopilot's maximum
  (`uav_worker_node`), and their Safety Boards veto proximity below 10 m
  instead of 1.5 m
  (`src/guarded_swarms_bringup/launch/coastal_pipeline.launch.py`). The worker
  handed PX4 the far goal, which it flew at `MPC_XY_VEL_MAX` (12 m/s): braking
  from that speed takes ~28 m, which would need a proximity threshold of some
  30 m and stop the UAV far from anything ahead, its target included. The
  worker now advances the setpoint toward the goal at `MPC_XY_CRUISE`
  (5 m/s), measured in simulated time, so the UAV brakes in ~6 m. The rover is
  unchanged.
- `scripts/sim/coastal_down.sh` also matches the node executables whose
  package or node name contains a digit, such as `px4_safety_bridge_node`
  and `px4_safety_gate_node`. If one of them survived the stop of the
  scenario launch, it was neither killed nor reported.

## [0.2.0] - 2026-11-05

### Added

- `scripts/metrics/audit_timing.py`: timing audit of the coordination chain
  from recorded bags, in simulated time. It maps receive times to simulated
  time through the recorded `/clock`, flags runs with more than one intruder
  ground-truth source, decomposes the authorisation path and writes per-run
  values to CSV.
- `scripts/metrics/thesis_receive_axis.py`: reproduces the latency tables of
  the thesis (6.1 and 6.2) on the recorder's receive clock, to document how
  those figures were computed.
- `scripts/tools/time_auth_stub.sh`: times the steps that
  `scripts/pipeline/test_pipeline.sh` performs between the first
  ConfirmedThreat and the authorisation.
- `guarded_swarms_supervisor` package with `scripted_supervisor_node`, which
  stands in for the human supervisor of T6 in automated runs. At the first
  ConfirmedThreat of each target it waits a configurable delay in simulated
  time, then issues one decision (authorise, deny or none) on
  `/supervisor_auth`, stamped in simulated time and published with the
  RELIABLE + TRANSIENT_LOCAL QoS of T6's subscription. `supervisor.launch.py`
  reads `DECISION`, `AUTH_DELAY_S` and `AUTH_TTL_S` from the environment.
- `docs/`: project documentation, starting with the page of the
  `guarded_swarms_supervisor` package.
- `seed` parameter in the four sensing agents: a value above 0 fixes the
  random generator, 0 draws a seed at random, and the seed in use is logged
  at start-up. `sensing.launch.py` takes the seed of the run from `SEED` and
  gives each agent its own (`SEED+1` to `SEED+4`); `test_pipeline.sh` and
  `record_run.sh` draw and print one when `SEED` is unset.
- `scripts/pipeline/run_guards.sh`: checks shared by `test_pipeline.sh` and
  `record_run.sh`. A run refuses to start (exit 2) if the scenario is down or
  processes of an earlier run are still alive, and stops (exit 3) if the
  intruder's ground truth does not have exactly one source. The run scripts
  are documented in `docs/scripts/pipeline.md`.
- `scripts/experiments/run_campaign.sh`: unattended campaigns of recorded
  runs over the configurations of `scripts/experiments/configurations.conf`.
  Every run starts from a freshly started scenario; the runs alternate
  between the configurations, and run _n_ has the same seed in all of them.
  A campaign can be stopped with Ctrl-C or after `MAX_HOURS` and continued
  later with the same command; every attempt has its own folder and its own
  line in `manifest.csv`, and nothing is overwritten. Documented in
  `docs/experiments/campaigns.md`.
- `scripts/sim/coastal_up.sh` and `scripts/sim/coastal_down.sh`: start the
  coastal scenario with the settings of `make demo-coastal`, without
  terminals, and wait until it is ready; stop it and check that nothing
  survives.
- This changelog.

### Changed

- `scripts/pipeline/test_pipeline.sh` authorises through the scripted
  supervisor instead of the command-line stub, so nothing but the
  supervisor's own delay sits between the first ConfirmedThreat and the
  decision. New variables `AUTH_DELAY_S` and `AUTH_TTL_S`; `DECISION` also
  accepts `none`; `AUTH_TARGET` and `SUPERVISOR` are removed. The starting
  poses for the verdict are taken before a threat can form.
- `scripts/record/record_run.sh` passes `AUTH_DELAY_S` and `AUTH_TTL_S` to
  the run.
- `scripts/record/record_run.sh` runs the pre-run checks before it starts the
  recorder, warns when a guard stopped the run, and exits with the code of
  `test_pipeline.sh`.
- `scripts/pipeline/test_pipeline.sh` ends on its own, with exit code 0, once
  the report is printed if `STAY_UP=0`; by default it still stays up until
  Ctrl-C. `scripts/record/record_run.sh` writes the bag to `BAG_DIR` when it
  is set.
- The manual authorisation command shown by `tbcspn.launch.py` publishes with
  TRANSIENT_LOCAL durability, as T6's subscription requires.
- `results/` is ignored by git: analysis outputs are regenerated from the
  bags by the scripts in `scripts/metrics/`.

### Fixed

- `scripts/pipeline/test_pipeline.sh` no longer stops the scenario's vehicle
  workers on exit: it stops only what it started, and checks that nothing
  survives.
- The verdict of `test_pipeline.sh` measures how far each vehicle travelled
  and reports it as moved only beyond `MOVE_THRESHOLD_M` (default 0.5 m),
  instead of comparing positions as text.
- `test_pipeline.sh` and `record_run.sh` run their teardown once, and a
  second Ctrl-C no longer interrupts it.
- Ctrl-C takes effect at once while `test_pipeline.sh` waits for the
  ConfirmedThreat, instead of when the wait ends.
- The intruder and the four sensing agents run on simulated time: the
  intruder's start delay, motion and ground truth, and the agents' scans.
  On the wall clock the intruder covered its route faster in simulated time
  whenever the real-time factor was below 1 (6.2 m/s instead of 6.0 at a
  factor of 0.97) and the agents scanned more often, so latencies measured
  in simulated time depended on the load of the machine. The scripted
  supervisor also checks its pending decisions on simulated time.

### Known issues

Found after the release.

- `scripts/pipeline/test_pipeline.sh` checks `/clock` only before the launch.
  If the nodes of the run then receive no `/clock`, the chain publishes
  nothing and the run ends without a ConfirmedThreat (exit code 1), which
  `scripts/experiments/run_campaign.sh` counts as a valid run. In the bag of
  such a run, `/clock` and the intruder's ground truth are missing or stop
  early.
- `scripts/sim/coastal_down.sh` does not match the node executables with a
  digit in their name, such as `px4_safety_bridge_node`: if one survived the
  stop of the scenario launch, it would be neither killed nor reported.

## [0.1.0] - 2026-11-05

Snapshot of the code described in the bachelor's thesis (University of
Molise, 2026), tagged on the commit of 2026-09-23. The tag annotation carries
the full reference to the thesis.

### Known issues

Found after the thesis.

- The latency tables of the thesis (6.1 and 6.2) were computed on the
  recorder's receive clock, not on simulated time.
  `scripts/metrics/audit_timing.py` recomputes them in simulated time.
- In automatic mode, `scripts/pipeline/test_pipeline.sh` authorises through a
  command-line stub: three `gz model` calls and a short-lived
  `ros2 topic pub` put 12-15 s between the first ConfirmedThreat and the
  authorisation. The delay comes from the test harness, not from a
  supervisor decision; in one run of the thesis campaign no mission was
  released although the threat was still valid.
- The test scripts do not check that the nodes of a previous run have
  stopped: two runs of the thesis campaign recorded two intruder
  ground-truth sources.
- On exit, `scripts/pipeline/test_pipeline.sh` also stops the vehicle
  workers started by the scenario, so from the second run of a session the
  vehicles have no controller.
- The verdict of `test_pipeline.sh` compares positions as text, so the
  jitter of a hovering vehicle counts as movement.
- On Ctrl-C, `test_pipeline.sh` and `record_run.sh` run their teardown
  twice, and a Ctrl-C pressed while `test_pipeline.sh` waits for the
  ConfirmedThreat takes effect only when the wait ends, up to 60 s later.
- Under a veto, `uav_worker_node` keeps sending its last commanded goal
  instead of holding its current position.
- `uav_worker_node` always commands yaw 0 (north), so the single-ray forward
  lidar does not look along the direction of travel.
- The Safety Boards of the UAVs veto attitudes beyond 30°, while the
  autopilot tilts a multirotor up to 45° (PX4 `MPC_TILTMAX_AIR`) to
  accelerate: an interceptor accelerating toward its target trips the
  attitude veto. Since the veto does not hold the UAV, these vetoes have no
  effect.
- The sensing agents seed their random generators from
  `std::random_device`, so a run cannot be repeated with the same noise.
- The intruder and the sensing agents advance on the wall clock, while
  Gazebo, PX4 and the coordination chain run on simulated time. At a
  real-time factor of 0.97 the intruder, commanded at 6.0 m/s, moves at
  6.2 m/s in simulated time, and the gap grows as the simulation slows down.
- `scripts/kill_all.sh` (`make kill-all`) matches node names anywhere in a
  command line, so it also kills an editor open on a node's source file.
- `scripts/metrics/metrics_veto.py` samples the Safety Board status on a
  0.1 s grid that starts with the first status message. For a hazard that
  starts while the board is safe, the reaction time it gives includes the
  wait for the next grid point: in the recorded runs, 100 ms more than the
  reaction measured message by message. For a hazard that starts while the
  board is already unsafe, as when hazards follow one another, it gives the
  offset between the sensor and status streams, not a reaction time. Its
  isolation check passes by construction, since `record_veto.sh` records
  only the Safety Board topics. `scripts/metrics/audit_recordings.py`
  measures the reaction message by message.
