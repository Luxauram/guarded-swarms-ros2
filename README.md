# Guarded Swarms ROS 2

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org/en/humble/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-orange.svg)](https://gazebosim.org/)
[![PX4](https://img.shields.io/badge/PX4-SITL-green.svg)](https://px4.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%2022.04-E95420.svg)](https://ubuntu.com/)

ROS 2 simulation framework implementing the Guarded Swarms hybrid digital-analog coordination architecture for autonomous multi-robot systems (UAV + UGV). Developed as a thesis project at the University of Molise, in collaboration with ongoing swarm robotics research.

Based on: _Borghoff, Bottoni, Pareschi (2025/2026) - "Guarded Swarms: Hybrid Digital-Analog Coordination for AI-Robot Systems"_

---

> **Platform Notice**
>
> **This project runs natively on Ubuntu 22.04 LTS. DOCKER IS NOT USED.**
>
> ROS 2 Humble, PX4, and Gazebo Harmonic are installed directly on the host system.
> This ensures full GPU access for Gazebo rendering and lidar sensors without
> the overhead and limitations of containerized environments.
>
> - **Windows and macOS are not supported.**
> - An NVIDIA GPU is recommended for Gazebo lidar sensor rendering.
> - GPU flags are embedded in all `px4-gui-*` Makefile targets automatically.

---

## Overview

The Guarded Swarms architecture coordinates autonomous agents through two complementary layers:

- **Digital coordination layer** - a token-based arbitration system inspired by TB-CSPN, where agents request access to shared zones by issuing signed geometry and authorization tokens. A coordinator node resolves concurrent requests within a configurable 300 ms time window.
- **Analog safety enforcement layer** - a virtual safety board that monitors real-time sensor data (proximity, attitude, battery, altitude) and applies OR-logic veto on actuator commands that violate any safety threshold, independently of the digital layer.

The two layers are deliberately decoupled: the safety board has no knowledge of tokens, and the coordinator has no knowledge of sensor readings. This mirrors the architectural separation described in the paper.

---

## Architecture

```
guarded-swarms-ros2/
├── install.sh                      # Automated installation script (Ubuntu 22.04)
├── Makefile                        # Root Makefile
├── scripts/
│   └── kill_all.sh                 # Process cleanup script (called by make kill-all)
├── make/
│   ├── vars.mk                     # Shared variables (paths, ROS 2 source, etc.)
│   ├── ros2.mk                     # ROS 2 workspace management
│   ├── px4.mk                      # PX4 SITL + Gazebo management
│   ├── demo.mk                     # Demo launch targets
│   ├── web.mk                      # Web dashboard
│   └── diagnostics.mk              # Setup + diagnostics
├── src/
│   ├── guarded_swarms_msgs/        # ROS 2 message definitions (ament_cmake)
│   │   └── msg/
│   │       ├── Token.msg
│   │       ├── GeometryToken.msg
│   │       └── AuthToken.msg
│   │
│   ├── guarded_swarms_coordinator/ # Digital coordination layer (ament_python)
│   │   ├── setup.py
│   │   ├── setup.cfg
│   │   └── guarded_swarms_coordinator/
│   │       ├── token_system.py     # Core token logic and arbitration
│   │       ├── agent_node.py       # Monitoring agent (publishes tokens)
│   │       └── coordinator_node.py # Arbitration coordinator
│   │
│   ├── guarded_swarms_safety/      # Analog safety enforcement layer (ament_cmake, C++)
│   │   ├── src/
│   │   │   ├── safety_board_node.cpp       # OR-logic veto on actuator commands
│   │   │   ├── px4_safety_bridge_node.cpp  # PX4 uORB → safety board adapter
│   │   │   └── mock_sensor_publisher.cpp   # 6 fault scenarios (no PX4)
│   │   ├── models/                         # Gazebo UGV model with lidar
│   │   └── px4_airframes/                  # Custom PX4 airframe for UGV
│   │
│   ├── guarded_swarms_control/     # Offboard UAV control + command bridge (ament_cmake, C++)
│   │   └── src/
│   │       ├── offboard_control_node.cpp   # UAV hover control
│   │       ├── command_bridge_node.cpp     # AuthToken → actuator command
│   │       └── px4_safety_bridge_node.cpp  # PX4 sensor bridge (lidar topic configurable)
│   │
│   ├── guarded_swarms_bringup/     # Launch files package (ament_cmake)
│   │   └── launch/
│   │       ├── mock_pipeline.launch.py         # Full pipeline, no PX4
│   │       ├── uav_pipeline.launch.py          # UAV pipeline (default world)
│   │       ├── uav_urban_pipeline.launch.py    # UAV urban pipeline (R1 scenario)
│   │       ├── ugv_pipeline.launch.py          # UGV pipeline (default world)
│   │       └── ugv_urban_pipeline.launch.py    # UGV urban pipeline (R2 scenario)
│   │
│   ├── guarded_swarms_gz/          # Gazebo simulation assets
│   │   ├── worlds/
│   │   │   ├── urban_uav.sdf       # UAV urban scenario (R1): buildings + obstacle pillar
│   │   │   └── urban_ugv.sdf       # UGV urban scenario (R2): street corridor + vehicle
│   │   └── models/                 # Custom Gazebo models
│   │
│   ├── tools/
│   │   ├── launch/
│   │   │   └── demo.launch.py      # Coordinator-only launch
│   │   └── visualization/
│   │       └── dashboard.py        # Lightweight terminal dashboard
│   │
│   ├── web_dashboard/              # Real-time browser-based monitoring UI
│   │   ├── backend/                # FastAPI server + ROS 2 WebSocket bridge
│   │   └── frontend/               # TypeScript + Tailwind + Chart.js
│   │
│   ├── px4_msgs/                   # PX4 message definitions (submodule)
│   └── px4_ros_com/                # PX4-ROS 2 communication bridge (submodule)
│
└── README.md
```

---

## Prerequisites

| Component  | Requirement                                 |
| ---------- | ------------------------------------------- |
| **OS**     | **Ubuntu 22.04 LTS (required)**             |
| **ROS 2**  | Humble Hawksbill                            |
| **Gazebo** | Harmonic (gz-harmonic)                      |
| **PX4**    | Autopilot SITL (cloned to ~/PX4-Autopilot)  |
| RAM        | 8 GB minimum, 16 GB recommended             |
| Storage    | 20 GB free                                  |
| GPU        | NVIDIA GPU recommended (required for lidar) |

---

## Installation

The easiest way is to use the automated script:

```bash
git clone --recurse-submodules git@github.com:YOUR_USERNAME/guarded-swarms-ros2.git
cd guarded-swarms-ros2
chmod +x install.sh && ./install.sh
```

Estimated time: 20-40 minutes depending on internet speed.

### Manual installation (step by step)

#### 1. ROS 2 Humble

```bash
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu jammy main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update && sudo apt install -y \
  ros-humble-desktop \
  ros-humble-ros-gzharmonic-bridge \
  python3-colcon-common-extensions \
  python3-rosdep
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

#### 2. Gazebo Harmonic

```bash
sudo curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
  | sudo tee /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
  http://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main" \
  | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt update && sudo apt install -y gz-harmonic
```

#### 3. Micro-XRCE-DDS Agent (PX4 bridge)

```bash
sudo apt install -y git cmake build-essential
cd /tmp && git clone --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git
cd Micro-XRCE-DDS-Agent && mkdir build && cd build
cmake .. && make -j$(nproc) && sudo make install && sudo ldconfig /usr/local/lib/
```

#### 4. PX4 dependencies and build

```bash
sudo apt install -y bc libeigen3-dev libopencv-dev pkg-config protobuf-compiler \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav libgstreamer-plugins-base1.0-dev \
  xterm expect
cd ~ && git clone https://github.com/PX4/PX4-Autopilot.git --recursive --depth 1
cd ~/PX4-Autopilot && bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools
make px4_sitl_default  # initial build (~10-20 minutes)
```

#### 5. Python dependencies

```bash
pip3 install \
  fastapi==0.104.1 "uvicorn[standard]==0.24.0" \
  websockets==12.0 pydantic==2.5.0 python-multipart==0.0.6
curl -fsSL https://bun.sh/install | bash && source ~/.bashrc
```

#### 6. Build the ROS 2 workspace

```bash
cd ~/guarded-swarms-ros2
git submodule update --init --recursive
source /opt/ros/humble/setup.bash
colcon build --packages-select guarded_swarms_msgs px4_msgs --symlink-install
source install/setup.bash
colcon build --packages-select \
  guarded_swarms_coordinator \
  guarded_swarms_safety \
  guarded_swarms_control \
  guarded_swarms_bringup \
  --symlink-install
echo "source ~/guarded-swarms-ros2/install/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

#### 7. Install Guarded Swarms assets (run once)

```bash
make setup-ugv      # install rover airframe and model into PX4
make setup-worlds   # install urban world files into PX4
```

---

## Quick Start

```bash
# Token coordination demo (no PX4, no Gazebo)
make demo-coordinator   # Terminal 1
make demo-web           # Terminal 2 -> http://localhost:8765

# Safety board demo with mock sensors (no PX4, no Gazebo)
make demo-safety-board    # Terminal 1
make demo-safety-sensors  # Terminal 2

# Full pipeline with mock sensors (all layers, no PX4)
ros2 launch guarded_swarms_bringup mock_pipeline.launch.py

# Monitor output
ros2 topic echo /actuator_cmd_safe
```

---

## Gazebo Simulation

### UAV Urban Scenario (R1 from paper) - single command

```bash
make demo-px4-uav-urban
```

Opens Gazebo with the urban world, auto-arms the drone, launches the full
ROS2 pipeline. The analog safety board vetoes actuator commands when the
lidar detects an obstacle within 1.5m.

```bash
ros2 topic echo /actuator_cmd_safe   # 0.0 = vetoed
ros2 topic echo /drone/proximity     # lidar distance
```

### UGV Urban Scenario (R2 from paper) - single command

```bash
make setup-ugv              # run once
make demo-px4-ugv-urban
```

Opens Gazebo with the urban street world, launches the full ROS2 pipeline.
Move the abandoned vehicle obstacle near the rover in Gazebo to trigger veto.

### Manual launch (advanced)

```bash
# UAV default world
make px4-gui-uav      # Terminal 1
make ros2-agent       # Terminal 2
ros2 launch guarded_swarms_bringup uav_pipeline.launch.py  # Terminal 3

# UGV default world
make px4-gui-ugv      # Terminal 1
make ros2-agent       # Terminal 2
ros2 launch guarded_swarms_bringup ugv_pipeline.launch.py  # Terminal 3
```

---

## Available Demos

### A) Token Coordination (no PX4)

```bash
make demo-coordinator   # Terminal 1
make demo-web           # Terminal 2 -> http://localhost:8765
```

### B) Safety Board with Mock Sensors (no PX4)

| Scenario | Description                             | Result |
| -------- | --------------------------------------- | ------ |
| 0        | NOMINAL - all sensors within bounds     | PASS   |
| 1        | PROXIMITY - obstacle at 0.8 m (< 1.5 m) | VETO   |
| 2        | ATTITUDE - pitch 45 deg (> 30 deg)      | VETO   |
| 3        | BATTERY LOW - 10% (< 15%)               | VETO   |
| 4        | ALTITUDE HIGH - 60 m (> 50 m)           | VETO   |
| 5        | NOMINAL RECOVERY                        | PASS   |

```bash
make demo-safety-board    # Terminal 1
make demo-safety-sensors  # Terminal 2
ros2 topic echo /actuator_cmd_safe   # 0.6 = pass, 0.0 = vetoed
```

### C) Full Pipeline with Mock Sensors

```bash
ros2 launch guarded_swarms_bringup mock_pipeline.launch.py
```

### D) UAV Urban Scenario (R1 from paper)

```bash
make demo-px4-uav-urban
```

### E) UGV Urban Scenario (R2 from paper)

```bash
make setup-ugv
make demo-px4-ugv-urban
```

---

## Monitor Topics

```bash
ros2 topic echo /actuator_cmd_safe   # 0.6 = pass, 0.0 = vetoed
ros2 topic echo /actuator_cmd_raw    # 0.6 when token approved
ros2 topic echo /safety_status       # 1.0 = safe, 0.0 = unsafe
ros2 topic echo /drone/proximity     # lidar distance (m)
ros2 topic echo /drone/altitude      # altitude (m)
```

---

## Development Roadmap

### Phase 0 - Environment Setup

- [x] ROS 2 Humble + Gazebo Harmonic native installation (Ubuntu 22.04)
- [x] PX4 SITL integration via Micro-XRCE-DDS bridge
- [x] Basic UAV offboard control (takeoff, hover, position hold)
- [x] Makefile-based development workflow

### Phase 1 - Digital Coordination Layer

- [x] Separate `guarded_swarms_msgs` package for ROS 2 message definitions
- [x] `agent_node`: publishes geometry and authorization tokens
- [x] `coordinator_node`: arbitrates concurrent requests within 300 ms window
- [x] Token buffering, expiry, and signature validation
- [x] Real-time web dashboard for token stream monitoring
- [x] Multi-agent concurrency validation with live demo

### Phase 2 - Analog Safety Enforcement Layer

- [x] `safety_board_node` (C++) with configurable sensor thresholds
- [x] OR-logic veto on actuator commands upon any threshold violation
- [x] `mock_sensor_publisher` (C++) with 6 pre-defined fault scenarios
- [x] Safety interventions validated: proximity veto, attitude veto
- [x] PX4 safety bridge: IMU, battery, altitude from real Gazebo simulation
- [x] Lidar proximity from Gazebo (end-to-end validated)

### Phase 3 - Integration and Full Pipeline

- [x] Full software pipeline validated with mock sensors
- [x] UAV pipeline with real PX4 sensors and lidar (R1 scenario)
- [x] UGV pipeline with real PX4 sensors and proximity veto (R2 scenario)
- [x] `guarded_swarms_bringup` package with 5 launch files
- [x] Urban world files (R1 + R2 scenarios) in `guarded_swarms_gz`
- [x] Single-command demo launch for both UAV and UGV urban scenarios
- [ ] ROS 2 bag recording and scenario replay

### Phase 4 - Evaluation

- [ ] Resilience testing: dropped tokens, forged tokens, sensor failure
- [ ] Demonstration video

### Phase 5 - Documentation and Submission

- [ ] Complete API documentation
- [ ] Finalize GitHub repository
- [ ] Submit thesis report (PDF)

---

## Development Commands

```bash
make help                  # full command reference
make show-guide            # complete usage guide and workflows
make diagnose              # full system diagnostic
make ros2-rebuild-ws       # clean and rebuild the ROS 2 workspace
make px4-kill              # terminate PX4 and Gazebo processes
make kill-all              # terminate all processes
```

---

## Web Dashboard

A browser-based monitoring panel is included under `src/web_dashboard/`.
It bridges ROS 2 token topics to the browser via WebSocket, providing live
token stream visualization, per-agent statistics, and demo lifecycle control.

Build the frontend once before first use:

```bash
make web-ts-build
```

Access at `http://localhost:8765` after running `make demo-web`.

---

## Citation

```bibtex
@inproceedings{borghoff2025guarded,
  author    = {Borghoff, Uwe M. and Bottoni, Paolo and Pareschi, Remo},
  title     = {Guarded Swarms: Hybrid Digital--Analog Coordination for {AI}--Robot Systems},
  booktitle = {Proceedings of the IEEE International Workshop on Technologies
               for Defense and Security (TechDefense 2025)},
  year      = {2025},
  publisher = {IEEE}
}
```

---

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Developed under the supervision of Prof. R. Pareschi, University of Molise.
- Built on [PX4 Autopilot](https://px4.io/) and [ROS 2 Humble](https://docs.ros.org/en/humble/).
- Gazebo simulation powered by [Gazebo Harmonic](https://gazebosim.org/).
- Coordination architecture based on the Guarded Swarms paper by Borghoff, Bottoni, and Pareschi (2025).
