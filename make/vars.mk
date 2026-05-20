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
# Requires: Ubuntu 22.04 or 24.04, ROS 2 Jazzy, PX4, Gazebo Harmonic.
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
WEB_BACKEND_DIR  := $(REPO_ROOT)/src/web_dashboard/backend
WEB_FRONTEND_DIR := $(REPO_ROOT)/src/web_dashboard/frontend
TOOLS_LAUNCH_DIR := src/tools/launch
TOOLS_VIZ_DIR    := src/tools/visualization

# Guarded Swarms custom assets (not part of PX4 repo)
GS_MODELS_DIR    := $(SRC_DIR)/guarded_swarms_safety/models
GS_AIRFRAMES_DIR := $(SRC_DIR)/guarded_swarms_safety/px4_airframes

# ------------------------------------------------------------------------------
# ROS 2
# ------------------------------------------------------------------------------
ROS2_SOURCE      := source /opt/ros/jazzy/setup.bash
WORKSPACE_SOURCE := source $(INSTALL_DIR)/setup.bash
FULL_SOURCE      := $(ROS2_SOURCE) && $(WORKSPACE_SOURCE)

COORDINATOR_PKG  := guarded_swarms_coordinator
CONTROL_PKG      := guarded_swarms_control
SAFETY_PKG       := guarded_swarms_safety

# ------------------------------------------------------------------------------
# Process management (all on single lines - no backslash continuations)
# ------------------------------------------------------------------------------
KILL_PX4       := pkill -9 -x px4 2>/dev/null || true
KILL_GAZEBO    := pkill -9 -f "gz sim" 2>/dev/null || true; pkill -9 gzserver 2>/dev/null || true; pkill -9 gzclient 2>/dev/null || true
KILL_MICRO_ROS := pkill -9 MicroXRCEAgent 2>/dev/null || true
KILL_ROS2      := pkill -9 -f 'ros2' 2>/dev/null || true; pkill -9 python3 2>/dev/null || true
KILL_WEB       := pkill -9 -f 'uvicorn.*app:app' 2>/dev/null || true; pkill -9 -f 'python3.*uvicorn' 2>/dev/null || true; fuser -k $(DASHBOARD_PORT)/tcp 2>/dev/null || true
CLEANUP_TMP    := rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true

# ------------------------------------------------------------------------------
# Build
# ------------------------------------------------------------------------------
COLCON_BUILD          := colcon build --symlink-install
COLCON_BUILD_PKG      = colcon build --packages-select
COLCON_BUILD_PARALLEL := $(COLCON_BUILD) --parallel-workers 4 --event-handlers console_direct+

# ------------------------------------------------------------------------------
# Web dashboard
# ------------------------------------------------------------------------------
DASHBOARD_PORT := 8765