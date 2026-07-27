# Guarded Swarms ROS 2

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org/en/humble/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-orange.svg)](https://gazebosim.org/)
[![PX4](https://img.shields.io/badge/PX4-SITL-green.svg)](https://px4.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%2022.04-E95420.svg)](https://ubuntu.com/)

A ROS 2 digital twin of the **Guarded Swarms** architecture: sensor-driven
mission synthesis for a heterogeneous UAV/UGV swarm, with human-authorised
action release and hardware-style safety enforcement at the actuator boundary.
Built on PX4 SITL and Gazebo Harmonic. Master's thesis, University of Molise,
supervised by Prof. Remo Pareschi.

**Target paper:** Borghoff, Bottoni, Pareschi (2026), _"Sensor-Driven Mission
Synthesis for UAV/UGV Swarms"_, IET Radar, Sonar & Navigation. That paper is
architectural and leaves quantitative benchmarking and hardware-in-the-loop
validation to future work; **this project builds the working digital twin and
fills that gap.**

---

> **Platform Notice**
>
> **Runs natively on Ubuntu 22.04 LTS. Docker is not used.** ROS 2 Humble, PX4
> and Gazebo Harmonic are installed on the host for full GPU access (Gazebo
> rendering and lidar sensors). Windows and macOS are not supported. An NVIDIA
> GPU is recommended (needed for the lidar sensors).

---

## What the system does

The coastal case study runs a full sensing-to-action pipeline against a moving
intruder:

```
 sensors (radar, RF, acoustic, EO)  ->  semantic tokens
     │
     ▼  TB-CSPN coordination layer (Figure 4 of the paper)
 T1..T5  observations are interpreted and fused into a ConfirmedThreat
 T6      a human supervisor authorises (or denies) the interception
 T7      the mission is dispatched into per-vehicle tasks
 T8/T9   worker agents fly the interception / drive the observation
     │
     ▼
 a UAV leaves hover and tracks the intruder; the UGV moves to a shore
 observation point — all from one human authorisation, with a full,
 auditable justification chain from raw observation to action.
```

Two properties are the point of the architecture, and both are enforced
structurally rather than by configuration:

- **Human-in-the-loop.** No interception mission is ever formed without an
  explicit supervisor authorisation. Withhold it, and the threat persists but
  nothing is dispatched.
- **Decoupled analogue safety.** Every vehicle carries an independent safety
  board that vetoes its own actuator on a proximity/attitude/battery/altitude
  violation, with no knowledge of the coordination layer.

---

## Architecture layers

- **Sensing layer** (`guarded_swarms_sensing`) — four consultant agents (radar,
  RF, acoustic, electro-optical) synthesise temporally-bounded semantic tokens
  from the scene. Each has its own coverage and error model; the EO coverage
  moves with its carrier UAV. The coverage geometry is a simulation model
  (declared as such) and produces a realistic sea-vs-inland detection
  asymmetry.
- **Coordination layer** (`guarded_swarms_tbcspn`) — the TB-CSPN transitions of
  Figure 4. Two generic nodes (interpretation, time-windowed join) plus mission
  release and dispatch cover T1–T7. Tokens carry an unbroken provenance chain.
- **Worker agents** (`guarded_swarms_control`) — the digital-physical bridge.
  Each worker is the single controller of its vehicle: the UAV worker flies a
  stand-off interception and track-locks the target's threat estimate; the UGV
  worker drives to a shore observation point. Executors run deterministic
  platform control only.
- **Safety layer** (`guarded_swarms_safety`) — a per-vehicle virtual safety
  board applying an OR-logic veto on the actuator command, decoupled from the
  coordination layer.
- **Adversary** (`guarded_swarms_control/intruder_node`) — a scripted,
  open-loop, replayable intruder, with a radio-silence flag for a counterfactual.

---

## Quick start — the coastal pipeline

The full case study is four launches plus one authorisation. **The scenario
needs its own terminal (Gazebo GUI); a helper script runs everything else.**

```bash
# Terminal 1 — the world: 2 UAV + 1 UGV on the coastal map
make demo-coastal

# Terminal 2 — intruder + sensing + TB-CSPN, waits for a threat, then
#              authorises automatically and reports which vehicle moved
./scripts/test_pipeline.sh
```

To drive it by hand instead of the script, run the three layers and authorise
yourself:

```bash
# after `make demo-coastal` in terminal 1:
ros2 launch guarded_swarms_bringup intruder.launch.py start_delay_s:=20.0
ros2 launch guarded_swarms_sensing sensing.launch.py
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py

# when a ConfirmedThreat is scrolling, authorise:
ros2 topic pub --once /auth_tokens guarded_swarms_msgs/msg/SupervisorAuth \
  "{target_id: 'intruder', authorised_by: 'supervisor_luca', \
    decision: 'authorise', ttl_s: 10.0}"
```

Health check and world regeneration:

```bash
make check-coastal   # RTF, DDS namespaces, per-vehicle arm/airborne, safety, pristine PX4
make gen-coastal     # regenerate coastal.sdf (fixed seed, byte-identical)
```

Monitor:

```bash
ros2 topic echo /obs_tokens --field source     # what each modality sees
ros2 topic echo /interp_tokens --field label   # the chain climbing to ConfirmedThreat
ros2 topic echo /mission_tokens                # a released mission + justification
ros2 topic echo /vehicle_tasks                 # the dispatched per-vehicle tasks
```

---

## The PX4 version pin (important)

`px4_msgs` and the PX4 firmware **must** come from the same commit, or the
uXRCE-DDS bridge silently stops publishing some topics — the vehicle arms but
never moves. The firmware is pinned:

```
PX4 commit  091ac918b133d518da8b73e395243ea0e0d087b5   (branch guarded-swarms-pin)
```

Never bump PX4 without regenerating `px4_msgs`. The PX4 tree is treated as
read-only (`git -C ~/PX4-Autopilot status --short` must print nothing);
everything is layered via environment variables.

---

## Prerequisites

| Component  | Requirement                                 |
| ---------- | ------------------------------------------- |
| **OS**     | **Ubuntu 22.04 LTS (required)**             |
| **ROS 2**  | Humble Hawksbill                            |
| **Gazebo** | Harmonic (gz-harmonic)                      |
| **PX4**    | Autopilot SITL, pinned commit (see above)   |
| RAM        | 8 GB minimum, 16 GB recommended             |
| Storage    | 20 GB free                                  |
| GPU        | NVIDIA GPU recommended (required for lidar) |

---

## Installation

```bash
git clone --recurse-submodules git@github.com:YOUR_USERNAME/guarded-swarms-ros2.git
cd guarded-swarms-ros2
chmod +x install.sh && ./install.sh
```

Estimated 20–40 minutes. `install.sh` installs ROS 2 Humble, Gazebo Harmonic,
the Micro-XRCE-DDS agent, PX4 dependencies, checks out and builds the pinned PX4
commit, and builds the workspace. A fresh clone plus `./install.sh` should
produce a working demo with no manual steps.

After install, install the scenario assets into PX4 once:

```bash
make setup-ugv       # rover airframe + model
make setup-worlds    # world assets
make gen-coastal     # generate the coastal world
```

<details>
<summary>Manual installation (step by step)</summary>

The manual sequence (ROS 2, Gazebo, Micro-XRCE-DDS, PX4 deps, workspace build)
is unchanged from the standard PX4 + ROS 2 Humble setup; see `install.sh` for
the authoritative, current steps. The one project-specific requirement is the
PX4 commit pin above and building `guarded_swarms_msgs` + `px4_msgs` first, then
the rest of the workspace.

</details>

---

## Package layout

```
src/
├── guarded_swarms_msgs/        # message definitions
│   └── msg/  ObsToken, InterpToken, MissionToken, SupervisorAuth, VehicleTask,
│             + AuthToken, Token, GeometryToken (the older coordinator's tokens)
├── guarded_swarms_sensing/     # the four consultant agents + sensing.launch.py
├── guarded_swarms_tbcspn/      # TB-CSPN transitions T1-T7 + tbcspn.launch.py
├── guarded_swarms_control/     # worker agents (uav/ugv), offboard, rover,
│                               # intruder, command/safety bridges
├── guarded_swarms_safety/      # analogue safety board + mock sensors
├── guarded_swarms_coordinator/ # older Python token-coordination layer
├── guarded_swarms_bringup/     # launch files (coastal_pipeline, intruder, ...)
├── guarded_swarms_gz/          # worlds (coastal, urban) + models (incl. intruder)
├── web_dashboard/              # browser UI (to be reframed as the supervisor console)
├── px4_msgs/                   # PX4 messages (submodule, pinned)
└── px4_ros_com/                # PX4-ROS 2 bridge (submodule)
```

---

## Other demos (no PX4 / earlier scenarios, still working)

These predate the coastal case study and remain useful for isolated testing.

```bash
# Analogue safety board with mock sensors (6 fault scenarios, no PX4/Gazebo)
make demo-safety-board      # terminal 1
make demo-safety-sensors    # terminal 2
ros2 topic echo /actuator_cmd_safe    # 0.6 = pass, 0.0 = vetoed

# Full software pipeline with mock sensors (no PX4)
ros2 launch guarded_swarms_bringup mock_pipeline.launch.py

# Older single-vehicle urban scenarios (R1 UAV, R2 UGV)
make demo-px4-uav-urban
make demo-px4-ugv-urban
```

Safety board mock scenarios: NOMINAL (pass), PROXIMITY 0.8 m (veto), ATTITUDE
45° (veto), BATTERY 10% (veto), ALTITUDE 60 m (veto), NOMINAL recovery (pass).

---

## Development roadmap

**Done**

- Environment, PX4 pin, native Ubuntu 22.04 stack
- Digital coordination layer + analogue safety layer, decoupled
- Coastal scenario: 2 UAV + 1 UGV, one command (`make demo-coastal`)
- Scripted replayable intruder (radio-silence counterfactual)
- Token types (multi-target) and the four consultant sensing agents
- TB-CSPN detection chain T1–T5, verified in flight
- T6 human authorisation (withheld-authorisation counterfactual comes free)
- T7 dispatch into per-vehicle tasks
- T8 UAV worker: flies the interception, track-locks the threat estimate
- T9 UGV worker: drives to a shore observation point
- One-command end-to-end test (`scripts/test_pipeline.sh`)

**Next**

- [ ] Supervisor console: a web decision-support interface (rosbridge + a
      decision panel showing the threat and its justification, then a
      situational picture). Replaces the manual authorisation.
- [ ] Wire the analogue veto into the UAV worker (the rover already honours it)
- [ ] The two remaining §5.3 counterfactuals (stale EO, conflicting labels)
- [ ] Multi-intruder waves (sea + inland) from a YAML config
- [ ] Metrics (sim time): detection→mission latency, per-transition latency,
      detection latency by attack vector, the counterfactuals as pass/fail tests
- [ ] Demonstration video, thesis PDF

---

## Development commands

```bash
make help                  # full command reference
make show-guide            # usage guide and workflows
make diagnose              # system diagnostic
make check-coastal         # coastal scenario health check
make ros2-rebuild-ws       # clean + rebuild the workspace
make kill-all              # terminate all processes
```

---

## Citation

```bibtex
@article{borghoff2026sensor,
  author  = {Borghoff, Uwe M. and Bottoni, Paolo and Pareschi, Remo},
  title   = {Sensor-Driven Mission Synthesis for {UAV}/{UGV} Swarms},
  journal = {IET Radar, Sonar \& Navigation},
  year    = {2026}
}
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Acknowledgments

Developed under the supervision of Prof. R. Pareschi, University of Molise.
Built on [PX4 Autopilot](https://px4.io/), [ROS 2 Humble](https://docs.ros.org/en/humble/)
and [Gazebo Harmonic](https://gazebosim.org/). Architecture from the Guarded
Swarms line of work by Borghoff, Bottoni and Pareschi.
