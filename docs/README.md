# Guarded Swarms documentation

The repository README gives the overview of the project and the quick start.
The pages in this folder document each part of the project in detail.

## Overview

| Page                                  | Description                                                                                        |
| ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| [Getting started](getting-started.md) | Requirements, the pinned PX4 version, installation, the coastal scenario and a run of the pipeline |
| [Architecture](architecture.md)       | The layers, the tokens and the transitions, the supervisor, the Safety Board and the safety gate   |

## Packages

| Package                                                              | Description                                                                                              |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [`guarded_swarms_msgs`](packages/guarded_swarms_msgs.md)             | Messages of the coordination layer, from the observations to the tasks of the vehicles, field by field   |
| [`guarded_swarms_sensing`](packages/guarded_swarms_sensing.md)       | The four sensing agents, radar, RF, acoustic and EO, with their coverage, error and rate models          |
| [`guarded_swarms_tbcspn`](packages/guarded_swarms_tbcspn.md)         | The TB-CSPN transitions T1 to T7, from the interpretations to the release and dispatch of a mission      |
| [`guarded_swarms_safety`](packages/guarded_swarms_safety.md)         | The Safety Board of each vehicle, its checks and limits, and a scripted sensor publisher for a demo      |
| [`guarded_swarms_control`](packages/guarded_swarms_control.md)       | Vehicle-side nodes and the simulated intruder, including the safety gate between the UAV workers and PX4 |
| [`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md) | Scripted supervisor that issues the authorisation decisions of T6 in automated runs                      |

## Scripts

| Page                                        | Description                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| [Pipeline run scripts](scripts/pipeline.md) | One end-to-end run, its recording, and the checks that keep its data clean |

## Experiments

| Page                                       | Description                                                                                           |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| [Campaigns](experiments/campaigns.md)      | Unattended campaigns of recorded runs, and the scripts that start and stop the scenario               |
| [Analysis](experiments/analysis.md)        | Clean-run checks, the tables of the campaigns, the figures, and the script that rebuilds every result |
| [Clock-denial bench](experiments/clock.md) | The Safety Board in isolation under clock denial, and the tables of the bench                         |

The remaining sections (the other packages, the other scripts, the supervisor
console, conventions) are added as the documentation is completed.
