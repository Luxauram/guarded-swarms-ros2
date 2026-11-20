# Guarded Swarms ROS 2

[![Release](https://img.shields.io/github/v/release/Luxauram/guarded-swarms-ros2)](https://github.com/Luxauram/guarded-swarms-ros2/releases)
[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org/en/humble/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-orange.svg)](https://gazebosim.org/)
[![PX4](https://img.shields.io/badge/PX4-SITL%2C_pinned-green.svg)](docs/getting-started.md#the-px4-version)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu_22.04-E95420.svg)](https://ubuntu.com/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

A ROS 2 digital twin of the Guarded Swarms architecture for heterogeneous
UAV/UGV swarms. Four sensing agents turn a moving intruder into semantic tokens;
a TB-CSPN coordination layer fuses them into a confirmed threat, waits for a
supervisor's authorisation and dispatches the mission to the vehicles; on every
vehicle an independent Safety Board can veto the commands, whatever the
coordination layer decides. Every vehicle runs the full PX4 flight stack in
software-in-the-loop, in Gazebo Harmonic.

## Features

- **Sensing agents.** Radar, RF, acoustic and electro-optical, each with its own
  coverage and error model, seeded for repeatable runs.
- **TB-CSPN coordination chain.** Observations are interpreted and joined in
  time windows into a CandidateTarget and a ConfirmedThreat, and every token
  keeps the chain of tokens it was derived from.
- **Human authorisation.** No mission is released without a supervisor's
  decision, taken by a scripted supervisor in automated runs, by hand, or in a
  browser-based console.
- **A Safety Board on every vehicle.** An OR-logic veto on proximity, attitude,
  battery, altitude and stale sensor data, independent of the coordination
  layer. On the UAVs a safety gate between the worker and PX4 can enforce it
  even against a faulty worker.
- **Scalable coastal scenario.** From 2 to 8 UAVs and a UGV, all with PX4, in a
  generated coastal world.
- **Reproducible experiments.** Unattended, seeded campaigns with clean-run
  checks, fault injection (forged missions, faulty workers, forged observations,
  clock denial), and one command that rebuilds every table and figure from the
  recordings.

## Requirements

Ubuntu 22.04 LTS with ROS 2 Humble, Gazebo Harmonic and PX4 SITL at a pinned
commit, installed natively (no Docker). An NVIDIA GPU is recommended: Gazebo
renders the lidar sensors on the GPU. See
[Getting started](docs/getting-started.md#requirements).

## Installation

```bash
git clone --recurse-submodules https://github.com/Luxauram/guarded-swarms-ros2.git
cd guarded-swarms-ros2
./install.sh
```

`install.sh` installs ROS 2 with rosbridge, Gazebo Harmonic, the uXRCE-DDS
agent and PX4 at the pinned commit, then the dependencies of the packages with
rosdep, and builds the workspace, in 20 to 40 minutes. Run it as your user: it
calls `sudo` where it needs to. See
[Getting started](docs/getting-started.md#installation).

## Quick start

```bash
# Terminal 1: the coastal world, with 2 UAVs and a UGV
make demo-coastal

# Terminal 2: intruder, sensing, TB-CSPN and the supervisor's decision, then a report
./scripts/pipeline/test_pipeline.sh
```

Once the threat is confirmed and authorised, the nearest UAV leaves its hover
point to intercept the intruder and the UGV moves to observe it; the script
reports which vehicles moved. See
[Getting started](docs/getting-started.md#a-run-of-the-pipeline).

## Reproducing the experiments

```bash
RUNS=20 ./scripts/experiments/run_campaign.sh <campaign> <configuration>...
./scripts/metrics/make_results.sh
```

The first command records a campaign of runs, the second rebuilds every table
and figure in `results/` from the recordings. See
[Campaigns](docs/experiments/campaigns.md),
[Analysis](docs/experiments/analysis.md) and the
[clock-denial bench](docs/experiments/clock.md).

## Documentation

| Page                                       | Content                                                                          |
| ------------------------------------------ | -------------------------------------------------------------------------------- |
| [Getting started](docs/getting-started.md) | Requirements, installation, the coastal scenario, a run of the pipeline          |
| [Architecture](docs/architecture.md)       | The layers, the tokens and the transitions, the Safety Board and the safety gate |
| [Documentation index](docs/README.md)      | Every page: interfaces, make, packages, scripts, experiments, development        |
| [Changelog](CHANGELOG.md)                  | The changes of every version                                                     |

## Repository layout

```
src/        ROS 2 packages
console/    supervisor console: browser decision panel and its bridge node
scripts/    scenario, run, recording, campaign and analysis scripts
make/       Makefile fragments (make help lists the targets)
docs/       documentation
install.sh  installation on Ubuntu 22.04
```

| Package                     | Content                                                    |
| --------------------------- | ---------------------------------------------------------- |
| `guarded_swarms_msgs`       | Token, authorisation and task messages                     |
| `guarded_swarms_sensing`    | The four sensing agents                                    |
| `guarded_swarms_tbcspn`     | The transitions of the coordination chain                  |
| `guarded_swarms_supervisor` | The scripted supervisor                                    |
| `guarded_swarms_control`    | Vehicle workers, safety gate, PX4 bridges and the intruder |
| `guarded_swarms_safety`     | The Safety Board and its mock sensors                      |
| `guarded_swarms_bringup`    | Launch files and the fleet description                     |
| `guarded_swarms_gz`         | Worlds and models                                          |

## Publications

The architecture implemented here is described in:

- U. M. Borghoff, P. Bottoni, R. Pareschi. _Beyond Prompt Chaining: The TB-CSPN
  Architecture for Agentic AI._ Future Internet 17(8):363, 2025.
  [doi:10.3390/fi17080363](https://doi.org/10.3390/fi17080363)
- U. M. Borghoff, P. Bottoni, R. Pareschi. _Guarded Swarms: Hybrid
  Digital–Analog Coordination for AI–Robot Systems._ IEEE International Workshop
  on Technologies for Defense and Security (TechDefense), Rome, 2025.
- U. M. Borghoff, P. Bottoni, R. Pareschi. _Guarded Swarms: Building Trusted
  Autonomy Through Digital Intelligence and Physical Safeguards._ Future
  Internet 18(1):64, 2026.
  [doi:10.3390/fi18010064](https://doi.org/10.3390/fi18010064)
- U. M. Borghoff, P. Bottoni, R. Pareschi. _Sensor-Driven Mission Synthesis for
  UAV/UGV Swarms: A TB-CSPN Coordination Architecture with Hardware-Enforced
  Safety._ Preprint, 2026. [arXiv:2608.14306](https://arxiv.org/abs/2608.14306)

## Citing

If you use this software, please cite it as given in
[`CITATION.cff`](CITATION.cff), also available from the "Cite this repository"
button of this page.

## License

[Apache License 2.0](LICENSE).

## Acknowledgments

The first version (v0.1.0) was developed for the author's B.Sc. thesis at the
University of Molise, supervised by Prof. Remo Pareschi. The architecture comes
from the Guarded Swarms line of work of U. M. Borghoff, P. Bottoni and R.
Pareschi. Built on [PX4 Autopilot](https://px4.io/),
[ROS 2](https://docs.ros.org/en/humble/) and [Gazebo](https://gazebosim.org/).
