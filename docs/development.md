# Development

How the repository is organised, the conventions the code follows, and how a
change goes from the working tree to a release.

## Layout

| Folder     | Content                                                                                                                                        |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/`     | The ROS 2 packages, one purpose each, and `px4_msgs` as a git submodule                                                                        |
| `scripts/` | The scripts of the project, by area: `sim`, `world`, `pipeline`, `record`, `experiments`, `metrics`, `resilience`, `bench`                     |
| `make/`    | The modules of the Makefile, included by the `Makefile` at the root                                                                            |
| `console/` | The supervisor console and its bridge                                                                                                          |
| `docs/`    | This documentation                                                                                                                             |
| `bags/`    | The recordings; ignored by git                                                                                                                 |
| The root   | `README.md`, `CHANGELOG.md`, `CITATION.cff`, `LICENSE`, `install.sh`, the `Makefile`, and the configurations of the linters and of the editors |

## Building

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install    # every package
colcon build --symlink-install --packages-select guarded_swarms_control
source install/setup.bash
```

With `--symlink-install` the launch and configuration files are installed as
links to the source tree, so an edit to one of them takes effect without a
rebuild; a new file, or a change to C++ code, needs one. The scripts under
`scripts/` run from the source tree and are never built.

## Conventions

### Names

- **Packages** are named `guarded_swarms_<purpose>`, and **nodes** and their
  executables `<function>_node`, in snake case, without abbreviations. The one
  exception is `mock_sensor_publisher`, a test publisher.
- **Topics.** The topics of a vehicle are relative, so that the namespace of
  its nodes selects the vehicle: `drone/imu`, `actuator_cmd_safe`,
  `fmu/in/...`. The topics of the coordination layer and of the intruder are
  absolute: `/obs_tokens`, `/vehicle_tasks`, `/intruder/ground_truth`. A worker
  in the namespace of its vehicle still subscribes to the absolute
  `/vehicle_tasks`, and keeps the tasks of its kind of vehicle and of its
  system. The topics are listed in [Interfaces](interfaces.md).
- **Gazebo topics** embed the world and the instance-suffixed model name, so
  they reach the nodes as parameters, set by the launch files.

### Vehicles

- **One instance, one identity.** PX4 instance `i` has the MAV*SYS_ID `i + 1`,
  the namespace `px4*<i>`(the root for instance 0), and its own uXRCE-DDS agent
on UDP port`8888 + i`. The system ID travels inside `VehicleCommand`, so
every node that commands a vehicle has a `target_system` parameter.
- **One command source per actuator.** Exactly one node publishes the setpoints
  of a vehicle: the worker of the rover, and the safety gate of a UAV, which
  passes on those of its worker. Two publishers on one actuator leave PX4 to
  execute whichever arrives last, and give the veto no single point to act on.
  `ros2 topic info /fmu/in/trajectory_setpoint` shows one publisher.
- **Frames.** The world is ENU: Gazebo x points east, y north. The local frame
  of PX4 is NED, from the spawn point of the vehicle. From the world to a
  vehicle, `north = y − spawn_y` and `east = x − spawn_x`; from a vehicle to
  the world, `x = spawn_x + east`, `y = spawn_y + north` and
  `z = spawn_z − down`. Every node that crosses the boundary takes the spawn
  point of the vehicle as a parameter. A vehicle that flies to the wrong place
  is a north and east swap until proven otherwise.

### Nodes

- **Parameters.** A value that differs between instances (a system ID, a topic,
  a spawn point, an altitude, a coverage, a threshold) is a ROS parameter, not
  a constant in the code. The launch files, and the configuration files under
  `config/`, set the values of the scenario. Integer arrays arrive as `int64`:
  a node declares and reads them as `std::vector<int64_t>`.
- **Time.** Every node of the scenario runs with `use_sim_time`, and every
  latency and validity is measured in simulated time. A time read from a
  message is built in the clock type of the node before it is compared with
  the clock: `rclcpp::Time(msg->t, this->now().get_clock_type())`. Comparing
  times of two clock types throws.
- **Determinism.** The sensing agents draw from a seeded generator, and model a
  latency by dating an observation in the past rather than delaying its
  publication, so a seeded run replays the same draws. The intruder is open
  loop: its motion depends only on the time and its parameters. The coastal
  world is generated with a fixed seed: change the generator, never the SDF.
- **Safety.** A reading the Safety Board cannot interpret is read in the
  conservative direction, never discarded: a lidar return closer than the
  minimum range is a contact. A check that gates motion has hysteresis. The
  veto stops a vehicle; it does not navigate it around the obstacle.
- **Transitions.** A transition validates and interprets, and emits nothing
  when its guards fail: that silence is what the counterfactual runs measure.
  A transition never drops the `origin` or the `justification` of the tokens
  it consumes.

### Scripts

- A script that starts nodes with `ros2 launch` also stops them by name on
  exit: stopping the launch process alone can leave its nodes running, and they
  would join the next run.
- A recording is stopped with SIGINT or SIGTERM, never with SIGKILL, so that
  rosbag2 closes the bag.
- A script that sources a ROS setup file does not use `set -u`, since the setup
  files read variables that may be unset; it uses `set -o pipefail`, or
  `set -e`.
- A script that formats numbers with `awk` or `printf` sets `LC_ALL=C`: in a
  locale with a decimal comma, a number would be printed, or read back, wrong.
- The settings of a scenario that a launch file needs while it builds its nodes
  (the number of UAVs, the label of T2, the delay of the EO camera) are
  environment variables, so that a script exports them once for every launch
  file of the run.

### External code

- **PX4** lives in `~/PX4-Autopilot`, at the pinned commit, and is never
  modified: the models and worlds of the repository reach Gazebo through
  `GZ_SIM_RESOURCE_PATH`. `make check-coastal` fails on a modified PX4 tree.
- **`px4_msgs`** is a submodule, generated from the same commit of PX4. Moving
  PX4 to another commit without regenerating `px4_msgs` leaves uXRCE-DDS
  dropping topics: the vehicles arm, and never move.
- A submodule is never edited.

## Style

| Language | Style                                                                                                                                                              | Checked with            |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| C++      | Google style, with each block of includes kept as written (`.clang-format`); classes in `PascalCase`, members with a trailing `_`, constants in `UPPER_SNAKE_CASE` | `clang-format` 14       |
| Python   | Errors only (`.flake8`): syntax errors, undefined names, unused imports and variables; the style is not checked                                                    | `flake8` 4.0.1          |
| Shell    | Bash, with the checks of shellcheck at the warning level                                                                                                           | `shellcheck` 0.8.0      |
| Markdown | Prettier 3, with tables padded; prose wrapped by hand at 80 columns                                                                                                | Prettier, in the editor |

The versions are those of Ubuntu 22.04, which the CI uses too. Before a
commit, the same checks as the CI:

```bash
git ls-files -z '*.cpp' '*.hpp' | xargs -0r clang-format --dry-run --Werror
git ls-files -z '*.py' | xargs -0r flake8
git ls-files -z '*.sh' | xargs -0r shellcheck -S warning
```

`clang-format -i <file>` formats a C++ file in place.

Across languages:

- Every source file starts with the Apache-2.0 license header, then a comment
  that says what the file is for.
- Comments and documentation describe the code as it is now: what changed, and
  when, belongs in the CHANGELOG and in the git history.
- Code, comments and documentation are in English.
- Every text file ends with a newline; `.editorconfig` sets it, with the
  character set and the line endings, for the editors that read it, and the
  CI checks it.

## CI

`.github/workflows/ci.yml` runs on every push and pull request to `main` and
`dev`, and by hand from the Actions tab. A newer push to a branch cancels the
run still in progress on it. Two jobs:

| Job            | Container                   | Steps                                                                                                                  |
| -------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Lint           | `ubuntu:22.04`              | `clang-format`, `flake8` and `shellcheck` on every file git tracks, as above, and the final newline of every text file |
| Build and test | `ros:humble-ros-base-jammy` | `rosdep install`, `colcon build` of every package, and `make test-resilience-mock`                                     |

The build job has no PX4 and no Gazebo, so it builds the packages and runs the
[resilience tests](scripts/resilience.md), but no simulation. rosdep skips
`ros_gz_sim` and `ros_gz_bridge`: it would install them for Gazebo Fortress,
the default of Humble, while the project uses Gazebo Harmonic. If the tests
fail, the job prints the log of the mock pipeline.

## Branches, commits and releases

- **Branches.** Work happens on `dev`. `main` moves only at a release, fast
  forward to `dev`.
- **Commits.** `<type>(<scope>): <description>`, in English, in the imperative,
  on one line. The types are `feat`, `fix`, `docs`, `refactor`, `style`,
  `ci` and `chore`; the scope is the package or the area, as `control`, `sim`,
  `console` or `make`, and is left out for a change across the repository.
- **CHANGELOG.** Every change a user would notice gets an entry under
  `[Unreleased]` in `CHANGELOG.md`, in the section that fits: Added, Changed,
  Removed or Fixed. The format follows Keep a Changelog, and the versions
  follow semantic versioning.

A release:

1. Rename `[Unreleased]` in `CHANGELOG.md` to the version and the date, and
   open a new empty `[Unreleased]` above it.
2. Commit it as `chore(release): <version>`.
3. Tag the commit with an annotated tag, `v<version>`, whose message sums up
   the release in one line.
4. Move `main` to the release, fast forward, and push both branches and the
   tag.

```bash
git commit -m "chore(release): 0.6.0"
git tag -a v0.6.0 -m "<one line about the release>"
git checkout main && git merge --ff-only dev && git checkout dev
git push origin main dev v0.6.0
```
