# Guarded Swarms ROS 2

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org/en/humble/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-orange.svg)](https://gazebosim.org/)
[![PX4](https://img.shields.io/badge/PX4-SITL-green.svg)](https://px4.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%2022.04-E95420.svg)](https://ubuntu.com/)

ROS 2 simulation framework implementing the Guarded Swarms hybrid digital-analog coordination architecture for autonomous multi-robot systems (UAV + UGV). Developed as a thesis project at the University of Molise, in collaboration with ongoing swarm robotics research.

Based on: _Borghoff, Bottoni, Pareschi (2025/2026) - "Guarded Swarms: Hybrid Digital-Analog Coordination for AI-Robot Systems"_

---

> ** Platform Notice**
>
> **This project requires an Ubuntu Linux host (22.04 or 24.04 LTS).**
>
> The Docker container runs **Ubuntu 22.04 + ROS 2 Humble** internally, regardless
> of the host Ubuntu version. This means you can use Ubuntu 24.04 as your host OS
> and everything will work correctly inside the container.
>
> Gazebo Harmonic requires direct OpenGL/GPU access that Docker cannot reliably
> provide on Windows (WSL2) or macOS. Attempting to run the full simulation stack
> on those platforms will result in degraded or non-functional Gazebo rendering,
> missing lidar data, and unreliable sensor pipelines.
>
> - **Windows:** Gazebo renders at unusable framerates even with WSL2 + VcXsrv.
>   GPU passthrough via NVIDIA Container Toolkit on WSL2 is fragile and untested.
> - **macOS:** Apple dropped NVIDIA GPU support in 2019. Gazebo lidar sensors
>   will not publish data. The full simulation pipeline cannot run on macOS.
>
> **Recommended setup:** Ubuntu 22.04 or 24.04 LTS (native install or dual boot)
>
> - Docker Engine. This is the only configuration that has been developed and tested.

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
├── docker/                         # Containerized development environment
│   ├── Dockerfile                  # ROS 2 Humble + Gazebo Harmonic + PX4 deps
│   ├── docker-compose.yml          # Standard container (Ubuntu only)
│   └── docker-compose.nvidia.yml   # NVIDIA GPU override (Ubuntu + NVIDIA GPU)
│
├── src/
│   ├── guarded_swarms_coordinator/ # Digital coordination layer (token system)
│   │   ├── msg/                    # Custom ROS 2 message definitions
│   │   │   ├── Token.msg
│   │   │   ├── GeometryToken.msg
│   │   │   └── AuthToken.msg
│   │   └── guarded_swarms_coordinator/
│   │       ├── token_system.py     # Core token logic and arbitration
│   │       ├── agent_node.py       # Monitoring agent (publishes tokens)
│   │       └── coordinator_node.py # Arbitration coordinator
│   │
│   ├── guarded_swarms_safety/      # Analog safety enforcement layer
│   │   ├── safety_board_node.py    # OR-logic veto on actuator commands
│   │   ├── px4_safety_bridge.py    # PX4 uORB → safety board adapter
│   │   └── mock_sensor_publisher.py# Simulated sensor scenarios (no PX4)
│   │
│   ├── guarded_swarms_control/     # Offboard UAV control node (C++)
│   │
│   ├── tools/
│   │   ├── launch/
│   │   │   └── demo.launch.py      # Full system launch file
│   │   └── visualization/
│   │       └── dashboard.py        # Lightweight terminal dashboard
│   │
│   ├── web_dashboard/              # Real-time browser-based monitoring UI
│   │   ├── backend/                # FastAPI server + ROS 2 WebSocket bridge
│   │   └── frontend/               # TypeScript + Tailwind + Chart.js
│   │
│   ├── px4_msgs/                   # PX4 message definitions (submodule)
│   └── px4_ros_com/                # PX4–ROS 2 communication bridge (submodule)
│
├── Makefile                        # Build, test, and deployment automation
└── README.md
```

---

## Prerequisites

### System Requirements

| Component  | Requirement                                         |
| ---------- | --------------------------------------------------- |
| **OS**     | **Ubuntu 22.04 or 24.04 LTS (host, required)**      |
| **Docker** | Docker Engine 20.10+ (**not** Docker Desktop)       |
| RAM        | 8 GB minimum, 16 GB recommended                     |
| Storage    | 15 GB free for Docker images and PX4 build          |
| GPU        | NVIDIA GPU recommended (required for lidar sensors) |

> **The container always runs Ubuntu 22.04 + ROS 2 Humble internally.**
> Your host can be Ubuntu 22.04 or 24.04 - both work identically.
> Windows and macOS are not supported. See the platform notice at the top.

### Installing Docker Engine on Ubuntu

```bash
# Remove any old Docker versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Install Docker Engine (not Docker Desktop)
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group (avoids needing sudo)
sudo usermod -aG docker $USER
newgrp docker
```

### X11 Display (for Gazebo GUI)

```bash
# Allow Docker containers to connect to your X server
xhost +local:docker
```

Add this to your `~/.bashrc` to make it permanent:

```bash
echo "xhost +local:docker > /dev/null 2>&1" >> ~/.bashrc
```

---

## GPU Acceleration

Gazebo lidar sensors require OpenGL hardware rendering to publish scan data.
Without a GPU, the safety board operates but uses a fallback proximity value
(`prox=999.0 m`, meaning no obstacle detected).

| Level          | Command                    | Sensors                     | Notes                           |
| -------------- | -------------------------- | --------------------------- | ------------------------------- |
| 1 - Software   | `make docker-start`        | IMU, battery, altitude      | No GPU required; lidar inactive |
| 2 - NVIDIA GPU | `make docker-start-nvidia` | All sensors including lidar | Requires NVIDIA GPU + toolkit   |
| 3 - Real HW    | physical deployment        | All sensors on real robots  | -                               |

### Enabling NVIDIA GPU (Level 2)

**Requirements:**

- NVIDIA GPU (GeForce, Quadro, or Tesla)
- NVIDIA drivers installed on the Ubuntu host
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Verify
make check-gpu
make docker-start-nvidia
```

---

## Quick Start

```bash
# 0. Clone the repository (with submodules)
git clone --recurse-submodules https://github.com/YOUR_USER/guarded-swarms-ros2.git
cd guarded-swarms-ros2

# 1. Copy and configure environment
cp docker/.env.example docker/.env
# Edit docker/.env if needed (default values work on Ubuntu)

# 2. Start the container
make docker-start          # standard (no GPU)
# or
make docker-start-nvidia   # with NVIDIA GPU

# 3. First-time setup (inside container or via make)
make setup-all

# 4. Run a demo
make demo-pipeline
```

---

## Available Demos

### A) Token Coordination (no PX4, no safety layer)

Demonstrates the digital coordination layer in isolation. Four agents continuously
request spatial zones; the coordinator validates, arbitrates, and issues signed
AuthTokens. Rejected agents are blocked until the zone is free.

```bash
# Terminal 1
make demo-coordinator

# Terminal 2 - browser dashboard
make demo-web           # → http://localhost:8765

# Terminal 2 (alternative) - desktop GUI (requires X server)
make demo-tkinter
```

### B) Safety Board with Mock Sensors (no PX4)

Demonstrates the analog safety enforcement layer in isolation. A mock sensor
publisher cycles through 6 pre-defined fault scenarios every 10 seconds.
The safety board applies OR-logic veto independently of any coordinator state.

| Scenario | Description                             | Result |
| -------- | --------------------------------------- | ------ |
| 0        | NOMINAL - all sensors within bounds     | PASS   |
| 1        | PROXIMITY - obstacle at 0.8 m (< 1.5 m) | VETO   |
| 2        | ATTITUDE - pitch 45° (> 30°)            | VETO   |
| 3        | BATTERY LOW - 10% (< 15%)               | VETO   |
| 4        | ALTITUDE HIGH - 60 m (> 50 m)           | VETO   |
| 5        | NOMINAL RECOVERY - back to safe values  | PASS   |

```bash
# Terminal 1
make demo-safety-board

# Terminal 2
make demo-safety-sensors

# Monitor output
ros2 topic echo /actuator_cmd_safe   # 0.6 = pass, 0.0 = vetoed
ros2 topic echo /safety_status       # 1.0 = safe, 0.0 = unsafe
```

### C) Full Pipeline with Mock Sensors (all layers, no PX4)

All software layers run together with simulated sensors. Agents generate tokens →
coordinator approves → command bridge converts approved tokens to actuator
commands → safety board independently vetoes if any sensor is in violation.

```bash
make demo-coordinator     # Terminal 1 - agent → coordinator → AuthToken
make demo-bridge          # Terminal 2 - AuthToken → /actuator_cmd_raw
make demo-safety-board    # Terminal 3 - /actuator_cmd_raw → /actuator_cmd_safe
make demo-safety-sensors  # Terminal 4 - inject sensor fault scenarios
```

### D) UAV Full Pipeline with Gazebo - R1 from paper (requires GPU)

Sensor data comes from a real PX4 SITL simulation of an x500 quadcopter.
Lidar reads actual distances from the Gazebo world.
This is the R1 (UAV) scenario from the paper.

```bash
make demo-px4-uav   # prints full step-by-step instructions
```

### E) UGV Full Pipeline with Gazebo - R2 from paper (requires GPU)

Same architecture as D) but on a differential rover. Altitude check is disabled
(rover stays on the ground); proximity is active. This is the R2 scenario from
the paper where the rover is blocked by a proximity violation.

```bash
make setup-ugv      # run once to install UGV assets
make demo-px4-ugv   # prints full step-by-step instructions
```

---

## Development Roadmap

### Phase 0 - Environment Setup

- [x] ROS 2 Humble + Gazebo Harmonic in Docker
- [x] PX4 SITL integration via micro-ROS bridge
- [x] Basic UAV offboard control (takeoff, hover, position hold)
- [x] Makefile-based development workflow

### Phase 1 - Digital Coordination Layer

- [x] Custom ROS 2 message types (`Token`, `GeometryToken`, `AuthToken`)
- [x] `agent_node`: publishes geometry and authorization tokens
- [x] `coordinator_node`: arbitrates concurrent requests with configurable time window and signature validation
- [x] Token buffering and expiry logic (300 ms concurrency window)
- [x] Real-time web dashboard for token stream monitoring
- [x] Multi-agent concurrency validation with live demo

### Phase 2 - Analog Safety Enforcement Layer

- [x] `safety_board` node with configurable sensor thresholds
- [x] OR-logic veto on PWM commands upon any threshold violation
- [x] Mock sensor publisher with 6 pre-defined fault scenarios
- [x] Safety interventions validated: proximity → thrust cutoff, attitude → command block
- [ ] Full integration with Gazebo UAV/UGV sensor plugins (lidar, IMU)

### Phase 3 - Integration and Full Pipeline

- [ ] Route actuator commands through safety board before Gazebo dispatch
- [ ] Wire token-based activation to PWM command generation end-to-end
- [ ] Real-time monitoring: token status, safety check results, pre/post-safety commands
- [ ] ROS 2 bag recording and scenario replay

### Phase 4 - Evaluation

- [ ] Resilience testing: dropped tokens, forged tokens, partial sensor failure
- [ ] Extend to 3+ heterogeneous robots (UAV + UGV)
- [ ] Demonstration video: nominal operation, safety veto, token expiry

### Phase 5 - Documentation and Submission

- [ ] Complete API documentation for all nodes and topics
- [ ] Finalize GitHub repository
- [ ] Submit thesis report (PDF)

---

## Development Commands

```bash
make help               # full command reference
make show-guide         # complete usage guide with all demo workflows

make docker-shell       # open interactive shell inside the container
make ros2-rebuild-ws    # clean and rebuild the ROS 2 workspace
make diagnose           # full system diagnostic
make check-gpu          # verify GPU acceleration level
make kill-all           # terminate all processes and stop container
```

---

## Web Dashboard

A browser-based monitoring panel is included under `src/web_dashboard/`.
It bridges ROS 2 token topics to the browser via WebSocket, providing live
token stream visualization, per-agent statistics, and demo lifecycle control.

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
