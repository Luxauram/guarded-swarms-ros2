# Guarded Swarms ROS 2

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org/en/humble/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-orange.svg)](https://gazebosim.org/)
[![PX4](https://img.shields.io/badge/PX4-SITL-green.svg)](https://px4.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

ROS 2 simulation framework implementing hybrid digital-analog coordination for autonomous multi-robot systems (UAV + UGV). Developed as part of a thesis project at the University of Molise, in collaboration with ongoing research in swarm robotics.

Based on: _Borghoff, Bottoni, Pareschi (2025) — "Guarded Swarms: Hybrid Digital-Analog Coordination for AI-Robot Systems"_

---

## Overview

The Guarded Swarms architecture coordinates autonomous agents through two complementary layers:

- **Digital coordination layer** — a token-based arbitration system inspired by TB-CSPN, where agents request access to shared zones by issuing cryptographically signed geometry and authorization tokens. A coordinator node resolves concurrent requests within a configurable time window.
- **Analog safety enforcement layer** — a virtual safety board that monitors real-time sensor data and vetoes actuator commands that violate safety thresholds, independently of the digital layer.

This repository provides a modular ROS 2 implementation of both layers, integrated with PX4 SITL and Gazebo for simulation, and complemented by a real-time web dashboard for monitoring and control.

---

## Architecture

```
guarded-swarms-ros2/
├── docker/                         # Containerized development environment
│   ├── Dockerfile                  # ROS 2 Humble + Gazebo Harmonic + PX4 deps
│   └── docker-compose.yml
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
│   ├── guarded_swarms_control/     # Offboard UAV control node (C++)
│   │
│   ├── tools/
│   │   ├── launch/
│   │   │   └── demo.launch.py      # Full system launch file
│   │   ├── visualization/
│   │   │   └── dashboard.py        # Lightweight terminal dashboard
│   │   └── docs/
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

## Development Roadmap

Progress is tracked against the thesis milestones defined in the project plan.

### Phase 0 — Environment Setup and Literature Review

- [x] Set up ROS 2 Humble + Gazebo Harmonic in a Docker container
- [x] Validate PX4 SITL integration via micro-ROS bridge
- [x] Implement basic UAV offboard control (takeoff, hover, position hold)
- [x] Establish Makefile-based development workflow

### Phase 1 — Digital Coordination Layer (Token System)

- [x] Define custom ROS 2 message types (`Token`, `GeometryToken`, `AuthToken`)
- [x] Implement `agent_node`: publishes geometry and authorization tokens
- [x] Implement `coordinator_node`: arbitrates concurrent requests with configurable time window and signature validation
- [x] Implement token buffering and expiry logic
- [x] Deploy real-time web dashboard for token stream monitoring (`web_dashboard/`)
- [x] Validate multi-agent concurrency and arbitration with live demo

### Phase 2 — Analog Safety Enforcement Layer

- [x] Implement `safety_board` ROS 2 node with configurable sensor thresholds
- [x] Subscribe to simulated sensor topics (proximity, attitude, battery)
- [x] Implement OR-logic veto on PWM commands upon threshold violation
- [ ] Integrate safety board with Gazebo UAV/UGV sensor plugins
- [x] Validate safety interventions: obstacle proximity → thrust cutoff, pitch limit → command block

### Phase 3 — Integration and Digital Twin

- [ ] Route actuator commands through the safety board before Gazebo dispatch
- [ ] Wire token-based activation to PWM command generation
- [ ] Build real-time monitoring view: token status, safety check results, pre/post-safety actuator commands
- [ ] Implement ROS 2 bag recording and scenario replay

### Phase 4 — Evaluation and Extension

- [ ] Resilience testing: dropped tokens, forged tokens, partial sensor failure
- [ ] Extend to 3+ heterogeneous robots (UAV + UGV)
- [ ] Evaluate one optional extension: additional safety constraints, or dual Petri net (Section V of the paper)
- [ ] Record demonstration video: nominal operation, safety veto, token expiry
- [ ] Prepare final report and presentation

### Phase 5 — Documentation and Submission

- [ ] Complete API documentation for all nodes and topics
- [ ] Write user guide for running simulations
- [ ] Finalize GitHub repository
- [ ] Submit thesis report (PDF)

---

## Prerequisites

### System Requirements

| Component | Requirement                                    |
| --------- | ---------------------------------------------- |
| OS        | Windows 10/11 (WSL2), Ubuntu 20.04+, macOS 12+ |
| Docker    | Docker Desktop 4.0+ / Docker Engine 20.10+     |
| RAM       | 8 GB minimum, 16 GB recommended                |
| Storage   | 10 GB free for Docker images                   |

### X Server (for Gazebo GUI)

| Platform | Tool                                               |
| -------- | -------------------------------------------------- |
| Windows  | [VcXsrv](https://sourceforge.net/projects/vcxsrv/) |
| Linux    | Native X11 — run `xhost +local:docker`             |
| macOS    | [XQuartz](https://www.xquartz.org/)                |

---

## Quick Start

@TODO

---

## Web Dashboard

A browser-based monitoring and control panel is included under `src/web_dashboard/`. It bridges ROS 2 token topics to the browser via WebSocket, providing live token stream visualization, per-agent statistics, and demo lifecycle control without requiring a separate terminal.

See [`src/web_dashboard/README.md`](src/web_dashboard/README.md) for setup instructions.

---

## Citation

If you use or reference this work, please cite the paper it is based on:

```
Borghoff, U. M., Bottoni, P., & Pareschi, R. (2025).
Guarded Swarms: Hybrid Digital-Analog Coordination for AI-Robot Systems.
```

---

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Developed under the supervision of Prof. R. Pareschi, University of Molise.
- Built on [PX4 Autopilot](https://px4.io/) and [ROS 2 Humble](https://docs.ros.org/en/humble/).
- Gazebo simulation powered by [Gazebo Harmonic](https://gazebosim.org/).
- Coordination architecture based on the Guarded Swarms paper by Borghoff, Bottoni, and Pareschi (2025).
