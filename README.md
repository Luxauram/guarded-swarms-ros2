# Guarded Swarms: ROS 2 Implementation

**Work in Progress**

ROS 2 digital twin implementing Guarded Swarms hybrid coordination for UAV-UGV swarms.

Based on: Borghoff, Bottoni, Pareschi (2025) - "Guarded Swarms: Hybrid Digital-Analog Coordination for AI-Robot Systems"

## PX4 SITL Setup

PX4-Autopilot is cloned manually inside the container (not tracked in Git).

### Clone PX4

```bash
docker exec -it guarded_swarms_dev bash
cd /workspace
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools
```

### First Build (~10 min)

```bash
HEADLESS=1 make px4_sitl gz_x500
```

### Run System (3 terminals required)

**Terminal 1: micro-ROS Agent**

```bash
docker exec -it guarded_swarms_dev bash
MicroXRCEAgent udp4 -p 8888
```

**Terminal 2: PX4 SITL**

```bash
docker exec -it guarded_swarms_dev bash
cd /workspace/PX4-Autopilot
HEADLESS=1 make px4_sitl gz_x500
```

**Terminal 3: Verify Topics**

```bash
docker exec -it guarded_swarms_dev bash
source /workspace/install/setup.bash
ros2 topic list | grep fmu
```

# Status

- [x] Docker environment with ROS 2 Humble + Gazebo Harmonic

- [x] PX4 SITL integration

- [x] micro-ROS bridge functional

- [x] 242 PX4 message types available

- [ ] Offboard control node

## Quick Start

@TODO

## License

Apache-2.0
