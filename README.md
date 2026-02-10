# Guarded Swarms ROS 2

[![ROS 2](https://img.shields.io/badge/ROS_2-Humble-blue.svg)](https://docs.ros.org/en/humble/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Harmonic-orange.svg)](https://gazebosim.org/)
[![PX4](https://img.shields.io/badge/PX4-SITL-green.svg)](https://px4.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

ROS 2 implementation exploring hybrid digital-analog coordination for autonomous UAV systems. The system integrates PX4 SITL, Gazebo simulation, and micro-ROS bridge for offboard control experiments.

Based on: Borghoff, Bottoni, Pareschi (2025) - "Guarded Swarms: Hybrid Digital-Analog Coordination for AI-Robot Systems"

## Overview

This project implements a modular ROS 2 simulation framework for hybrid digital-analog robot coordination.

## Architecture

@TODO

## Features

### Currently Implemented

- **Dockerized Environment**: Reproducible ROS 2 Humble + Gazebo Harmonic setup
- **PX4 Integration**: Micro-ROS bridge connecting PX4 SITL to ROS 2 ecosystem
- **Offboard Control**: Autonomous UAV takeoff, hover, and position hold
- **3D Visualization**: Gazebo GUI with X11 forwarding for cross-platform support
- **Development Workflow**: Makefile-based automation for building, testing, and deployment

## Prerequisites

### System Requirements

- **OS**: Windows 10/11 (WSL2), Ubuntu 20.04+, or macOS 12+
- **Docker**: Docker Desktop 4.0+ or Docker Engine 20.10+
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 10GB free space for Docker images

### X Server (for GUI)

- **Windows**: [VcXsrv](https://sourceforge.net/projects/vcxsrv/)
- **Linux**: Native X11 (run `xhost +local:docker`)
- **macOS**: [XQuartz](https://www.xquartz.org/)

## Quick Start

@TODO

## Development Workflow

@TODO

## Project Structure

```
guarded-swarms-ros2/
├── docker/
│   ├── Dockerfile              # ROS 2 + Gazebo + PX4 dependencies
│   └── docker-compose.yml      # Container configuration
├── src/
│   ├── guarded_swarms_control/ # Offboard control node
│   ├── px4_msgs/               # PX4 message definitions
│   └── px4_ros_com/            # PX4-ROS 2 communication
├── Makefile                    # Automation commands
├── README.md                   # This file
└── LICENSE                     # Apache 2.0
```

## Citation

@TODO

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built on [PX4 Autopilot](https://px4.io/) and [ROS 2 Humble](https://docs.ros.org/en/humble/)
- Gazebo simulation powered by [Gazebo Harmonic](https://gazebosim.org/)
- Inspired by the Guarded Swarms coordination architecture

---
