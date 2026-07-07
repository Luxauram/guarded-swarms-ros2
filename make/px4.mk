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
#
# World files live in src/guarded_swarms_gz/worlds/ (never copied into PX4).
# GZ_SIM_RESOURCE_PATH is set at launch time to include our worlds + models.
# ==============================================================================

.PHONY: px4-run-uav px4-run-ugv \
        px4-gui-uav px4-gui-ugv \
        px4-gui-uav-urban px4-gui-ugv-urban \
        px4-kill px4-config px4-reset-params \
        setup-ugv setup-worlds gazebo-test gazebo-worlds

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
# Guard: verify UGV assets are installed
# ------------------------------------------------------------------------------
define CHECK_UGV
	@if ! grep -q "lidar_sensor_link" "$(PX4_DIR)/Tools/simulation/gz/models/r1_rover/model.sdf" 2>/dev/null; then \
		echo ""; \
		echo "ERROR: Guarded Swarms rover airframe not installed."; \
		echo "Run 'make setup-ugv' first (only needed once)."; \
		echo ""; \
		exit 1; \
	fi
endef

# ------------------------------------------------------------------------------
# Shared Gazebo kill block (used in all gui targets)
# Kills all Gazebo Harmonic processes cleanly before launching a new world.
# ------------------------------------------------------------------------------
define GZ_KILL
	@bash $(REPO_ROOT)/scripts/gz_kill.sh
endef

# ------------------------------------------------------------------------------
# UAV - x500 with frontal lidar (headless, default world)
# ------------------------------------------------------------------------------
px4-run-uav:
	@echo "=========================================="
	@echo "Launching PX4 SITL - UAV (headless)"
	@echo "=========================================="
	$(CHECK_PX4)
	@pkill -9 -x px4 2>/dev/null || true
	@sleep 1
	@echo "Arming commands at pxh> prompt:"
	@echo "  param set COM_ARM_WO_GPS 1 && param set SYS_HAS_MAG 0"
	@echo "  param set COM_RC_IN_MODE 1 && param set NAV_RCL_ACT 0"
	@echo "  param set NAV_DLL_ACT 0   && param set COM_RCL_EXCEPT 4"
	@echo "  param save && commander takeoff"
	@echo ""
	@cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_x500_lidar_front

# ------------------------------------------------------------------------------
# UGV - differential rover with frontal lidar (headless, default rover world)
# ------------------------------------------------------------------------------
px4-run-ugv:
	@echo "=========================================="
	@echo "Launching PX4 SITL - UGV (headless)"
	@echo "=========================================="
	$(CHECK_PX4)
	$(CHECK_UGV)
	@pkill -9 -x px4 2>/dev/null || true
	@sleep 1
	@cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_r1_rover

# ------------------------------------------------------------------------------
# UAV with Gazebo GUI - default empty world
# ------------------------------------------------------------------------------
px4-gui-uav:
	@echo "=========================================="
	@echo "Launching PX4 SITL + Gazebo GUI - UAV"
	@echo "=========================================="
	$(CHECK_PX4)
	$(GZ_KILL)
	@echo "Starting Gazebo..."
	@echo ""
	@cd $(PX4_DIR) && \
		__NV_PRIME_RENDER_OFFLOAD=1 \
		__GLX_VENDOR_LIBRARY_NAME=nvidia \
		MESA_GL_VERSION_OVERRIDE=4.5 \
		GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) \
		make px4_sitl gz_x500_lidar_front

# ------------------------------------------------------------------------------
# UAV with Gazebo GUI - urban scenario (R1 from paper)
# Uses src/guarded_swarms_gz/worlds/urban_uav.sdf
# ------------------------------------------------------------------------------
px4-gui-uav-urban:
	@echo "=========================================="
	@echo "Launching PX4 SITL + Gazebo GUI - UAV Urban (R1)"
	@echo "=========================================="
	$(CHECK_PX4)
	$(GZ_KILL)
	@echo "World: urban_uav (buildings + obstacle pillar)"
	@echo ""
	@# SIMULATION ONLY: auto-arms after PX4 starts via expect script.
	@# Comment out the next 'expect' block when using real hardware.
	@expect -c ' \
		set timeout 60; \
		spawn bash -c "cd $(PX4_DIR) && __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia MESA_GL_VERSION_OVERRIDE=4.5 PX4_GZ_WORLD=urban_uav GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) make px4_sitl gz_x500_lidar_front"; \
		expect "pxh>"; \
		send "param set COM_ARM_WO_GPS 1\r"; \
		expect "pxh>"; \
		send "param set SYS_HAS_MAG 0\r"; \
		expect "pxh>"; \
		send "param set COM_RC_IN_MODE 1\r"; \
		expect "pxh>"; \
		send "param set NAV_RCL_ACT 0\r"; \
		expect "pxh>"; \
		send "param set NAV_DLL_ACT 0\r"; \
		expect "pxh>"; \
		send "param set COM_RCL_EXCEPT 4\r"; \
		expect "pxh>"; \
		send "param save\r"; \
		expect "pxh>"; \
		send "commander takeoff\r"; \
		wait \
	' &


# ------------------------------------------------------------------------------
# UGV with Gazebo GUI - default rover world
# ------------------------------------------------------------------------------
px4-gui-ugv:
	@echo "=========================================="
	@echo "Launching PX4 SITL + Gazebo GUI - UGV"
	@echo "=========================================="
	$(CHECK_PX4)
	$(CHECK_UGV)
	$(GZ_KILL)
	@echo "Starting Gazebo..."
	@echo ""
	@cd $(PX4_DIR) && \
		__NV_PRIME_RENDER_OFFLOAD=1 \
		__GLX_VENDOR_LIBRARY_NAME=nvidia \
		MESA_GL_VERSION_OVERRIDE=4.5 \
		make px4_sitl gz_r1_rover 


# ------------------------------------------------------------------------------
# UGV with Gazebo GUI - urban scenario (R2 from paper)
# Uses src/guarded_swarms_gz/worlds/urban_ugv.sdf
# ------------------------------------------------------------------------------
px4-gui-ugv-urban:
	@echo "=========================================="
	@echo "Launching PX4 SITL + Gazebo GUI - UGV Urban (R2)"
	@echo "=========================================="
	$(CHECK_PX4)
	$(CHECK_UGV)
	$(GZ_KILL)
	@echo "World: urban_ugv (street corridor + abandoned vehicle)"
	@echo ""
	@cd $(PX4_DIR) && \
		__NV_PRIME_RENDER_OFFLOAD=1 \
		__GLX_VENDOR_LIBRARY_NAME=nvidia \
		MESA_GL_VERSION_OVERRIDE=4.5 \
		PX4_GZ_WORLD=urban_ugv \
		GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) \
		make px4_sitl gz_r1_rover


# ------------------------------------------------------------------------------
# Setup: copy Guarded Swarms world files into PX4 worlds directory (run once)
# ------------------------------------------------------------------------------
setup-worlds:
	@echo "=========================================="
	@echo "Installing Guarded Swarms World Files"
	@echo "=========================================="
	@echo ""
	$(CHECK_PX4)
	@echo "[1/1] Copying world files to PX4..."
	@cp $(GS_WORLDS_DIR)/urban_uav.sdf $(PX4_DIR)/Tools/simulation/gz/worlds/
	@cp $(GS_WORLDS_DIR)/urban_ugv.sdf $(PX4_DIR)/Tools/simulation/gz/worlds/
	@echo "      Done."
	@echo ""
	@echo "Worlds installed:"
	@echo "  urban_uav.sdf -> UAV urban scenario (R1)"
	@echo "  urban_ugv.sdf -> UGV urban scenario (R2)"
	@echo ""

# ------------------------------------------------------------------------------
# Setup: install Guarded Swarms rover assets into PX4 (run once)
# ------------------------------------------------------------------------------
setup-ugv:
	@echo "=========================================="
	@echo "Installing Guarded Swarms Rover Assets"
	@echo "=========================================="
	@echo ""
	$(CHECK_PX4)
	@echo "[1/2] Installing r1_rover model with frontal lidar..."
	@echo "      (overwrites PX4's stock r1_rover model.sdf with our"
	@echo "       lidar-equipped version; airframe 4009 stays unchanged)"
	@cp $(GS_MODELS_DIR)/r1_rover/model.sdf \
		$(PX4_DIR)/Tools/simulation/gz/models/r1_rover/model.sdf
	@echo "      Done."
	@echo ""
	@echo "[2/2] Rebuilding PX4 SITL..."
	@cd $(PX4_DIR) && make px4_sitl_default 2>&1 | tail -3
	@echo ""
	@echo "Rover setup complete. Run 'make px4-gui-ugv' or 'make px4-gui-ugv-urban'."
	@echo ""

# ------------------------------------------------------------------------------
# Misc
# ------------------------------------------------------------------------------
px4-kill:
	@echo "Killing all PX4 and Gazebo processes..."
	@pkill -9 -x px4 2>/dev/null || true
	@pkill -9 -x gz 2>/dev/null || true
	@pkill -9 -f "px4-gz_bridge" 2>/dev/null || true
	@pkill -9 -f "gz_sim_server" 2>/dev/null || true
	@pkill -9 gzserver 2>/dev/null || true
	@pkill -9 gzclient 2>/dev/null || true
	@pkill -9 MicroXRCEAgent 2>/dev/null || true
	@find $(PX4_DIR)/build/px4_sitl_default -name 'parameters*.bson' -delete 2>/dev/null || true
	@find $(PX4_DIR)/build/px4_sitl_default -name 'dataman' -delete 2>/dev/null || true
	@rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true
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
	@echo "Launching Gazebo standalone with empty world..."
	@GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) gz sim empty.sdf
 
gazebo-worlds:
	@echo "PX4 built-in worlds:"
	@ls -1 $(PX4_DIR)/Tools/simulation/gz/worlds/ 2>/dev/null || echo "  PX4 not found."
	@echo ""
	@echo "Guarded Swarms worlds:"
	@ls -1 $(GS_WORLDS_DIR)/ 2>/dev/null || echo "  guarded_swarms_gz not found."
	@echo ""