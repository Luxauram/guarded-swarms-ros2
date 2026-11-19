# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ==============================================================================
# vars.mk - Shared constants for all Makefiles
#
# Native Ubuntu installation.
# Requires: Ubuntu 22.04, ROS 2 Humble, PX4, Gazebo Harmonic.
# ==============================================================================

# ------------------------------------------------------------------------------
# Repo root (absolute path, resolved at make time)
# ------------------------------------------------------------------------------
REPO_ROOT := $(shell pwd)

# ------------------------------------------------------------------------------
# Paths - all relative to the repo root or home directory
# ------------------------------------------------------------------------------
WORKSPACE_DIR    := $(REPO_ROOT)
SRC_DIR          := $(REPO_ROOT)/src
INSTALL_DIR      := $(REPO_ROOT)/install
BUILD_DIR        := $(REPO_ROOT)/build
PX4_DIR          := $(HOME)/PX4-Autopilot

# PX4 firmware pinned commit.
# px4_msgs@31147da is generated from this exact PX4 commit; any other
# firmware version will silently break uXRCE-DDS topic bridging.
PX4_COMMIT       := 091ac918b133d518da8b73e395243ea0e0d087b5
PX4_BRANCH       := guarded-swarms-pin
TOOLS_LAUNCH_DIR := src/tools/launch
TOOLS_VIZ_DIR    := src/tools/visualization
RESILIENCE_DIR   := $(REPO_ROOT)/scripts/resilience

# Guarded Swarms custom assets (not part of PX4 repo)
GS_MODELS_DIR    := $(SRC_DIR)/guarded_swarms_gz/models
GS_AIRFRAMES_DIR := $(SRC_DIR)/guarded_swarms_safety/px4_airframes

# Guarded Swarms Gazebo worlds (guarded_swarms_gz package)
GS_WORLDS_DIR    := $(SRC_DIR)/guarded_swarms_gz/worlds
GS_GZ_MODELS_DIR := $(SRC_DIR)/guarded_swarms_gz/models

# GZ_SIM_RESOURCE_PATH: tells Gazebo where to find our worlds and models
# without copying anything into the PX4 installation.
# My assets first, so model:// resolves to the Guarded Swarms versions.
# Gazebo itself is launched by scripts/sim/gz_launch.sh; this is passed to the PX4
# process so that it reads MY model.sdf when spawning the vehicle.
GZ_RESOURCE_PATH := $(GS_GZ_MODELS_DIR):$(GS_WORLDS_DIR)

GZ_LAUNCH        := bash $(REPO_ROOT)/scripts/sim/gz_launch.sh
# PX4_GZ_NO_FOLLOW: stops PX4 from putting the GUI camera in FOLLOW mode on
# the vehicle it spawns. Follow mode disables orbit and pan, so with more than
# one vehicle the view becomes unusable.
PX4_STANDALONE   := PX4_GZ_STANDALONE=1 PX4_GZ_NO_FOLLOW=1
GZ_BOOT_WAIT     := 8

# ------------------------------------------------------------------------------
# ROS 2
# ------------------------------------------------------------------------------
ROS2_SOURCE      := source /opt/ros/humble/setup.bash
WORKSPACE_SOURCE := source $(INSTALL_DIR)/setup.bash
FULL_SOURCE      := $(ROS2_SOURCE) && $(WORKSPACE_SOURCE)
COORDINATOR_PKG  := guarded_swarms_coordinator
CONTROL_PKG      := guarded_swarms_control
SAFETY_PKG       := guarded_swarms_safety

# ------------------------------------------------------------------------------
# Process management
# ------------------------------------------------------------------------------
KILL_PX4       := pkill -9 -x px4 2>/dev/null || true
KILL_GAZEBO    := pkill -9 gzserver 2>/dev/null || true; pkill -9 gzclient 2>/dev/null || true; pkill -9 -f "gz_sim_server|gz-sim" 2>/dev/null || true
KILL_MICRO_ROS := pkill -9 MicroXRCEAgent 2>/dev/null || true
KILL_ROS2      := pkill -9 -f 'ros2' 2>/dev/null || true; pkill -9 python3 2>/dev/null || true
CLEANUP_TMP    := rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true

# ------------------------------------------------------------------------------
# Build
# ------------------------------------------------------------------------------
COLCON_BUILD          := colcon build --symlink-install
COLCON_BUILD_PKG      = colcon build --packages-select
COLCON_BUILD_PARALLEL := $(COLCON_BUILD) --parallel-workers 4 --event-handlers console_direct+

# ------------------------------------------------------------------------------
# Swarm scenario
# ------------------------------------------------------------------------------
SWARM_WORLD    := urban_ugv
UAV_POSE       := 0,0,0
# Offset along Y only: the rover patrols along X toward the abandoned vehicle,
# so it must stay on the obstacle's line while clearing the UAV's spawn point.
UGV_POSE       := -4,0,0
UAV_BOOT_WAIT  := 15

# ------------------------------------------------------------------------------
# Coastal scenario (IET paper 5.1): 2 UAV + 1 UGV
#
# Poses are Gazebo ENU (X = East, Y = North). The UAV pads are at (+/-24, -24)
# and the shore road the rover patrols runs along X at Y = -14.
# ------------------------------------------------------------------------------
COASTAL_WORLD    := coastal
UAV0_POSE        := -24,-24,0
UAV1_POSE        := 24,-24,0
COASTAL_UGV_POSE := -60,-14,0

# Rover patrol, NED relative to spawn, flattened as north,east,north,east...
# NED East = Gazebo X, so varying the SECOND value drives along the shore.
# From X = -60 eastward: the road barrier at X = -8 stops it via proximity veto.
# Patrol turnaround sits short of the road barrier at Gazebo X = -8: the
# patrol route is deliberately clear. The proximity veto is a safety net for
# obstacles that appear unexpectedly, not a navigation mechanism — route
# replanning belongs to the worker agents in the digital layer.
COASTAL_UGV_WAYPOINTS := [0.0, 0.0, 0.0, 46.0]