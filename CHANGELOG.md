# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Versions 0.x are development snapshots; 1.0.0 will be the first public,
reproducible release.

## [Unreleased]

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
  runs over the configurations of `scripts/experiments/configurations.conf`
  (the eleven of the thesis campaign). Every run starts from a freshly
  started scenario; the runs alternate between the configurations, and run
  _n_ has the same seed in all of them. A campaign can be stopped with Ctrl-C
  or after `MAX_HOURS` and continued later with the same command; every
  attempt has its own folder and its own line in `manifest.csv`, and nothing
  is overwritten. Documented in `docs/experiments/campaigns.md`.
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
- The sensing agents seed their random generators from
  `std::random_device`, so a run cannot be repeated with the same noise.
- The intruder and the sensing agents advance on the wall clock, while
  Gazebo, PX4 and the coordination chain run on simulated time. At a
  real-time factor of 0.97 the intruder, commanded at 6.0 m/s, moves at
  6.2 m/s in simulated time, and the gap grows as the simulation slows down.
- `scripts/kill_all.sh` (`make kill-all`) matches node names anywhere in a
  command line, so it also kills an editor open on a node's source file.
