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
   settings as `make demo-coastal` (Gazebo, three uXRCE-DDS agents, PX4
   instances 0, 1 and 2 configured by `px4_configure.sh`, then
   `coastal_pipeline.launch.py`), with no terminals. It returns once the
   scenario is [ready](#starting-and-stopping-the-scenario).
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
variables that make it differ from the nominal run. It defines eleven
configurations:

| Name            | Variables                                         | What it tests                                        |
| --------------- | ------------------------------------------------- | ---------------------------------------------------- |
| `nominal`       | (none)                                            | The full chain                                       |
| `deny`          | `DECISION=deny`                                   | Authorisation withheld                               |
| `stale-eo`      | `EO_DELAY_S=12`                                   | EO confirmation arriving after the threat TTL (10 s) |
| `civilian`      | `RF_LABEL=LikelyCivilianTraffic EXPECT_THREAT=no` | Conflicting RF evidence                              |
| `vec-frontal`   | `ATTACK_VECTOR=frontal`                           | Frontal ingress                                      |
| `vec-east-deep` | `ATTACK_VECTOR=east-deep`                         | Deep ingress from the east                           |
| `vec-rear`      | `ATTACK_VECTOR=rear`                              | Ingress from the rear                                |
| `loss-radar`    | `RADAR_ENABLED=false`                             | Loss of the radar                                    |
| `loss-rf`       | `RF_ENABLED=false`                                | Loss of the RF sensor                                |
| `loss-acoustic` | `ACOUSTIC_ENABLED=false`                          | Loss of the acoustic sensor                          |
| `loss-eo`       | `EO_ENABLED=false`                                | Loss of the EO camera                                |

`nominal` and `vec-frontal` set the same scenario, since the frontal vector is
the default, but they are separate configurations, each with its own runs.

The variables are those of the [pipeline run scripts](../scripts/pipeline.md#configuration).
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
./scripts/sim/coastal_down.sh
```

`coastal_up.sh` starts every component detached from the terminal, each with
its own log in `SIM_LOG_DIR`, and PX4 in daemon mode. It refuses to start if a
scenario is already running. The scenario is **ready** when:

- `/clock` is published;
- UAV0 and UAV1 hover within 1 m of their patrol altitudes (12 m and 20 m);
- the three PX4 instances are armed and not in failsafe, as
  `scripts/world/check_coastal.sh` checks them;
- the three vehicles publish a proximity reading (`/drone/proximity`,
  `/px4_1/drone/proximity`, `/px4_2/drone/proximity`): without it there is no
  lidar, and the Safety Boards would veto every command.

It exits with 0 once the scenario is ready, with 1 if a component did not
start or the scenario was not ready within `READY_TIMEOUT_S` (120 s; the
message lists what is missing), and with 130 on Ctrl-C. Whatever it started
keeps running until `coastal_down.sh`.

`coastal_down.sh` stops what is left of a run (`stop_pipeline_processes`),
the ROS 2 side of the scenario with SIGINT, then PX4, the DDS agents, Gazebo
and any node still alive with SIGKILL, and finally the ROS 2 daemon. It
exits with 0 if nothing is left, and with 1, listing the survivors,
otherwise. It matches the processes precisely (PX4 and the DDS agents by
name, the rest by command line), so an editor open on a node's source file
is left alone; `scripts/kill_all.sh` would kill it.

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
| `WARNING: only N GB free`                                   | Each run leaves a bag and its logs: free some space before a long session                                                                                  |
