# Guarded Swarms documentation

The repository README gives the overview of the project and the quick start.
The pages in this folder document each part of the project in detail.

## Packages

| Package                                                              | Description                                                                                              |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [`guarded_swarms_control`](packages/guarded_swarms_control.md)       | Vehicle-side nodes and the simulated intruder, including the safety gate between the UAV workers and PX4 |
| [`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md) | Scripted supervisor that issues the authorisation decisions of T6 in automated runs                      |

## Scripts

| Page                                        | Description                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| [Pipeline run scripts](scripts/pipeline.md) | One end-to-end run, its recording, and the checks that keep its data clean |

## Experiments

| Page                                  | Description                                                                             |
| ------------------------------------- | --------------------------------------------------------------------------------------- |
| [Campaigns](experiments/campaigns.md) | Unattended campaigns of recorded runs, and the scripts that start and stop the scenario |
| [Analysis](experiments/analysis.md)   | Clean-run checks of recorded runs, and the tables of a campaign                         |

The remaining sections (getting started, architecture, the other packages,
the other scripts, supervisor console, conventions) are added as the
documentation is completed.
