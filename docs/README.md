# Guarded Swarms documentation

The repository README gives the overview of the project and the quick start.
The pages in this folder document each part of the project in detail.

## Overview

| Page                                  | Description                                                                                        |
| ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| [Getting started](getting-started.md) | Requirements, the pinned PX4 version, installation, the coastal scenario and a run of the pipeline |
| [Architecture](architecture.md)       | The layers, the tokens and the transitions, the supervisor, the Safety Board and the safety gate   |
| [Interfaces](interfaces.md)           | Every topic of a run: its type, its publishers and subscribers, its namespace and its QoS          |
| [Supervisor console](console.md)      | The panel where the supervisor decides, the console bridge, rosbridge and the demo of the console  |
| [Development](development.md)         | The layout, the conventions of the code, the style, the CI, and how a change becomes a release     |

## Packages

| Package                                                              | Description                                                                                            |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| [`guarded_swarms_msgs`](packages/guarded_swarms_msgs.md)             | Messages of the coordination layer, from the observations to the tasks of the vehicles, field by field |
| [`guarded_swarms_sensing`](packages/guarded_swarms_sensing.md)       | The four sensing agents, radar, RF, acoustic and EO, with their coverage, error and rate models        |
| [`guarded_swarms_tbcspn`](packages/guarded_swarms_tbcspn.md)         | The TB-CSPN transitions T1 to T7, from the interpretations to the release and dispatch of a mission    |
| [`guarded_swarms_safety`](packages/guarded_swarms_safety.md)         | The Safety Board of each vehicle, its checks and limits, and a scripted sensor publisher for a demo    |
| [`guarded_swarms_control`](packages/guarded_swarms_control.md)       | The workers of the vehicles, the sensor bridge, the safety gate of the UAVs, and the scripted intruder |
| [`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md) | Scripted supervisor that issues the authorisation decisions of T6 in automated runs                    |
| [`guarded_swarms_bringup`](packages/guarded_swarms_bringup.md)       | The fleet of the coastal scenario, and the launch files of the vehicles and of the intruder            |
| [`guarded_swarms_gz`](packages/guarded_swarms_gz.md)                 | The coastal world and how it is generated, the rover with its lidar, and the intruder model            |

## Scripts

| Page                                        | Description                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| [Simulation scripts](scripts/simulation.md) | Starting, configuring, checking and stopping Gazebo and PX4                |
| [Pipeline run scripts](scripts/pipeline.md) | One end-to-end run, its recording, and the checks that keep its data clean |
| [Resilience tests](scripts/resilience.md)   | The tests of the Safety Board alone, their configuration and reports       |

## Experiments

| Page                                       | Description                                                                                           |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| [Campaigns](experiments/campaigns.md)      | Unattended campaigns of recorded runs, and the scripts that start and stop the scenario               |
| [Analysis](experiments/analysis.md)        | Clean-run checks, the tables of the campaigns, the figures, and the script that rebuilds every result |
| [Clock-denial bench](experiments/clock.md) | The Safety Board in isolation under clock denial, and the tables of the bench                         |
| [Veto recording](experiments/veto.md)      | The Safety Board in isolation under the scripted scenarios of the mock publisher, recorded to a bag   |
| [Scaling bench](experiments/scaling.md)    | The real-time factor of the simulation against the number of PX4 instances                            |

The remaining sections (the other packages, the other scripts, the supervisor
console, conventions) are added as the documentation is completed.
