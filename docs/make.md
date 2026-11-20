# Make targets

The `Makefile` at the root includes the modules in `make/`, and each target
sources ROS 2 and the workspace itself where it needs them, so they run from
any shell at the root of the repository. `make`, alone, prints the list of the
targets; `make show-guide` prints a short guide to the common workflows.

| Module                | Targets                                     |
| --------------------- | ------------------------------------------- |
| `make/vars.mk`        | None: the variables below                   |
| `make/ros2.mk`        | The ROS 2 workspace                         |
| `make/px4.mk`         | PX4 and Gazebo, and the coastal scenario    |
| `make/demo.mk`        | The Safety Board alone, and its tests       |
| `make/diagnostics.mk` | The setup, the diagnostics and the clean-up |

## Setup

`install.sh` installs every dependency, then builds PX4 and the workspace as
these targets do (see [Getting started](getting-started.md#installation)). The
targets serve a machine that already has ROS 2, Gazebo and the uXRCE-DDS agent,
or redo one part of the installation.

| Target            | Does                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------- |
| `setup-all`       | `setup-workspace`, then `setup-px4`                                                                           |
| `setup-workspace` | Fetches the submodules, removes `build/`, `install/` and `log/`, and builds every package                     |
| `setup-px4`       | Clones PX4 at the pinned commit, if `PX4_DIR` does not exist, installs its dependencies, and builds PX4 SITL  |
| `setup-ugv`       | Checks that the rover model of the repository carries its lidar; copies nothing                               |
| `gen-coastal`     | Regenerates the coastal world (see [`guarded_swarms_gz`](packages/guarded_swarms_gz.md#generating-the-world)) |

`setup-workspace` installs no dependencies: `install.sh` installs them with
rosdep. `setup-px4` stops if PX4 is already in `PX4_DIR` at another commit, and
prints the commands that bring it to the pinned one. With PX4 already at the
pinned commit it only builds it, without running the dependency script of
PX4 again.

## The coastal scenario

| Target          | Does                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------- |
| `demo-coastal`  | Starts the coastal scenario with two UAVs and the UGV, and the nodes of the vehicles                |
| `check-coastal` | Checks a running coastal scenario (see [Simulation scripts](scripts/simulation.md#check_coastalsh)) |

`demo-coastal` needs a display and `xterm`, in which it opens Gazebo, the
agents and the PX4 instances:

1. It checks that PX4 is in `PX4_DIR` and that the rover model carries its
   lidar, runs `gz_kill.sh`, and clears the state of PX4 instances 1 and 2.
2. It starts Gazebo with the coastal world, with its window, through
   `gz_launch.sh`, and waits `GZ_BOOT_WAIT`.
3. It starts three uXRCE-DDS agents, on UDP ports 8888, 8889 and 8890.
4. It starts UAV0, PX4 instance 0, with `make px4_sitl gz_x500_lidar_front` in
   the PX4 tree, which first builds PX4 if needed; waits `UAV_BOOT_WAIT`; and
   configures it with `px4_configure.sh`.
5. It starts UAV1, instance 1, and the UGV, instance 2, from the built PX4,
   waiting 12 s for each before it configures it.
6. It restarts the ROS 2 daemon, and runs `coastal_pipeline.launch.py` in the
   terminal of make (see
   [`guarded_swarms_bringup`](packages/guarded_swarms_bringup.md#coastal_pipelinelaunchpy)).

Each PX4 instance attaches to the running Gazebo (`PX4_GZ_STANDALONE=1`), at
its pose of `make/vars.mk`, without moving the camera of the Gazebo window to
follow it (`PX4_GZ_NO_FOLLOW=1`). Its output goes to its window and to
`/tmp/px4_<instance>.log`.

Ctrl-C stops the launch file only: the windows of Gazebo, of the agents and of
PX4 stay open, and `make kill-all` or `make px4-kill` stops them. The scenario
then runs with the scripts of the pipeline, such as
`scripts/pipeline/test_pipeline.sh` (see
[Pipeline run scripts](scripts/pipeline.md)). For more than two UAVs, or a
scenario without windows, `scripts/sim/coastal_up.sh` starts it instead (see
[Campaigns](experiments/campaigns.md#starting-and-stopping-the-scenario)).

## ROS 2 workspace

| Target            | Does                                                         |
| ----------------- | ------------------------------------------------------------ |
| `ros2-build-ws`   | Builds every package, with `--symlink-install`               |
| `ros2-clean-ws`   | Removes `build/`, `install/` and `log/`                      |
| `ros2-rebuild-ws` | `ros2-clean-ws`, then `ros2-build-ws`                        |
| `ros2-graph`      | Opens `rqt_graph`, the graph of the running nodes and topics |

## PX4 and Gazebo

| Target          | Does                                                                                                  |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| `px4-kill`      | Runs `gz_kill.sh`, then stops the uXRCE-DDS agents and deletes the mission storage of PX4 (`dataman`) |
| `gazebo-test`   | Starts Gazebo with its empty world, to check that Gazebo runs                                         |
| `gazebo-worlds` | Lists the worlds of PX4 and those of the repository                                                   |

`gz_kill.sh` is described in
[Simulation scripts](scripts/simulation.md#gz_killsh).

## The Safety Board alone

Without PX4 or Gazebo:

| Target                 | Does                                                                                                |
| ---------------------- | --------------------------------------------------------------------------------------------------- |
| `demo-safety`          | Prints the steps of the demo and its scenarios                                                      |
| `demo-safety-board`    | Runs `safety_board_node` in the root namespace, with its default parameters                         |
| `demo-safety-sensors`  | Runs `mock_sensor_publisher`                                                                        |
| `test-resilience-mock` | Runs the resilience tests against the mock pipeline (see [Resilience tests](scripts/resilience.md)) |

The demo is described with the publisher, in
[`guarded_swarms_safety`](packages/guarded_swarms_safety.md#mock_sensor_publisher).

## Diagnostics and clean-up

| Target      | Does                                                                                                                                                                    |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `diagnose`  | Checks ROS 2, the workspace, PX4 and its pinned commit, the rover model, Gazebo, the uXRCE-DDS agent and the GPU, and lists the running PX4, Gazebo and agent processes |
| `check-gpu` | Shows the NVIDIA GPU, if `nvidia-smi` finds one, or the GPUs of the machine                                                                                             |
| `kill-all`  | Runs `scripts/kill_all.sh`, which stops the whole stack (see [Simulation scripts](scripts/simulation.md#kill_allsh))                                                    |

## Variables

Defined in `make/vars.mk`. Any of them can be set for one call, as
`make demo-coastal GZ_BOOT_WAIT=15`; `PX4_DIR` also from the environment, as
for the scripts.

| Variable                   | Default                           | Meaning                                                      |
| -------------------------- | --------------------------------- | ------------------------------------------------------------ |
| `PX4_DIR`                  | `~/PX4-Autopilot`                 | The PX4 tree                                                 |
| `PX4_COMMIT`, `PX4_BRANCH` | `091ac918…`, `guarded-swarms-pin` | The pinned commit of PX4, and the local branch that holds it |
| `COASTAL_WORLD`            | `coastal`                         | The world of `demo-coastal`                                  |
| `UAV0_POSE`, `UAV1_POSE`   | `-24,-24,0`, `24,-24,0`           | The spawn points of the UAVs, Gazebo ENU, m                  |
| `COASTAL_UGV_POSE`         | `-60,-14,0`                       | The spawn point of the UGV, Gazebo ENU, m                    |
| `GZ_BOOT_WAIT`             | `8`                               | The wait for Gazebo, s                                       |
| `UAV_BOOT_WAIT`            | `15`                              | The wait for UAV0 before it is configured, s                 |

The three poses must match `coastal_fleet.yaml` (see
[`guarded_swarms_bringup`](packages/guarded_swarms_bringup.md#coastal_fleetyaml)),
which the nodes of the vehicles read.
