# Campaigns

A campaign repeats recorded pipeline runs over a set of configurations, with
no one at the keyboard. Every run starts from a freshly started scenario, so
all runs share the same initial state, and every attempt is logged in a
manifest. A campaign can be split over as many sessions as needed: each
session does the runs that are still missing.

| File                                      | Role                                                                                                           |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `scripts/experiments/run_campaign.sh`     | Runs a campaign: for each run it starts the scenario, records the run, stops the scenario and logs the attempt |
| `scripts/experiments/configurations.conf` | The configurations: a name and the variables that set it apart from the nominal run                            |
| `scripts/sim/coastal_up.sh`               | Starts the coastal scenario without terminals and waits until it is ready                                      |
| `scripts/sim/coastal_down.sh`             | Stops the scenario and anything left of a run, and checks that nothing survived                                |

## Quick start

```bash
RUNS=1 ./scripts/experiments/run_campaign.sh pilot nominal   # one run, to check the set-up
./scripts/experiments/run_campaign.sh full                   # every configuration, 20 runs each
MAX_HOURS=6 ./scripts/experiments/run_campaign.sh full       # a session of at most 6 hours
```

Before starting:

- **Nothing else may run.** The campaign starts and stops the scenario
  itself: close `make demo-coastal` and its terminals first.
- **The code must be committed.** The manifest records the commit of every
  run, so a campaign refuses to start with uncommitted changes to tracked
  files.

To continue a campaign, run the same command again.

## What a run does

1. **Start the scenario** with `coastal_up.sh`: the same sequence and
   settings as `make demo-coastal` (Gazebo, one uXRCE-DDS agent and one PX4
   instance per vehicle, each configured by `px4_configure.sh`, then
   `coastal_pipeline.launch.py`), with no terminals, and with the `VETO_BY`,
   `UAV_FAULT`, `N_UAVS` and `READY_TIMEOUT_S` of the configuration. It
   returns once the scenario is [ready](#starting-and-stopping-the-scenario).
2. **Record the run** with `record_run.sh`, with the variables of the
   configuration, the seed of the run, `STAY_UP=0` (the run ends on its own
   after the report) and `BAG_DIR` set to the folder of the attempt.
3. **Copy the logs** of the run and of the scenario next to the bag.
4. **Stop the scenario** with `coastal_down.sh`.
5. **Log the attempt** in the manifest.

Restarting the scenario for every run puts every run in the same initial
state: the vehicles at their spawn points, the EO camera (carried by UAV0) at
its post, the rover at the start of its patrol.

## Configurations

`configurations.conf` holds one configuration per line: a name, then the
variables that make it differ from the nominal run. It defines twenty-nine
configurations:

| Name                  | Variables                                                                                                               | What it tests                                                        |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `nominal`             | (none)                                                                                                                  | The full chain                                                       |
| `deny`                | `DECISION=deny`                                                                                                         | Authorisation withheld                                               |
| `stale-eo`            | `EO_DELAY_S=12`                                                                                                         | EO confirmation arriving after the threat TTL (10 s)                 |
| `civilian`            | `RF_LABEL=LikelyCivilianTraffic EXPECT_THREAT=no`                                                                       | Conflicting RF evidence                                              |
| `vec-frontal`         | `ATTACK_VECTOR=frontal`                                                                                                 | Frontal ingress                                                      |
| `vec-east-deep`       | `ATTACK_VECTOR=east-deep`                                                                                               | Deep ingress from the east                                           |
| `vec-rear`            | `ATTACK_VECTOR=rear`                                                                                                    | Ingress from the rear                                                |
| `loss-radar`          | `RADAR_ENABLED=false`                                                                                                   | Loss of the radar                                                    |
| `loss-rf`             | `RF_ENABLED=false`                                                                                                      | Loss of the RF sensor                                                |
| `loss-acoustic`       | `ACOUSTIC_ENABLED=false`                                                                                                | Loss of the acoustic sensor                                          |
| `loss-eo`             | `EO_ENABLED=false`                                                                                                      | Loss of the EO camera                                                |
| `fault-worker`        | `VETO_BY=worker UAV_FAULT=obstacle REACT_S=30`                                                                          | A faulty UAV worker flies into a building; the veto is left to it    |
| `fault-gate`          | `VETO_BY=gate UAV_FAULT=obstacle REACT_S=30`                                                                            | The same faulty worker, with the safety gate enforcing the veto      |
| `nominal-gate`        | `VETO_BY=gate REACT_S=30`                                                                                               | The full chain, with the safety gate enforcing the veto and no fault |
| `forge-worker`        | `VETO_BY=worker DECISION=deny FORGE_MISSION=obstacle REACT_S=30`                                                        | An unauthorised mission is injected; the honest worker holds the UAV |
| `forge-gate`          | `VETO_BY=gate DECISION=deny FORGE_MISSION=obstacle REACT_S=30`                                                          | The same injection, with the safety gate enforcing the veto          |
| `forge-obs-authorise` | `RADAR_ENABLED=false RF_ENABLED=false ACOUSTIC_ENABLED=false EO_ENABLED=false FORGE_OBS=ghost REACT_S=15`               | Forged observations fuse into a threat; the supervisor authorises    |
| `forge-obs-deny`      | `RADAR_ENABLED=false RF_ENABLED=false ACOUSTIC_ENABLED=false EO_ENABLED=false FORGE_OBS=ghost DECISION=deny REACT_S=15` | The same forgery, with the authorisation withheld                    |
| `auth-delay-5s`       | `AUTH_DELAY_S=5 REACT_S=20`                                                                                             | The supervisor decides 5 s after the first ConfirmedThreat           |
| `auth-delay-10s`      | `AUTH_DELAY_S=10 REACT_S=20`                                                                                            | The supervisor decides 10 s after the first ConfirmedThreat          |
| `auth-delay-20s`      | `AUTH_DELAY_S=20 REACT_S=20`                                                                                            | The supervisor decides 20 s after the first ConfirmedThreat          |
| `t3-window-500ms`     | `T3_WINDOW_S=0.5`                                                                                                       | Window of T3 at 0.5 s; T5 keeps 3 s                                  |
| `t3-window-1s`        | `T3_WINDOW_S=1`                                                                                                         | Window of T3 at 1 s                                                  |
| `t3-window-2s`        | `T3_WINDOW_S=2`                                                                                                         | Window of T3 at 2 s                                                  |
| `t3-window-4s`        | `T3_WINDOW_S=4`                                                                                                         | Window of T3 at 4 s                                                  |
| `uav-2`               | `N_UAVS=2`                                                                                                              | The full chain with two UAVs and the UGV                             |
| `uav-4`               | `N_UAVS=4 THREAT_TIMEOUT=120 READY_TIMEOUT_S=240`                                                                       | The full chain with four UAVs and the UGV                            |
| `uav-6`               | `N_UAVS=6 THREAT_TIMEOUT=180 READY_TIMEOUT_S=360`                                                                       | The full chain with six UAVs and the UGV                             |
| `uav-8`               | `N_UAVS=8 THREAT_TIMEOUT=300 READY_TIMEOUT_S=600`                                                                       | The full chain with eight UAVs and the UGV                           |

`nominal` and `vec-frontal` set the same scenario, since the frontal vector is
the default, but they are separate configurations, each with its own runs.

The last five configurations record 30 s after the decision (`REACT_S=30`)
instead of 10. With the faulty worker, the flight reaches the building about
10 s after the task, and the rest of the recording shows the impact or the
hold; `nominal-gate` records as long, so that the three compare. The faulty
worker and its targets are described in
[`guarded_swarms_control`](../packages/guarded_swarms_control.md#uav_worker_node-fault-mode).

The `forge-worker` and `forge-gate` configurations run with the authorisation
withheld (`DECISION=deny`), so no mission is released through the chain, and
`FORGE_MISSION=obstacle` instead publishes one unauthorised `MissionToken`
directly, to check that the safety layer holds the UAV it is dispatched to.
`forge-worker` leaves the veto to the worker, `forge-gate` to the safety gate.

The `forge-obs-authorise` and `forge-obs-deny` configurations switch the four
sensing agents off and, through `FORGE_OBS=ghost`, inject forged radar, RF and
EO observations of a target that is not there, so the chain forms a
ConfirmedThreat from the injected evidence alone. The mission then forms only
if the supervisor authorises it: `forge-obs-authorise` authorises,
`forge-obs-deny` withholds it (`DECISION=deny`).

The `auth-delay-*` configurations delay the supervisor decision: it comes
`AUTH_DELAY_S` simulated seconds after the first ConfirmedThreat, instead of
at once as in `nominal`. The decision stays valid for `AUTH_TTL_S` (15 s), and
T6 releases the mission if a ConfirmedThreat is valid at some point in that
time, so these configurations record 20 s after the decision (`REACT_S=20`).

The `t3-window-*` configurations set the synchronisation window of T3 alone,
through `T3_WINDOW_S`. T5 keeps the shared window of 3 s, which is also
the window of T3 in `nominal`.

The `uav-*` configurations run the whole chain with `N_UAVS` UAVs and the UGV
(see [The fleet](#the-fleet)). `uav-2` is the fleet of `nominal`, run with the
others so that the four fleet sizes are compared in the same sessions. More
UAVs slow the simulation down below real time, so these configurations raise
the two waits counted in real seconds: `THREAT_TIMEOUT` of `test_pipeline.sh`
(60 s by default) and `READY_TIMEOUT_S` of `coastal_up.sh` (120 s by default).

The variables are those of the
[pipeline run scripts](../scripts/pipeline.md#configuration), including
`FORGE_MISSION`, `FORGE_OBS` and `T3_WINDOW_S` of `test_pipeline.sh`, plus
`VETO_BY`, `UAV_FAULT`, `N_UAVS` and `READY_TIMEOUT_S` of
[`coastal_up.sh`](#starting-and-stopping-the-scenario).
The campaign accepts only those, each with the values it allows, and checks
the whole file before the first run: a typo stops the campaign at once
instead of producing runs of the wrong scenario. A variable set in the
terminal does not reach the runs; only the configuration file sets the
scenario.

## Order and seeds

The runs alternate between the configurations: run 1 of each, then run 2 of
each, and so on. A campaign stopped halfway is therefore balanced, and
anything that drifts during a session (the temperature of the machine, other
load) affects every configuration alike.

Run _n_ has the same seed in every configuration:

```text
seed = FIRST_SEED + 10 * (n - 1)        1000, 1010, 1020, ...
```

so the configurations are compared on the same noise draws. The step of 10
keeps the runs apart, since each run also gives `SEED+1` to `SEED+4` to the
sensing agents. A repeated attempt of a run keeps its seed.

## Sessions

- **Ctrl-C** closes the run in progress cleanly, stops the scenario and ends
  the session (exit 130). That run is logged as `interrupted` and is redone,
  with the same seed, in the next session.
- **`MAX_HOURS`** ends the session once that many hours have passed: the run
  in progress is completed, no new one is started.
- **Failed attempts.** A run is done once it has a valid outcome (see
  [Outcomes](#outcomes)). An attempt that is not valid is repeated at once,
  with the same seed. After `MAX_ATTEMPTS` failed attempts in a row the run
  is put aside for the rest of the session and the campaign carries on; the
  next session tries it again. No run is given up, so every configuration
  reaches `RUNS` valid runs.
- **A failing set-up.** Two runs put aside one after the other stop the
  session (exit 1): then the problem is the set-up, not a run.
- **Teardown.** If the scenario does not stop cleanly after a run, the
  session stops (exit 1): the next run would not start from a clean state.
- **One session at a time.** A second session of the same campaign refuses to
  start while the first is running.
- **Fixed seeds and code.** A campaign keeps the `FIRST_SEED` it started with,
  and refuses to continue on a different commit unless `ALLOW_NEW_COMMIT=1`.

Nothing is ever overwritten: every attempt has its own folder and its own line
in the manifest, so the record of a campaign is complete, failures included.

## Variables

| Variable           | Default       | Meaning                                                                   |
| ------------------ | ------------- | ------------------------------------------------------------------------- |
| `RUNS`             | `20`          | Runs per configuration                                                    |
| `FIRST_SEED`       | `1000`        | Seed of run 1; fixed for the whole campaign                               |
| `MAX_HOURS`        | (none)        | Length of the session, in hours                                           |
| `MAX_ATTEMPTS`     | `3`           | Failed attempts in a row before a run is put aside until the next session |
| `HEADLESS`         | `0`           | `1`: Gazebo without its window                                            |
| `ALLOW_NEW_COMMIT` | `0`           | `1`: continue a campaign on a commit other than the one it started on     |
| `SIM_LOG_DIR`      | `/tmp/gs_sim` | Where `coastal_up.sh` writes the logs of the scenario                     |

## Output

Everything is under `bags/campaigns/<campaign>/`:

```text
bags/campaigns/full/
├── campaign.env                      first seed and commit of the campaign
├── manifest.csv                      one line per attempt
├── nominal/
│   ├── run-01-seed1000/
│   │   ├── bag/                      the rosbag2 bag
│   │   └── logs/                     logs of the run and of the scenario
│   ├── run-02-seed1010/
│   └── run-02-seed1010-try2/         a later attempt of the same run
└── deny/
    └── ...
```

The `logs/` folder holds the output of the three steps (`coastal_up.log`,
`record_run.log`, `coastal_down.log`), the logs of the run (`gs_*.log`, see
[Logs](../scripts/pipeline.md#logs)) and those of the scenario (`gazebo.log`,
`px4_<instance>.log`, `px4_configure.log`, `dds_agent_<port>.log`,
`coastal_pipeline.log`).

### Manifest

| Column          | Content                                                                           |
| --------------- | --------------------------------------------------------------------------------- |
| `campaign`      | Name of the campaign                                                              |
| `configuration` | Name of the configuration                                                         |
| `run`           | Run number, from 1 to `RUNS`                                                      |
| `attempt`       | Attempt of that run, from 1                                                       |
| `seed`          | Seed of the run                                                                   |
| `commit`        | Commit of the code (12 characters)                                                |
| `host`          | Machine that ran it                                                               |
| `started_utc`   | Start of the attempt, UTC                                                         |
| `duration_s`    | Duration of the attempt, scenario start and stop included                         |
| `exit_code`     | Exit code of `record_run.sh`, or of `coastal_up.sh` if the scenario did not start |
| `outcome`       | See [Outcomes](#outcomes)                                                         |
| `valid`         | `yes` if the run can be analysed                                                  |
| `folder`        | Folder of the attempt                                                             |

### Outcomes

| Outcome       | Exit code            | Valid | Meaning                                                                                        |
| ------------- | -------------------- | ----- | ---------------------------------------------------------------------------------------------- |
| `completed`   | 0                    | yes   | The run ended normally                                                                         |
| `no-threat`   | 1                    | yes   | No ConfirmedThreat within `THREAT_TIMEOUT`: a result, which counts against the completion rate |
| `refused`     | 2                    | no    | A pre-run check refused the run (see [Guards](../scripts/pipeline.md#guards))                  |
| `guard-stop`  | 3                    | no    | A guard stopped the run: **its bag must not be analysed**                                      |
| `interrupted` | 130                  | no    | Stopped with Ctrl-C; redone in the next session                                                |
| `sim-failed`  | from `coastal_up.sh` | no    | The scenario did not start or was not ready in time                                            |
| `error`       | any other            | no    | The run ended in an unexpected way; see `record_run.log`                                       |

The [analysis](analysis.md) takes, for each configuration and run, the first
attempt with `valid=yes` whose recording is clean.

## Exit codes

| Code  | Meaning                                                                                                                                                               |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`   | The session ended: the campaign is complete, or `MAX_HOURS` has passed                                                                                                |
| `1`   | The campaign cannot start (see the message), or the session needs a look: runs were put aside, two of them in a row stopped the session, or the scenario did not stop |
| `130` | Stopped with Ctrl-C                                                                                                                                                   |

## Starting and stopping the scenario

`coastal_up.sh` and `coastal_down.sh` also work on their own, for example to
start the scenario without the terminals of `make demo-coastal`:

```bash
./scripts/sim/coastal_up.sh                 # Gazebo with its window
HEADLESS=1 ./scripts/sim/coastal_up.sh      # Gazebo without its window
N_UAVS=8 READY_TIMEOUT_S=600 ./scripts/sim/coastal_up.sh   # eight UAVs and the UGV
VETO_BY=gate UAV_FAULT=obstacle ./scripts/sim/coastal_up.sh
./scripts/sim/coastal_down.sh
```

`VETO_BY` (`worker` or `gate`, default `worker`) and `UAV_FAULT` (`none` or
`obstacle`, default `none`) set the launch arguments `veto_by` and `uav_fault`
of `coastal_pipeline.launch.py`: which node enforces the Safety Board veto on
the UAVs, and the fault mode of the UAV workers (see
[`guarded_swarms_control`](../packages/guarded_swarms_control.md)).
`coastal_up.sh` refuses any other value.

`N_UAVS` is the number of UAVs, from 2 (the default, the fleet of
`make demo-coastal`) to 8 (see [The fleet](#the-fleet)). `UAV_FAULT=obstacle`
needs `N_UAVS=2`: the faulty flights are defined for the first two UAVs.

`coastal_up.sh` starts every component detached from the terminal, each with
its own log in `SIM_LOG_DIR`, and PX4 in daemon mode, each instance with its
uXRCE-DDS client on its own agent from the start (`PX4_UXRCE_DDS_PORT`). It
refuses to start if a scenario is already running. The scenario is **ready**
when:

- `/clock` is published;
- every UAV hovers within 1 m of its patrol altitude (12 m or 20 m, see
  [The fleet](#the-fleet));
- every PX4 instance is armed and not in failsafe, as
  `scripts/world/check_coastal.sh` checks them;
- every vehicle publishes a proximity reading (`/drone/proximity`,
  `/px4_1/drone/proximity`, `/px4_2/drone/proximity` and so on): without it
  there is no lidar, and the Safety Boards would veto every command.

A PX4 instance that reports its battery unhealthy (`Battery unhealthy` in
`px4_<instance>.log`) stops the start-up at once: from then on the Safety
Board of that vehicle receives no battery status and vetoes all its commands,
so the vehicle could not fly the run. A campaign then starts the scenario
again.

It exits with 0 once the scenario is ready, with 1 if a component did not
start, `px4_configure.sh` failed or took more than `CONFIGURE_TIMEOUT_S`
(60 s), a PX4 instance reports its battery unhealthy, or the scenario was not
ready within `READY_TIMEOUT_S` (120 s of real time by default; the message
lists what is missing), and with 130 on Ctrl-C. Whatever it started keeps
running until `coastal_down.sh`.

`coastal_down.sh` stops what is left of a run (`stop_pipeline_processes`),
the ROS 2 side of the scenario with SIGINT, then PX4, the DDS agents, Gazebo
and any node still alive with SIGKILL, and finally the ROS 2 daemon. It
exits with 0 if nothing is left, and with 1, listing the survivors,
otherwise. It matches the processes precisely (PX4 and the DDS agents by
name, the rest by command line), so an editor open on a node's source file
is left alone; `scripts/kill_all.sh` would kill it.

### The fleet

The vehicles of the scenario are listed in
`src/guarded_swarms_bringup/config/coastal_fleet.yaml`: for each, its PX4
instance, its spawn pose in the world frame and, for a UAV, its hover
altitude. `coastal_up.sh` starts the UGV and the first `N_UAVS` UAVs of the
file, `coastal_pipeline.launch.py` brings up their nodes, and
`tbcspn.launch.py` gives the same UAVs to the dispatch transition (T7), which
sends the nearest one to intercept. All three read `N_UAVS` from the
environment, so the chain must run with the `N_UAVS` of the scenario:
`test_pipeline.sh` refuses to start otherwise (exit 2).

| Vehicle | PX4 instance | System ID | Namespace | Spawn (x, y) | Hover  |
| ------- | ------------ | --------- | --------- | ------------ | ------ |
| UAV0    | 0            | 1         | (root)    | (-24, -24)   | 12 m   |
| UAV1    | 1            | 2         | `/px4_1`  | (24, -24)    | 20 m   |
| UGV     | 2            | 3         | `/px4_2`  | (-60, -14)   | (none) |
| UAV2    | 3            | 4         | `/px4_3`  | (48, -24)    | 12 m   |
| UAV3    | 4            | 5         | `/px4_4`  | (72, -24)    | 20 m   |
| UAV4    | 5            | 6         | `/px4_5`  | (96, -24)    | 12 m   |
| UAV5    | 6            | 7         | `/px4_6`  | (120, -24)   | 20 m   |
| UAV6    | 7            | 8         | `/px4_7`  | (144, -24)   | 12 m   |
| UAV7    | 8            | 9         | `/px4_8`  | (168, -24)   | 20 m   |

The UAVs stand on the launch pads along y = -24, 24 m apart and at least 10 m
from any building, and neighbouring UAVs hover at different altitudes. The DDS
agent of each instance listens on UDP 8888 plus the instance. The UAVs past
the first two are interceptors only: they carry the same nodes as UAV0 and
UAV1 (lidar bridge, safety bridge, Safety Board, worker and safety gate) but
no sensor of the chain, so the sensing is the same for every fleet, and they
have no faulty flight.

`make demo-coastal` starts the first two UAVs and the UGV with the poses of
`make/vars.mk`, which must stay in sync with the file.

## Troubleshooting

| Message                                                     | What to do                                                                                                                                                 |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `the working tree has uncommitted changes`                  | Commit them (or stash them), then start again                                                                                                              |
| `a scenario is already running`                             | Close `make demo-coastal`, or run `./scripts/sim/coastal_down.sh`                                                                                          |
| `campaign '...' is already running in another terminal`     | Only one session per campaign: wait for it, or stop it with Ctrl-C                                                                                         |
| `this campaign started at commit ...`                       | Finish the campaign at that commit, start a new campaign, or set `ALLOW_NEW_COMMIT=1` if the change does not affect the runs                               |
| `put aside after 3 failed attempts each: ...`               | Read the logs of the attempts of those runs: `coastal_up.log` if the scenario did not start, `record_run.log` otherwise. The next session tries them again |
| `STOPPED: two runs in a row failed 3 times each`            | The set-up is failing, not a single run. Read the logs of the last attempt, fix the cause and run the same command                                         |
| `STOPPED: the scenario did not stop cleanly`                | Run `./scripts/sim/coastal_down.sh` until it reports `nothing left`, then run the same command                                                             |
| `not ready within 120s; missing: ...` (in `coastal_up.log`) | The listed items did not come up. Check `px4_<instance>.log` and `coastal_pipeline.log` in the same folder                                                 |
| `PX4 <instance> reports its battery unhealthy`              | That vehicle could not have flown the run. A campaign starts the scenario again by itself; by hand, run `./scripts/sim/coastal_down.sh` and start again    |
| `px4_configure.sh ... took more than 60s`                   | A PX4 instance did not answer its configuration: see `px4_configure.log`. A campaign starts the scenario again by itself                                   |
| `WARNING: only N GB free`                                   | Each run leaves a bag and its logs: free some space before a long session                                                                                  |
