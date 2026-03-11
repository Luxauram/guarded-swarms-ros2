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
# px4.mk - PX4 SITL and Gazebo management
# ==============================================================================
#
# Vehicle targets:
#   px4-run-uav    UAV  - x500 quadcopter with frontal lidar
#   px4-run-rover  UGV  - differential rover with frontal lidar (Guarded Swarms)
#   px4-run        UAV  - alias for px4-run-uav (backward compat)
#   px4-gui        UAV  - x500 with Gazebo GUI (requires X server)
#
# Setup:
#   setup-rover    Install custom airframe + model into PX4 (run once)
#
# ==============================================================================

.PHONY: px4-run px4-run-uav px4-run-rover px4-gui \
        px4-kill px4-console px4-config px4-reset-params \
        setup-rover gazebo-test gazebo-worlds

# ------------------------------------------------------------------------------
# Shared PX4 guard
# ------------------------------------------------------------------------------
define CHECK_PX4
	@if ! $(DOCKER_EXEC) bash -c "test -d $(PX4_DIR)"; then \
		echo "Error: PX4-Autopilot not found."; \
		echo "Run 'make setup-px4' first."; \
		exit 1; \
	fi
endef

# ------------------------------------------------------------------------------
# UAV - x500 with lidar (main vehicle for Guarded Swarms Phase 3)
# ------------------------------------------------------------------------------
px4-run-uav:
	@echo "=========================================="
	@echo "Launching PX4 SITL - UAV (x500 + lidar)"
	@echo "=========================================="
	$(CHECK_PX4)
	@$(DOCKER_EXEC) bash -c "$(KILL_PX4)"
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
	@$(DOCKER_EXEC_IT) bash -c "cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_x500_lidar_front"

# Backward-compat alias
px4-run: px4-run-uav

# ------------------------------------------------------------------------------
# UGV - differential rover with lidar (Guarded Swarms custom model)
# Requires: make setup-rover (run once after setup-px4)
# ------------------------------------------------------------------------------
px4-run-rover:
	@echo "=========================================="
	@echo "Launching PX4 SITL - UGV (rover + lidar)"
	@echo "=========================================="
	$(CHECK_PX4)
	@if ! $(DOCKER_EXEC) bash -c "test -f $(PX4_DIR)/ROMFS/px4fmu_common/init.d-posix/airframes/50001_gz_rover_differential_lidar"; then \
		echo ""; \
		echo "ERROR: Guarded Swarms rover airframe not installed."; \
		echo "Run 'make setup-rover' first (only needed once)."; \
		echo ""; \
		exit 1; \
	fi
	@$(DOCKER_EXEC) bash -c "$(KILL_PX4)"
	@sleep 1
	@echo "Rover starts on ground - no arming commands needed."
	@echo ""
	@$(DOCKER_EXEC_IT) bash -c "cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_rover_differential_lidar"

# ------------------------------------------------------------------------------
# UAV with Gazebo GUI (requires X server on host)
# ------------------------------------------------------------------------------
px4-gui:
	@echo "=========================================="
	@echo "Launching PX4 SITL with Gazebo GUI"
	@echo "=========================================="
	$(CHECK_PX4)
	@echo "Stopping any existing PX4 and Gazebo instances..."
	@$(DOCKER_EXEC) bash -c "pkill -9 px4 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 -f 'gz sim' 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 gzserver 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 gzclient 2>/dev/null || true" 2>/dev/null || true
	@sleep 3
	@echo "Prerequisites:"
	@echo "  - X server must be running"
	@echo "  - Windows: VcXsrv with 'Disable access control' enabled"
	@echo "  - Linux:   xhost +local:docker"
	@echo ""
	@echo "Starting Gazebo with 3D visualization..."
	@$(DOCKER_EXEC_IT) bash -c "cd $(PX4_DIR) && make px4_sitl gz_x500_lidar_front"

# ------------------------------------------------------------------------------
# Setup: install Guarded Swarms rover assets into PX4 (run once)
#
# What this does (documented for reproducibility):
#   1. Copies our custom airframe file (50001_gz_rover_differential_lidar)
#      into PX4's airframes directory so 'make px4_sitl gz_rover_differential_lidar'
#      is a valid build target. PX4 auto-discovers airframes by filename convention.
#   2. Copies our rover_differential_lidar Gazebo model (which extends the stock
#      rover_differential via <include merge='true'>) into PX4's models directory
#      so Gazebo can find it by name at spawn time.
#   3. Rebuilds PX4 SITL so the new airframe is registered in the binary.
#
# This follows the same pattern PX4 uses internally for all gz_* variants.
# We do NOT modify any existing PX4 files.
# ------------------------------------------------------------------------------
setup-rover:
	@echo "=========================================="
	@echo "Installing Guarded Swarms Rover Assets"
	@echo "=========================================="
	@echo ""
	$(CHECK_PX4)
	@echo "[1/3] Installing custom airframe (50001_gz_rover_differential_lidar)..."
	@$(DOCKER_EXEC) bash -c "cp $(GS_AIRFRAMES_DIR)/50001_gz_rover_differential_lidar \
		$(PX4_DIR)/ROMFS/px4fmu_common/init.d-posix/airframes/"
	@echo "      Done."
	@echo ""
	@echo "[2/3] Installing rover_differential_lidar Gazebo model..."
	@$(DOCKER_EXEC) bash -c "cp -r $(GS_MODELS_DIR)/rover_differential_lidar \
		$(PX4_DIR)/Tools/simulation/gz/models/"
	@echo "      Done."
	@echo ""
	@echo "[3/3] Rebuilding PX4 SITL to register new airframe..."
	@$(DOCKER_EXEC) bash -c "cd $(PX4_DIR) && make px4_sitl_default 2>&1 | tail -3"
	@echo ""
	@echo "=========================================="
	@echo "Rover setup complete."
	@echo "Run 'make px4-run-rover' to launch."
	@echo "=========================================="
	@echo ""

# ------------------------------------------------------------------------------
# Misc PX4 targets
# ------------------------------------------------------------------------------
px4-kill:
	@echo "Killing all PX4 and Gazebo processes..."
	@$(DOCKER_EXEC) bash -c "$(KILL_PX4)"
	@$(DOCKER_EXEC) bash -c "$(KILL_GAZEBO)"
	@$(DOCKER_EXEC) bash -c "$(KILL_MICRO_ROS)"
	@$(DOCKER_EXEC) bash -c "find $(PX4_DIR)/build/px4_sitl_default -name 'parameters*.bson' -delete 2>/dev/null || true"
	@$(DOCKER_EXEC) bash -c "find $(PX4_DIR)/build/px4_sitl_default -name 'dataman' -delete 2>/dev/null || true"
	@echo "All processes stopped."

px4-console:
	@echo "Opening PX4 interactive console (UAV)..."
	$(CHECK_PX4)
	@$(DOCKER_EXEC_IT) bash -c "cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_x500_lidar_front"

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

# ------------------------------------------------------------------------------
# Gazebo utilities
# ------------------------------------------------------------------------------
gazebo-test:
	@echo "=========================================="
	@echo "Testing Gazebo Installation"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites:"
	@echo "  - X server must be running"
	@echo ""
	@echo "Launching Gazebo with empty world..."
	@echo "Close the Gazebo window to continue."
	@echo ""
	@$(DOCKER_EXEC_IT) bash -c "gz sim worlds/empty.sdf"

gazebo-worlds:
	@echo "Available Gazebo worlds:"
	@echo ""
	@$(DOCKER_EXEC) bash -c "ls -1 $(PX4_DIR)/Tools/simulation/gz/worlds/ 2>/dev/null || echo 'PX4-Autopilot not found. Run make setup-px4 first.'"
	@echo ""
	@echo "To launch a specific world:"
	@echo "  make docker-shell"
	@echo "  gz sim /workspace/PX4-Autopilot/Tools/simulation/gz/worlds/<world_name>.sdf"
