# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Versions 0.x are development snapshots; 1.0.0 will be the first public,
reproducible release.

## [Unreleased]

### Added

- `scripts/metrics/plot_figures.py`: two figures from recorded runs, as PDF and
  PNG. `trajectories` shows a nominal run and a run with a faulty UAV worker
  from above, on the map of the coastal world read from `coastal.sdf`.
  `verdicts` shows the Safety Board of the faulty UAV over time, with the veto
  left to the worker and applied by the safety gate: the distance of the UAV
  and of the setpoints at PX4 to the wall, the lidar range and the intervals of
  veto. Documented in `docs/experiments/analysis.md`.
- `scripts/metrics/make_results.sh`: runs the analysis scripts on the recordings
  of the experiments and rebuilds every table and figure in `results/`, one step
  per output. A step whose recordings are missing is skipped and named.
  Documented in `docs/experiments/analysis.md`.
- An EO-evidence table in `scripts/metrics/analyze_campaign.py`: for the runs
  with a ConfirmedThreat in which UAV0, which carries the EO camera, stays at
  its post, the EO pass, the last ConfirmedThreat after the last EO
  confirmation, the age of the EO confirmation fused into it, and the
  CandidateTargets per second during the pass. `runs.csv` has the five values of
  each run. Documented in `docs/experiments/analysis.md`.
- `CITATION.cff`, so that GitHub offers the citation of the software, and two
  pages of documentation: `docs/getting-started.md` (requirements, the pinned
  PX4 version, installation, the coastal scenario, a run of the pipeline) and
  `docs/architecture.md` (the layers, the tokens, the transitions, the
  supervisor and the safety layer).

### Changed

- The README is a short overview of the project, with links to the
  documentation; the detail moved to `docs/`.
- `scripts/metrics/audit_timing.py` names the constant-offset projection of the
  authorisation after its method: the columns `t_auth_thesis` and
  `confirmed_to_auth_thesis` of its CSV are now `t_auth_offset` and
  `confirmed_to_auth_offset`, and its report calls section [A] the chain
  latencies.

### Removed

- The web dashboard (`src/web_dashboard`), with `make/web.mk` and the
  `demo-web` target: it showed the tokens of the earlier coordinator, which the
  TB-CSPN chain does not use. The supervisor console in `console/` takes its
  place.
- From the resilience suite in `scripts/resilience`, the tests of the earlier
  coordinator (`test_forged_tokens.py`, `test_dropped_tokens.py`) and the
  configurations of the urban and four-agent scenarios (`uav_r1.yaml`,
  `ugv_r2.yaml`, `swarm_4.yaml`), with the `test-resilience-uav`,
  `test-resilience-ugv`, `test-resilience-swarm` and `test-resilience-all`
  targets. The suite keeps the two Safety Board tests, sensor staleness and
  sensor spike, on the mock pipeline: `make test-resilience-mock`.
- The urban demos and the two-vehicle swarm demo: the worlds `urban_uav.sdf`
  and `urban_ugv.sdf`, the launch files `uav_urban_pipeline.launch.py`,
  `ugv_urban_pipeline.launch.py` and `swarm_pipeline.launch.py`, the helpers
  `scripts/sim/launch_uav_swarm.sh` and `launch_ugv_swarm.sh`, and the targets
  `px4-gui-uav-urban`, `px4-gui-ugv-urban`, `demo-swarm`,
  `demo-px4-uav-urban`, `demo-px4-ugv-urban`, `demo-uav-urban-pipeline`,
  `demo-ugv-urban-pipeline`, `demo-record-uav` and `demo-record-ugv`. The
  coastal scenario is the only scenario of the repository.
- The single-vehicle demos: the launch files `uav_pipeline.launch.py` and
  `ugv_pipeline.launch.py`, the differential rover of `guarded_swarms_safety`
  (`models/rover_differential_lidar` and its airframe in `px4_airframes`), and
  the targets `px4-run-uav`, `px4-run-ugv`, `px4-gui-uav`, `px4-gui-ugv`,
  `px4-config`, `px4-reset-params`, `demo-px4-uav`, `demo-px4-rover`,
  `demo-px4-bridge`, `demo-px4-bridge-rover`, `demo-safety-board-uav` and
  `demo-safety-board-rover`. Also `setup-worlds`, which only listed the
  worlds.
- `offboard_control_node` and `rover_control_node` from
  `guarded_swarms_control`: only the removed demos started them. In the coastal
  scenario `uav_worker_node` and `ugv_worker_node` control the vehicles.
- `command_bridge_node` from `guarded_swarms_control`, with the `demo-bridge`
  and `demo-pipeline` targets: it turned the authorisations of the earlier
  coordinator (`AuthToken`) into actuator commands for the Safety Board. In the
  coastal scenario the workers propose the actuator commands.
- The earlier coordinator: the `guarded_swarms_coordinator` package, the tools
  in `src/tools` (its launch file, a Tkinter dashboard and their guides), the
  messages `Token`, `GeometryToken` and `AuthToken`, and the
  `demo-coordinator`, `demo-coordinator-batch` and `demo-tkinter` targets. The
  TB-CSPN chain of `guarded_swarms_tbcspn` takes its place.
- The analysis scripts that `analyze_campaign.py`, `analyze_faults.py`,
  `analyze_scaling.py` and `audit_recordings.py` replace: `metrics_chain.py`,
  `metrics_counterfactual.py`, `metrics_detection.py`, `metrics_layer.py`,
  `metrics_scalability.py`, `metrics_veto.py`, `aggregate_layer.py`,
  `aggregate_metrics.py` and `thesis_receive_axis.py`.
- The coordination-overhead bench (`scripts/bench/bench_coordination.sh` and
  `scripts/pipeline/coord_mission_injector.py`), the attack-vector check
  `scripts/pipeline/test_vector.sh`, the authorisation timing stub
  `scripts/tools/time_auth_stub.sh`, and `scripts/record/record_demo.sh` with
  the `demo-record-mock`, `demo-replay` and `demo-bag-info` targets.
- `coordination.launch.py` and the `demo-coordination` target. The coordination
  layer runs from `scripts/pipeline/test_pipeline.sh`,
  `scripts/pipeline/demo_console.sh`, or its three launch files.
- Unused make variables (`BUILD_DIR`, `KILL_PX4`, `KILL_GAZEBO`, `KILL_ROS2`,
  `CLEANUP_TMP`, `COASTAL_UGV_WAYPOINTS`) and the JavaScript entries of
  `.gitignore`.
- The `px4_ros_com` submodule: nothing in the repository uses it. The nodes
  need only `px4_msgs`.
- The `sync_threshold_s` parameter of `mission_transition_node` (T6), which
  the node declared but never read: T6 releases a mission while a
  ConfirmedThreat and an authorisation for the same target are both valid.
  `tbcspn.launch.py` no longer passes it to T6; T3 and T5 keep it.

### Fixed

- The Safety Board tests of the resilience suite publish the IMU as well. The
  board vetoes while a sensor has never been received, so without it the board
  stayed unsafe for the whole test: every check of a safe verdict failed, and
  the checks of an unsafe verdict passed whatever the sensors said. The
  staleness test also sends the command it expects to be vetoed after the
  sensors have gone stale rather than before, and `mock.yaml` takes the
  staleness timeout of the board, 2 s.
- `make test-resilience-mock` stops the mock pipeline with SIGINT, so that the
  launch file stops the safety board as well, and matches the launch file only.
  It used SIGKILL, which left the board running, with a pattern that also
  matched the shell of the recipe: the target was killed, and ended with an
  error even when every test passed.
- `scripts/kill_all.sh` also stops the scripted supervisor, the console bridge
  and the mock sensor publisher.

## [0.4.0] - 2026-11-18

### Added

- `T3_WINDOW_S` in `scripts/pipeline/test_pipeline.sh` and
  `tbcspn.launch.py`: the synchronisation window of T3 alone, in seconds,
  read from the environment as `RF_LABEL` is, so that the CandidateTarget
  join can be varied while T5 and T6 keep the shared `sync_threshold_s`
  (3 s). Unset, T3 shares it as before. `test_pipeline.sh` refuses a value
  that is not a number (exit 2), and `scripts/experiments/run_campaign.sh`
  accepts it as a scenario variable.
- Seven configurations in `scripts/experiments/configurations.conf`:
  `auth-delay-5s`, `auth-delay-10s` and `auth-delay-20s` delay the supervisor
  decision after the first ConfirmedThreat and record 20 s after it
  (`REACT_S=20`); `t3-window-500ms`, `t3-window-1s`, `t3-window-2s` and
  `t3-window-4s` set the window of T3.
- A threat-window table in `scripts/metrics/analyze_campaign.py`: for the
  runs with an authorise decision, how long the threat was confirmed and
  valid, and whether the authorisation, while valid, met a valid
  ConfirmedThreat, which is when T6 releases a mission. A configuration that
  sets `T3_WINDOW_S` adds a clean-run check, that T3 logged that window at
  start-up, and the Runs table gives the window T3 ran with. Documented in
  `docs/experiments/analysis.md`.
- `N_UAVS`: the coastal scenario flies from 2 to 8 UAVs, with the UGV. The
  fleet is described in `src/guarded_swarms_bringup/config/coastal_fleet.yaml`
  (PX4 instance, spawn pose and hover altitude of each vehicle), installed
  with the package and read by `scripts/sim/coastal_up.sh`,
  `coastal_pipeline.launch.py` and `tbcspn.launch.py`, which gives the UAVs to
  the dispatch transition (T7). `coastal_up.sh` starts one uXRCE-DDS agent and
  one PX4 instance per vehicle and waits for all of them, and
  `coastal_pipeline.launch.py` brings up the same nodes for every UAV. The
  UAVs past the first two are interceptors only. With the default of 2 the
  scenario, T7 and `make demo-coastal` are as before. `test_pipeline.sh`
  refuses to start (exit 2) unless one PX4 instance runs for each UAV and one
  for the UGV, and `scripts/record/record_run.sh` records the position, the
  safety layer and the setpoints of every UAV. Documented in
  `docs/experiments/campaigns.md`.
- Four configurations in `scripts/experiments/configurations.conf`, `uav-2`,
  `uav-4`, `uav-6` and `uav-8`: the whole chain with that many UAVs, with
  `THREAT_TIMEOUT` and `READY_TIMEOUT_S` raised for the slower simulation.
  `scripts/experiments/run_campaign.sh` accepts `N_UAVS` and
  `READY_TIMEOUT_S` as scenario variables.
- `scripts/pipeline/sim_sleep.py`: waits a number of seconds of simulated
  time on `/clock`, and gives up if the clock stops advancing. Documented in
  `docs/scripts/pipeline.md`.
- `scripts/metrics/analyze_scaling.py`: the tables of the configurations that
  set `N_UAVS`, on the runs that `analyze_campaign.py` uses, with one more
  check: that T7 logged that fleet at start-up. For each fleet size it gives
  the times of the chain, the time from the first observation to the first
  task also in real time, the real-time factor, the messages of a mission (the
  tokens of the chain, the UAV positions that T7 reads, and the safety layer),
  the interceptor, and the vehicles whose Safety Board never reported safe.
  The topics published on the real clock are also counted at real-time rates.
  Documented in `docs/experiments/analysis.md`.
- `scripts/metrics/peak_speed.py`: the peak horizontal speed of every vehicle
  of one or more recordings, away from its spawn point and back toward it,
  with the time of each in simulated time, and the first vehicle task.
  Documented in `docs/experiments/analysis.md`.

### Changed

- `scripts/experiments/run_campaign.sh` accepts digits after the first
  character in the variable names of a configuration, as in `T3_WINDOW_S`.
- `guarded_swarms_tbcspn` depends on `guarded_swarms_bringup` at run time:
  `tbcspn.launch.py` reads the fleet file.

### Fixed

- `scripts/sim/coastal_up.sh` started every PX4 instance with its uXRCE-DDS
  client on port 8888, the agent of UAV0, and `scripts/sim/px4_configure.sh`
  then moved the client to its own port by restarting it. With many instances
  the restart could hang, and the start-up with it. Each instance now starts
  on its own port (`PX4_UXRCE_DDS_PORT` of the PX4 startup script), and
  `px4_configure.sh`, given the same variable, leaves its client running;
  `make demo-coastal` keeps the restart. `coastal_up.sh` also stops when
  `px4_configure.sh` takes more than `CONFIGURE_TIMEOUT_S` (60 s).
- A PX4 instance at times reports its simulated battery unhealthy at start-up:
  the Safety Board of the vehicle then receives no battery status and vetoes
  all its commands, so the vehicle stays put for the whole run.
  `scripts/sim/coastal_up.sh` now stops the start-up at once when the log of a
  PX4 instance reports it, and a campaign starts the scenario again.
- `scripts/pipeline/test_pipeline.sh` waited `AUTH_DELAY_S + REACT_S` after
  the threat, and `OBSERVE_S` with `EXPECT_THREAT=no`, on the real clock. With
  the simulation slower than real time, the recording then covered less
  simulated time than asked, in proportion to the real-time factor. The waits
  are now in simulated time, through `scripts/pipeline/sim_sleep.py`, and a
  clock that stops during a wait stops the run (exit 3).
- `scripts/sim/coastal_up.sh` waited for Gazebo by subscribing to the world
  statistics (`gz topic -e`), and that command at times crashed with a
  segmentation fault while the server was starting: the wait went on, but the
  crash was printed. It now asks for the publishers of the topic
  (`gz topic -i`), without subscribing.
- `scripts/bench/bench_vehicles.sh` spawned its vehicles on a line through the
  first row of town blocks of the coastal world: two inside a building, three
  within 2 m of one. They now spawn on free ground along the UAV launch pads,
  the first two on the pads of the scenario, each at least 10 m from any
  building or obstacle. `MAX` is at most 9, one spawn point per vehicle.

## [0.3.0] - 2026-11-11

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
- `scripts/metrics/analyze_faults.py`: the tables of the obstacle-injection
  configurations of a campaign (faulty UAV worker, forged mission), on the runs
  that `scripts/metrics/analyze_campaign.py` uses. Impact rate with its 95%
  Wilson interval, impact speed, closest distance to the wall, the speed at the
  lidar trip and the intervention of the safety layer message by message in
  simulated time, the commands that reached PX4 while the board reported unsafe
  and still drove the UAV toward the wall, and the holds of the gate on the
  other UAVs. Documented in `docs/experiments/analysis.md`.
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
- `scripts/pipeline/publish_observations.py`: a command-line node that
  publishes forged `ObsToken` messages to `/obs_tokens` for a target that is
  not there - a radar track, an RF signature and an EO fix that share one
  target_id - with the fields of the four sensing agents. Run with those
  agents off, the injected stream is the only evidence, and the chain fuses it
  into a ConfirmedThreat. It publishes only once every subscriber of
  `/obs_tokens` has matched it, so the recording holds the whole stream from
  its first observation, and confirms the ConfirmedThreat on `/interp_tokens`.
- Two configurations for a forged-observation test in
  `scripts/experiments/configurations.conf`: `forge-obs-authorise` and
  `forge-obs-deny`. Both switch the four sensing agents off and, through the
  new `FORGE_OBS=ghost` of `scripts/pipeline/test_pipeline.sh`, inject forged
  observations so a ConfirmedThreat forms from them alone; the supervisor then
  authorises (`forge-obs-authorise`) or withholds it (`forge-obs-deny`). They
  check that a mission forms only under authorisation.
  `scripts/metrics/audit_recordings.py` expects of them a mission and a threat
  without a mission.
- `scripts/pipeline/publish_clock.py`: a command-line node that publishes
  `/clock` for the Safety Board bench, advancing simulated time at a fixed
  rate and, with `--freeze-at`, holding it at a chosen instant. It is the
  board's clock source when no simulator is running.
- `scripts/pipeline/publish_sensors.py`: a command-line node that feeds the
  Safety Board its four readings and a constant command on the wall clock,
  independently of the clock the board reads. `--stop-at` stops the sensor
  streams at an instant; `--danger-at` turns the proximity reading unsafe.
- `scripts/experiments/run_clock_bench.sh`: a campaign that exercises the
  Safety Board in isolation under clock denial, over two arms with the same
  healthy sensors - the clock advancing (the board clears the command) and the
  clock held at zero (the board fails safe and vetoes every command, blocking
  the vehicle) - RUNS runs each, recording every run to its own bag with a
  manifest. Documented in `docs/experiments/clock.md`.
- `scripts/metrics/analyze_clock.py`: the tables of a clock-denial bench, from
  its bags: per arm, the share of runs that met the expected outcome with its
  95% Wilson interval, the share of the run the board denied the command and
  reported unsafe, and whether the simulated clock advanced. Documented in
  `docs/experiments/clock.md`.

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
- `scripts/experiments/run_campaign.sh` accepts `VETO_BY`, `UAV_FAULT`,
  `FORGE_MISSION` and `FORGE_OBS` in a configuration, and passes the variables
  of the configuration to `scripts/sim/coastal_up.sh` as well as to
  `scripts/record/record_run.sh`.
- `scripts/pipeline/test_pipeline.sh` accepts `FORGE_MISSION` (`none` or
  `obstacle`): with `obstacle` it publishes one unauthorised `MissionToken`
  after the supervisor's decision, to exercise the safety layer. Off by
  default, so every other run is unchanged.
- `scripts/pipeline/test_pipeline.sh` accepts `FORGE_OBS` (`none` or `ghost`):
  with `ghost` it injects forged observations before the wait for the threat,
  through `scripts/pipeline/publish_observations.py`, and turns a missing
  threat into a guard-stop so the campaign repeats the run. Off by default.

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
