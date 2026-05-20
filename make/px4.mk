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
# px4.mk - PX4 SITL and Gazebo management (native Ubuntu)
#
# PX4-Autopilot is installed at ~/PX4-Autopilot (outside the repo).
# Gazebo Harmonic runs natively on the host.
# ==============================================================================

.PHONY: px4-run-uav px4-run-ugv px4-gui-uav px4-gui-ugv \
        px4-kill px4-config px4-reset-params \
        setup-ugv gazebo-test gazebo-worlds

# ------------------------------------------------------------------------------
# Guard: verify PX4 is installed
# ------------------------------------------------------------------------------
define CHECK_PX4
	@if [ ! -d "$(PX4_DIR)" ]; then \
		echo "Error: PX4-Autopilot not found at $(PX4_DIR)."; \
		echo "Run 'make setup-px4' first."; \
		exit 1; \
	fi
endef

# ------------------------------------------------------------------------------
# UAV - x500 with frontal lidar (headless)
# ------------------------------------------------------------------------------
px4-run-uav:
	@echo "=========================================="
	@echo "Launching PX4 SITL - UAV (x500 + lidar)"
	@echo "=========================================="
	$(CHECK_PX4)
	@pkill -9 -x px4 2>/dev/null || true
	@sleep 1
	@echo "Arming commands at pxh> prompt:"
	@echo "  param set COM_ARM_WO_GPS 1"
	@echo "  param set SYS_HAS_MAG 0"
	@echo "  param set COM_RC_IN_MODE 1"
	@echo "  param set NAV_RCL_ACT 0"
	@echo "  param set NAV_DLL_ACT 0"
	@echo "  param set COM_RCL_EXCEPT 4"
	@echo "  param save"
	@echo "  commander takeoff"
	@echo ""
	@cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_x500_lidar_front

# ------------------------------------------------------------------------------
# UGV - differential rover with frontal lidar (headless)
# Requires: make setup-ugv (run once)
# ------------------------------------------------------------------------------
px4-run-ugv:
	@echo "=========================================="
	@echo "Launching PX4 SITL - UGV (rover + lidar)"
	@echo "=========================================="
	$(CHECK_PX4)
	@if [ ! -f "$(PX4_DIR)/ROMFS/px4fmu_common/init.d-posix/airframes/50001_gz_rover_differential_lidar" ]; then \
		echo ""; \
		echo "ERROR: Guarded Swarms rover airframe not installed."; \
		echo "Run 'make setup-ugv' first (only needed once)."; \
		echo ""; \
		exit 1; \
	fi
	@pkill -9 -x px4 2>/dev/null || true
	@sleep 1
	@echo "Rover starts on ground - no arming commands needed."
	@echo ""
	@cd $(PX4_DIR)/build/px4_sitl_default && PX4_SYS_AUTOSTART=50001 PX4_GZ_WORLD=rover PX4_SIM_MODEL=rover_differential_lidar PX4_GZ_WORLDS=$(PX4_DIR)/Tools/simulation/gz/worlds GZ_SIM_RESOURCE_PATH=$(PX4_DIR)/Tools/simulation/gz/models HEADLESS=1 ./bin/px4 -s etc/init.d-posix/rcS

# ------------------------------------------------------------------------------
# UAV with Gazebo GUI (native)
# ------------------------------------------------------------------------------
px4-gui-uav:
	@echo "=========================================="
	@echo "Launching PX4 SITL + Gazebo GUI - UAV"
	@echo "=========================================="
	$(CHECK_PX4)
	@pkill -9 -x px4 2>/dev/null || true
	@pkill -9 gzserver 2>/dev/null || true
	@pkill -9 gzclient 2>/dev/null || true
	@sleep 2
	@echo "Starting Gazebo with 3D visualization..."
	@echo ""
	@cd $(PX4_DIR) && make px4_sitl gz_x500_lidar_front

# ------------------------------------------------------------------------------
# UGV with Gazebo GUI (native)
# ------------------------------------------------------------------------------
px4-gui-ugv:
	@echo "=========================================="
	@echo "Launching PX4 SITL + Gazebo GUI - UGV"
	@echo "=========================================="
	$(CHECK_PX4)
	@pkill -9 -x px4 2>/dev/null || true
	@pkill -9 gzserver 2>/dev/null || true
	@pkill -9 gzclient 2>/dev/null || true
	@sleep 2
	@echo "Starting Gazebo with 3D visualization..."
	@echo ""
	@find $(PX4_DIR)/build/px4_sitl_default -name 'parameters*.bson' -delete 2>/dev/null || true
	@cd $(PX4_DIR)/build/px4_sitl_default && PX4_SYS_AUTOSTART=50001 PX4_GZ_WORLD=rover PX4_SIM_MODEL=rover_differential_lidar PX4_GZ_WORLDS=$(PX4_DIR)/Tools/simulation/gz/worlds GZ_SIM_RESOURCE_PATH=$(PX4_DIR)/Tools/simulation/gz/models ./bin/px4 -s etc/init.d-posix/rcS

# ------------------------------------------------------------------------------
# Setup: install Guarded Swarms rover assets into PX4 (run once)
# ------------------------------------------------------------------------------
setup-ugv:
	@echo "=========================================="
	@echo "Installing Guarded Swarms Rover Assets"
	@echo "=========================================="
	@echo ""
	$(CHECK_PX4)
	@echo "[1/3] Installing custom airframe..."
	@cp $(GS_AIRFRAMES_DIR)/50001_gz_rover_differential_lidar $(PX4_DIR)/ROMFS/px4fmu_common/init.d-posix/airframes/
	@cp $(GS_AIRFRAMES_DIR)/50001_gz_rover_differential_lidar $(PX4_DIR)/build/px4_sitl_default/rootfs/etc/init.d-posix/airframes/ 2>/dev/null || true
	@echo "      Done."
	@echo ""
	@echo "[2/3] Installing rover_differential_lidar Gazebo model..."
	@cp -r $(GS_MODELS_DIR)/rover_differential_lidar $(PX4_DIR)/Tools/simulation/gz/models/
	@echo "      Done."
	@echo ""
	@echo "[3/3] Rebuilding PX4 SITL to register new airframe..."
	@cd $(PX4_DIR) && make px4_sitl_default 2>&1 | tail -3
	@echo ""
	@echo "Rover setup complete. Run 'make px4-run-ugv' to launch."
	@echo ""

# ------------------------------------------------------------------------------
# Misc
# ------------------------------------------------------------------------------
px4-kill:
	@echo "Killing all PX4 and Gazebo processes..."
	@pkill -9 -x px4 2>/dev/null || true
	@pkill -9 gzserver 2>/dev/null || true
	@pkill -9 gzclient 2>/dev/null || true
	@pkill -9 MicroXRCEAgent 2>/dev/null || true
	@find $(PX4_DIR)/build/px4_sitl_default -name 'parameters*.bson' -delete 2>/dev/null || true
	@find $(PX4_DIR)/build/px4_sitl_default -name 'dataman' -delete 2>/dev/null || true
	@echo "All processes stopped."

px4-config:
	@echo "=========================================="
	@echo "PX4 Offboard Config - copy at pxh> prompt"
	@echo "=========================================="
	@echo ""
	@echo "param set COM_ARM_WO_GPS 1"
	@echo "param set SYS_HAS_MAG 0"
	@echo "param set COM_RC_IN_MODE 1"
	@echo "param set NAV_RCL_ACT 0"
	@echo "param set NAV_DLL_ACT 0"
	@echo "param set COM_RCL_EXCEPT 4"
	@echo "param save"
	@echo ""

px4-reset-params:
	@echo "=========================================="
	@echo "PX4 Reset to Defaults - copy at pxh> prompt"
	@echo "=========================================="
	@echo ""
	@echo "param set COM_ARM_WO_GPS 0"
	@echo "param set SYS_HAS_MAG 1"
	@echo "param set COM_RC_IN_MODE 4"
	@echo "param set NAV_RCL_ACT 2"
	@echo "param set NAV_DLL_ACT 2"
	@echo "param set COM_RCL_EXCEPT 0"
	@echo "param save"
	@echo ""

gazebo-test:
	@echo "Launching Gazebo with empty world..."
	@gz sim worlds/empty.sdf

gazebo-worlds:
	@echo "Available Gazebo worlds:"
	@echo ""
	@ls -1 $(PX4_DIR)/Tools/simulation/gz/worlds/ 2>/dev/null || echo "PX4-Autopilot not found. Run make setup-px4 first."
	@echo ""