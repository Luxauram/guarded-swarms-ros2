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
- The manual authorisation command shown by `tbcspn.launch.py` publishes with
  TRANSIENT_LOCAL durability, as T6's subscription requires.
- `results/` is ignored by git: analysis outputs are regenerated from the
  bags by the scripts in `scripts/metrics/`.

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
- Under a veto, `uav_worker_node` keeps sending its last commanded goal
  instead of holding its current position.
- `uav_worker_node` always commands yaw 0 (north), so the single-ray forward
  lidar does not look along the direction of travel.
- The sensing agents seed their random generators from
  `std::random_device`, so a run cannot be repeated with the same noise.
