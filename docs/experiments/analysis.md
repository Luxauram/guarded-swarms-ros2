# Analysis

Two scripts turn recorded runs into checked figures. They read the bags,
change none of them, and start no ROS node.

| File                                  | Role                                                                                                         |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `scripts/metrics/analyze_campaign.py` | The tables of a [campaign](campaigns.md), from its manifest and bags, with the clean-run checks on every run |
| `scripts/metrics/audit_recordings.py` | Checks that recorded runs are clean, and recomputes their time figures on both time axes                     |

Both build on `scripts/metrics/audit_timing.py`, which reads the bags, maps
receive times to simulated time through the recorded `/clock`, and computes
the statistics.

## Quick start

```bash
source /opt/ros/humble/setup.bash && source install/setup.bash
python3 scripts/metrics/analyze_campaign.py bags/campaigns/<campaign>
python3 scripts/metrics/audit_recordings.py bags/<run>... --csv results/audit_recordings.csv
```

## Campaign tables

`analyze_campaign.py` reads `manifest.csv`, `campaign.env` and the bags of
one or more campaign folders. It prints the tables and writes them, with the
data behind them, to `--out` (default `results/<first campaign>/`):

| File            | Content                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| `tables.md`     | The tables, as printed                                                  |
| `runs.csv`      | One line per run: identity, checks, counts and times                    |
| `outcomes.csv`  | Binary outcomes per configuration, with the 95% Wilson score interval   |
| `latencies.csv` | Time statistics per configuration: n, mean, sample sd, median, min, max |

All times come from the token stamps, in simulated time. Rates are computed
over the clean runs.

### Which attempt is used

- Attempts with the same configuration and seed are attempts of the same
  run, also across campaign folders.
- For each run the first attempt with `valid=yes` whose recording is
  [clean](#clean-runs) is used. A run with no clean attempt is left out of
  the tables and listed with the reasons.
- A run whose valid attempt is not clean is repeated in a new campaign with
  the same configuration and seed, and the folders are analysed together.
  The attempt set aside is listed under "Runs repeated", and the manifests
  keep every attempt:

```bash
FIRST_SEED=<seed> RUNS=1 ./scripts/experiments/run_campaign.sh <campaign>-repeat <configuration>
python3 scripts/metrics/analyze_campaign.py bags/campaigns/<campaign> bags/campaigns/<campaign>-repeat
```

### Tables

| Table                 | Content                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Outcomes              | Per configuration, the rate of its expected outcome and of CandidateTarget, EO confirmation, ConfirmedThreat and mission |
| Times                 | First observation → CandidateTarget → ConfirmedThreat → supervisor decision → mission → first task, mean ± sample sd     |
| Authorisation         | Runs with a supervisor decision, missions after an authorise decision, and the times of the decision path                |
| Detection by modality | Runs in which each modality observed the target, and its first observation after the first observation of any modality   |
| Runs                  | Valid, clean and left-out runs, real-time factor, intruder speed in simulated time                                       |

The lists that follow name the runs left out, the runs repeated, the runs
without a valid attempt, and the notes on single runs.

The expected outcome of each configuration of
`scripts/experiments/configurations.conf`:

| Configuration                             | Expected outcome                                        |
| ----------------------------------------- | ------------------------------------------------------- |
| `nominal`, `vec-frontal`, `loss-acoustic` | ConfirmedThreat and mission                             |
| `deny`                                    | ConfirmedThreat, no mission                             |
| `stale-eo`                                | CandidateTarget and EO confirmation, no ConfirmedThreat |
| `civilian`                                | Civilian RF interpretation, no CandidateTarget          |
| `vec-east-deep`, `vec-rear`               | CandidateTarget, no ConfirmedThreat                     |
| `loss-radar`, `loss-rf`                   | No CandidateTarget                                      |
| `loss-eo`                                 | CandidateTarget, no EO confirmation, no ConfirmedThreat |

## Clean runs

A pipeline run is clean when nothing outside the run took part in it and its
clocks agree. `audit_recordings.py` checks:

| Check                                                                                                           | A failure means                       |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| The intruder ground truth has no two consecutive samples more than 5 m apart, and at most 30 samples per second | More than one intruder                |
| `/clock` never goes back                                                                                        | More than one simulator, or a restart |
| The counter at the end of the observation ids never goes back                                                   | More than one agent of a modality     |
| One target is observed                                                                                          | Another target in the scenario        |
| A `deny` run has no `authorise` decision                                                                        | Another supervisor                    |
| Every token is stamped in simulated time                                                                        | A producer on the wall clock          |

`analyze_campaign.py` adds the checks that every run of the current code
must pass:

| Check                                                                                                    | A failure means                          |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| The bag holds `/clock`, the intruder ground truth and observation tokens                                 | The simulated time did not reach the run |
| The counter at the end of the interpretation ids never goes back                                         | More than one producer per transition    |
| The ground-truth stamps are in simulated time, and the intruder speed in simulated time is 6.0 ± 0.1 m/s | Mixed clocks                             |
| At most one supervisor decision for the target                                                           | More than one supervisor                 |

## Auditing recordings

`audit_recordings.py` takes any bags, for example the recordings made before
the campaigns. A bag is named by its folder
(`<configuration>-YYYYMMDD-HHMMSS`) or, in a campaign, by its configuration
and run folders.

For each pipeline run it prints the [clean-run checks](#clean-runs), the
outcome against the expected one, and the time figures on two axes:

- `sim`: the token stamps, in simulated time;
- `rx`: the recorder receive time, on the wall clock.

It also gives the intruder speed in simulated time (ground truth against
`/clock`) and on the ground-truth stamps. An intruder that advances on the
wall clock moves, in simulated time, at its commanded speed divided by the
real-time factor.

For each Safety Board run (bags of `scripts/record/record_veto.sh`) it
checks that no simulator and no digital-layer node was publishing, when
those topics are in the recording, that the sensor stamps are on one clock,
and that each hazard is one block of out-of-bounds samples. It measures the
reaction time message by message: from the first out-of-bounds sensor sample
to the first unsafe `/safety_status`, and to the first zero
`/actuator_cmd_safe` while the raw command is non-zero. A hazard that starts
while the board is already unsafe has no reaction time.

`--csv FILE` writes one line per pipeline run to `FILE`, and one line per
Safety Board run next to it, with a `_veto` suffix.
