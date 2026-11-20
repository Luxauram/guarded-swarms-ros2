# Getting started

This page takes a fresh Ubuntu 22.04 machine to a run of the coastal pipeline.

## Requirements

| Component | Requirement                                                                   |
| --------- | ----------------------------------------------------------------------------- |
| OS        | Ubuntu 22.04 LTS. Windows and macOS are not supported, and Docker is not used |
| ROS 2     | Humble Hawksbill                                                              |
| Gazebo    | Harmonic                                                                      |
| PX4       | Autopilot SITL at the pinned commit (see [The PX4 version](#the-px4-version)) |
| GPU       | NVIDIA recommended: Gazebo renders the lidar sensors on the GPU               |
| RAM       | 8 GB minimum, 16 GB recommended; larger fleets need more                      |
| Disk      | 20 GB free, plus the recordings                                               |

Everything is installed on the host, so Gazebo has direct access to the GPU.

## The PX4 version

`px4_msgs` and the PX4 firmware must come from the same commit. With mismatched
message definitions the uXRCE-DDS bridge silently stops publishing some topics:
the vehicles arm but never move. The firmware is therefore pinned:

```
PX4 commit 091ac918b133d518da8b73e395243ea0e0d087b5   (v1.17.0-alpha1-397-g091ac918b1)
```

`install.sh` checks out this commit on a local branch, `guarded-swarms-pin`. Do
not move PX4 to another commit without regenerating `px4_msgs` from it. The PX4
source tree is never modified: Gazebo finds the scenario's models and worlds in
this repository through `GZ_SIM_RESOURCE_PATH`, so
`git -C ~/PX4-Autopilot status --short` prints nothing, as `make check-coastal`
verifies.

## Installation

```bash
git clone --recurse-submodules https://github.com/Luxauram/guarded-swarms-ros2.git
cd guarded-swarms-ros2
./install.sh
```

Run it as your user, not as root: it calls `sudo` where it needs to. It takes
20 to 40 minutes, and runs these steps:

1. ROS 2 Humble, with rosbridge, the WebSocket bridge of the supervisor
   console, and the Python libraries of the scripts. On a system without
   ROS 2 it first upgrades the installed packages, as the ROS 2 documentation
   asks for a fresh Ubuntu 22.04.
2. Gazebo Harmonic, and its ROS 2 bridge, `ros-humble-ros-gzharmonic`.
3. Micro XRCE-DDS Agent, the transport between PX4 and ROS 2, at its release
   v2.4.3.
4. PX4 SITL, cloned into `~/PX4-Autopilot` at the pinned commit, with its
   dependencies.
5. The ROS 2 workspace: the submodules, the dependencies of the packages,
   installed with rosdep, and the build of every package.
6. The environment, in `~/.bashrc`.

Each step skips what is already in place, so the script can run again after a
failure, or on a machine that already has part of the stack. It stops on a
release other than Ubuntu 22.04, and on a PX4 tree at another commit, which it
does not touch: it prints the commands that bring the tree to the pinned one.

On a machine that already has ROS 2, Gazebo and the agent, `make setup-px4` and
`make setup-workspace` build PX4 and the workspace alone (see
[Make targets](make.md#setup)). The coastal world is part of the repository:
`make gen-coastal` regenerates it only after a change to its generator.

## The coastal scenario

```bash
make demo-coastal
```

The scenario starts Gazebo with the coastal world, one PX4 instance and one
uXRCE-DDS agent per vehicle, and the vehicle-side nodes: two UAVs that take off
and hover over their launch pads, and a UGV that patrols the shore road. Leave
it running in its own terminal. Ctrl-C stops the nodes of the vehicles, and
leaves Gazebo, the agents and PX4 running in their windows: `make kill-all`
stops everything (see [Make targets](make.md#the-coastal-scenario)).

Gazebo renders the lidar sensors on the GPU. On a machine with both integrated
and NVIDIA graphics, `scripts/sim/gz_launch.sh`, which starts Gazebo for the
scenario, selects the NVIDIA GPU when its driver is loaded; `make check-gpu`
shows the GPU. Without the scans of the lidars the Safety Boards have no
proximity reading, and veto every command.

`make check-coastal` checks a running scenario: the real-time factor, the topics
of each vehicle, that each vehicle is armed and airborne, the Safety Boards, and
that the PX4 tree is unmodified.

For more UAVs, `scripts/sim/coastal_up.sh` starts the same scenario without
terminals, with `N_UAVS` from 2 to 8, and `scripts/sim/coastal_down.sh` stops it
(see [The fleet](experiments/campaigns.md#the-fleet)).

## A run of the pipeline

With the scenario running, in a second terminal:

```bash
./scripts/pipeline/test_pipeline.sh
```

The script launches the intruder, the four sensing agents, the TB-CSPN
transitions and the scripted supervisor; waits for the first ConfirmedThreat;
lets the supervisor decide (authorise, by default); and after a reaction window
reports which vehicles moved. With an authorisation, the nearest UAV flies to
intercept the intruder and the UGV moves to observe it.
`scripts/record/record_run.sh` records the same run into a bag. The variables of
a run (decision and its delay, intruder path and speed, seed, recording) are in
[Pipeline run scripts](scripts/pipeline.md).

The decision can also be taken in the supervisor console, a page opened in a
browser, with `scripts/pipeline/demo_console.sh` in place of the test script.
The console is a demonstration, not used in the recorded runs, and it does not
always work reliably; it is described in [Supervisor console](console.md).

### Running the layers by hand

The same layers can be started one by one, each in its own terminal:

```bash
ros2 launch guarded_swarms_bringup intruder.launch.py
ros2 launch guarded_swarms_sensing sensing.launch.py
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py
DECISION=authorise ros2 launch guarded_swarms_supervisor supervisor.launch.py
```

Instead of the scripted supervisor, the decision can be published by hand (see
[`guarded_swarms_tbcspn`](packages/guarded_swarms_tbcspn.md#mission_transition_node)).
The supervisor and its decisions are described in
[`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md).

### Watching the chain

```bash
ros2 topic echo /obs_tokens --field source     # what each sensing agent observes
ros2 topic echo /interp_tokens --field label   # the interpretations, up to ConfirmedThreat
ros2 topic echo /supervisor_auth               # the supervisor's decision
ros2 topic echo /mission_tokens                # a released mission and its justification
ros2 topic echo /vehicle_tasks                 # the tasks dispatched to the vehicles
```

## The Safety Board on its own

The Safety Board runs without PX4 and Gazebo, against mock sensors that step
through six scenarios: nominal (pass), proximity 0.8 m (veto), attitude 45°
(veto), battery 10% (veto), altitude 60 m (veto), and nominal again (pass).

```bash
make demo-safety-board      # terminal 1: the board
make demo-safety-sensors    # terminal 2: the scripted readings
# terminal 3: a proposed command, ten times a second
ros2 topic pub -r 10 /actuator_cmd_raw std_msgs/msg/Float32 "{data: 0.6}"
# terminal 4: 0.6 while the board is safe, 0.0 while it vetoes
ros2 topic echo /actuator_cmd_safe
```

The mock publisher proposes no command, so the third terminal proposes one.
`make test-resilience-mock` runs the tests of the board (see
[Resilience tests](scripts/resilience.md)).

## Useful commands

| Command                | Effect                            |
| ---------------------- | --------------------------------- |
| `make help`            | Every `make` target               |
| `make show-guide`      | Usage guide and workflows         |
| `make diagnose`        | System diagnostic                 |
| `make check-gpu`       | GPU support                       |
| `make ros2-rebuild-ws` | Clean and rebuild the workspace   |
| `make kill-all`        | Stop every process of the project |

Every target is described in [Make targets](make.md).
