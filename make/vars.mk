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
# ==============================================================================

# ------------------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------------------
DOCKER_DIR         := docker
WORKSPACE_DIR      := /workspace
SRC_DIR            := $(WORKSPACE_DIR)/src
INSTALL_DIR        := $(WORKSPACE_DIR)/install
BUILD_DIR          := $(WORKSPACE_DIR)/build
PX4_DIR            := $(WORKSPACE_DIR)/PX4-Autopilot

WEB_BACKEND_DIR    := src/web_dashboard/backend
WEB_FRONTEND_DIR   := src/web_dashboard/frontend
TOOLS_LAUNCH_DIR   := src/tools/launch
TOOLS_VIZ_DIR      := src/tools/visualization

# Guarded Swarms custom assets (not part of PX4 repo)
GS_MODELS_DIR      := $(WORKSPACE_DIR)/src/guarded_swarms_safety/models
GS_AIRFRAMES_DIR   := $(WORKSPACE_DIR)/src/guarded_swarms_safety/px4_airframes

# ------------------------------------------------------------------------------
# Docker
# ------------------------------------------------------------------------------
CONTAINER_NAME  := guarded_swarms
DOCKER_EXEC     := docker exec $(CONTAINER_NAME)
DOCKER_EXEC_IT  := docker exec -it $(CONTAINER_NAME)

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
KILL_PX4       := pkill -9 px4 2>/dev/null || true
KILL_GAZEBO    := pgrep -f '^gz sim' | xargs -r kill -9 2>/dev/null || true; \
                  pkill -9 gzserver 2>/dev/null || true; \
                  pkill -9 gzclient 2>/dev/null || true
KILL_MICRO_ROS := pkill -9 MicroXRCEAgent 2>/dev/null || true
KILL_ROS2      := pkill -9 -f 'ros2' 2>/dev/null || true; \
                  pkill -9 python3 2>/dev/null || true
KILL_WEB       := pkill -9 -f 'uvicorn.*app:app' 2>/dev/null || true; \
                  pkill -9 -f 'python3.*uvicorn' 2>/dev/null || true; \
                  fuser -k $(DASHBOARD_PORT)/tcp 2>/dev/null || true
CLEANUP_TMP    := rm -rf /tmp/.gazebo* /tmp/.X* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true

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
