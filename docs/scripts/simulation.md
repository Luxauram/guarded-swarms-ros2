# Simulation scripts

The scripts that start Gazebo, configure the PX4 instances, check a running
scenario and stop the simulation. The make targets and the scripts that run a
scenario call them; they can also be run by hand.

| Script                           | Purpose                                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `scripts/sim/gz_launch.sh`       | Starts Gazebo with a world, with the models of the repository ahead of those of PX4                    |
| `scripts/sim/px4_configure.sh`   | Sets the parameters of a running PX4 instance, and moves its uXRCE-DDS client to the port of its agent |
| `scripts/sim/gz_kill.sh`         | Stops Gazebo and PX4, and clears the files they leave behind                                           |
| `scripts/world/check_coastal.sh` | Checks a running coastal scenario, item by item                                                        |
| `scripts/kill_all.sh`            | Stops the whole stack: PX4, Gazebo, the uXRCE-DDS agents and every node                                |

`scripts/sim/coastal_up.sh` and `scripts/sim/coastal_down.sh`, which start and
stop the scenario without terminals, are described in
[Campaigns](../experiments/campaigns.md#starting-and-stopping-the-scenario),
and `scripts/world/gen_coastal.py`, which generates the world, in
[`guarded_swarms_gz`](../packages/guarded_swarms_gz.md#generating-the-world).

The scripts that use PX4 find it in `PX4_DIR`, `~/PX4-Autopilot` by default,
built with `make px4_sitl_default`.

## gz_launch.sh

Starts Gazebo with a world of the repository, or of PX4.

```bash
bash scripts/sim/gz_launch.sh coastal              # with the Gazebo window
bash scripts/sim/gz_launch.sh coastal --headless   # the server alone
```

The argument is the name of the world, without `.sdf`. The script:

1. **Checks PX4.** It needs `build/px4_sitl_default/rootfs/gz_env.sh` in the
   PX4 tree, which the build of PX4 generates; without it, it exits with 1 and
   says how to build PX4.
2. **Sets the paths.** It puts `src/guarded_swarms_gz/models` and
   `src/guarded_swarms_gz/worlds` on `GZ_SIM_RESOURCE_PATH`, then sources
   `gz_env.sh`, which appends the models and worlds of PX4 and sets
   `GZ_SIM_SYSTEM_PLUGIN_PATH` and `GZ_SIM_SERVER_CONFIG_PATH`. Without these
   two, Gazebo loads none of the sensor systems of PX4, and every preflight
   check of PX4 fails. Since the paths of the repository come first, a model or
   a world with the same name is taken from the repository: its `r1_rover`
   replaces that of PX4, and nothing is copied into the PX4 tree.
3. **Selects the GPU.** When the NVIDIA driver is loaded, it sets
   `__NV_PRIME_RENDER_OFFLOAD=1` and `__GLX_VENDOR_LIBRARY_NAME=nvidia`, so
   that on a machine with two GPUs Gazebo renders, the lidar included, on the
   NVIDIA one. It always sets `MESA_GL_VERSION_OVERRIDE=4.5`, for the Mesa
   drivers that would otherwise give the renderer of Gazebo an older OpenGL
   context.
4. **Starts Gazebo** with `gz sim -r`, so the simulation runs from the start.
   `--headless` adds `-s`: the server alone, without the window. The sensors
   are rendered all the same.

The script replaces itself with Gazebo, so stopping it stops Gazebo. The make
targets start Gazebo through it, and so do `coastal_up.sh` and
`scripts/bench/bench_vehicles.sh`.

## px4_configure.sh

Configures one running PX4 instance, through the shell clients of PX4
(`px4-param`, `px4-uxrce_dds_client`) in `build/px4_sitl_default/bin`.

```bash
bash scripts/sim/px4_configure.sh 0 uav   # instance 0, a UAV
bash scripts/sim/px4_configure.sh 2 ugv   # instance 2, the rover
```

The clients select the instance with `--instance`: without it, every client
talks to instance 0, so in a fleet the wrong vehicle would be configured.

### Parameters

The script sets the parameters, then saves them:

| Parameters                                                       | Values             | Vehicle  | Purpose                                                                                                                                                                                 |
| ---------------------------------------------------------------- | ------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `COM_RC_IN_MODE`, `NAV_RCL_ACT`, `NAV_DLL_ACT`, `COM_RCL_EXCEPT` | `1`, `0`, `0`, `4` | UAV      | Turn off the failsafes that expect an RC transmitter and a ground station: the UAV flies offboard from ROS 2, with neither, and PX4 would refuse to arm with "no connection to the GCS" |
| `COM_ARM_WO_GPS`                                                 | `1`                | UAV      | Allow arming without GPS                                                                                                                                                                |
| `COM_LOW_BAT_ACT`                                                | `0`                | UAV, UGV | Turn off the low-battery failsafe: the simulated battery drains over time, and in a long session the failsafe would act during the run                                                  |

The other defaults of PX4 are right for the rover. `SYS_HAS_MAG` must stay as
it is: without a magnetometer the estimator of the rover never converges, its
local position stays invalid, and the failsafe disarms it.

`gz_kill.sh` deletes the saved parameters, so every start of the simulation
needs the script again: `make demo-coastal` and `coastal_up.sh` run it for
every instance.

### The uXRCE-DDS port

Each instance has its own uXRCE-DDS agent, on UDP port `8888 + instance`. A
single agent for every instance saturates and blocks the clients: since PX4
SITL runs in lockstep with Gazebo, a blocked client stalls the whole
simulation, and the real-time factor falls from 1.0 to about 0.0005.

The client of an instance starts on port 8888, the port of instance 0. For any
other instance the script:

- leaves the client running, if `PX4_UXRCE_DDS_PORT` in its environment is
  already the port of the instance: `coastal_up.sh` starts each instance with
  it, so its client starts on its own port;
- otherwise, sets `UXRCE_DDS_PRT` to the port of the instance, saves it, and
  restarts the client with the namespace `px4_<instance>`. The client reads its
  port only at start-up, hence the restart. `make demo-coastal` relies on
  this.

It stops at the first client that fails, and exits with 1 for a vehicle type
other than `uav` or `ugv`.

## gz_kill.sh

Stops the simulation and clears what it leaves behind, for a clean start:

```bash
./scripts/sim/gz_kill.sh
```

1. It kills PX4, Gazebo and the Gazebo bridge of PX4, with SIGKILL.
2. It waits 3 s, so that they release their files.
3. It deletes the temporary files of Gazebo (`/tmp/.gazebo*`), the shared
   memory in `/dev/shm` (`sem.*` and `fastrtps_*`), and the saved parameters of
   every PX4 instance (`parameters*.bson` in `build/px4_sitl_default`).

A Gazebo server left running, or the parameters of an earlier session, are a
common cause of a simulation that starts but never arms. `coastal_up.sh` and
`make demo-coastal` run the script before they start Gazebo, and
`make px4-kill` runs it, then stops the uXRCE-DDS agents.

It stops neither the uXRCE-DDS agents nor the ROS 2 nodes: `kill_all.sh` does.
The shared memory it deletes is that of every Fast DDS process on the machine,
not only of the simulation, so other ROS 2 sessions should be stopped first.
A kill that finds no process is normal, so the script does not stop at the
first error.

## check_coastal.sh

Checks a running coastal scenario, item by item, and prints `PASS`, `FAIL` or
`WARN` for each:

```bash
bash scripts/world/check_coastal.sh   # or: make check-coastal
```

It reads the state from Gazebo (`gz topic`, `gz model -p`), from the shell
clients of PX4 and from ROS 2, never from the Gazebo window: under load the
window can show a stale frame, with vehicles that are moving drawn still at
their spawn points.

| Section              | Check                                                                                     | Fails when                                                                     |
| -------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Simulation           | The real-time factor, from `/world/coastal/stats`                                         | No statistics arrive, or the factor is not above 0.3                           |
| uXRCE-DDS namespaces | The ROS 2 topics under `/fmu`, `/px4_1/fmu` and `/px4_2/fmu`                              | A vehicle has fewer than 60: each PX4 instance gives about 65                  |
| Vehicles             | The status of each PX4 instance, and the pose of its Gazebo model                         | A vehicle is not armed, is in failsafe or has no model; a UAV is not above 2 m |
| Safety layer         | One message of `drone/proximity` and of `actuator_cmd_safe` from each vehicle, within 5 s | One of them does not arrive. An active veto is a warning                       |
| PX4 tree             | `git status` of the PX4 tree                                                              | The PX4 tree has local changes                                                 |

The exit code is the number of failed checks, 0 when all pass. It checks the
fleet of `make demo-coastal`: UAV0, UAV1 and the UGV, as PX4 instances 0, 1
and 2. With `N_UAVS` above 2, the other UAVs are not checked. `WORLD` sets the
name of the world, `coastal` by default.

## kill_all.sh

Stops the whole stack, however it was started:

```bash
./scripts/kill_all.sh   # or: make kill-all
```

With SIGKILL, in this order:

1. the builds and runs of PX4 started by make (`make` and `cmake` with
   `px4_sitl` on the command line), so they do not start the simulator again;
2. PX4, Gazebo, the Gazebo bridge of PX4 and the uXRCE-DDS agents;
3. every node of the packages, `mock_sensor_publisher` included, matched on the
   path of its executable, `install/<package>/lib/<package>/<node>`, and the
   console bridge, matched on `python3` and the name of its script: a process
   that only names a node, such as an editor open on its source file, is left
   running;
4. every `parameter_bridge` of `ros_gz_bridge`, matched on the path of its
   executable.

Then it deletes the temporary files of Gazebo and the shared memory, as
`gz_kill.sh` does, but not the saved parameters of PX4. It leaves rosbridge
and any recording running.

Unlike `coastal_down.sh`, which stops the scenario of `coastal_up.sh` and checks
that nothing survived, `kill_all.sh` kills by name and checks nothing; it also
kills a build of PX4 in progress. It is a script rather than a recipe of the
Makefile because a `pkill make` inside a recipe would kill the make that runs
it.
