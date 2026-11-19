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

.PHONY: px4-kill setup-ugv gazebo-test gazebo-worlds \
        gen-coastal check-coastal \
        demo-coastal demo-coordination

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
	@if ! grep -q "lidar_sensor_link" "$(GS_GZ_MODELS_DIR)/r1_rover/model.sdf" 2>/dev/null; then \
		echo "ERROR: $(GS_GZ_MODELS_DIR)/r1_rover/model.sdf missing or has no lidar."; \
		exit 1; \
	fi
endef

# ------------------------------------------------------------------------------
# Shared Gazebo kill block (used by demo-coastal)
# Kills all Gazebo Harmonic processes cleanly before launching a new world.
# ------------------------------------------------------------------------------
define GZ_KILL
	@bash $(REPO_ROOT)/scripts/sim/gz_kill.sh
endef

# ------------------------------------------------------------------------------
# Coastal surveillance demo - 2 UAV + 1 UGV (IET paper 5.1)
#
# One Gazebo server: scripts/sim/gz_launch.sh starts the world once, and every
# PX4 instance attaches to it with PX4_GZ_STANDALONE=1. Instance N gets
# MAV_SYS_ID N+1 and the /px4_N topic namespace; instance 0 stays at the root.
# PX4_GZ_NO_FOLLOW=1 keeps PX4 from putting the GUI camera in follow mode on
# the vehicle it spawns: follow mode disables orbit and pan, which with more
# than one vehicle makes the view unusable.
#
# The rover needs no parameter tweaks: PX4 defaults are correct for it.
# In particular do NOT set SYS_HAS_MAG 0 (that is a UAV-only workaround) —
# without a magnetometer the rover EKF never converges, local_position stays
# invalid, and the vehicle is disarmed by failsafe right after arming.
# ------------------------------------------------------------------------------
demo-coastal:
	@echo "=========================================="
	@echo "Coastal Surveillance Demo - 2 UAV + 1 UGV"
	@echo "=========================================="
	$(CHECK_PX4)
	$(CHECK_UGV)
	$(GZ_KILL)
	@echo "Clearing instance state for a reproducible start..."
	@rm -rf $(PX4_DIR)/build/px4_sitl_default/rootfs/1
	@rm -rf $(PX4_DIR)/build/px4_sitl_default/rootfs/2
	@echo "[1/6] Gazebo world: $(COASTAL_WORLD)"
	@xterm -title "Gazebo - $(COASTAL_WORLD)" -geometry 100x20 \
		-e bash -c '$(GZ_LAUNCH) $(COASTAL_WORLD); bash' &
	@sleep $(GZ_BOOT_WAIT)
	@echo "[2/6] uXRCE-DDS agents, one UDP port per instance"
	@xterm -title "DDS agent :8888" -geometry 90x14 \
		-e bash -c 'MicroXRCEAgent udp4 -p 8888; bash' &
	@xterm -title "DDS agent :8889" -geometry 90x14 \
		-e bash -c 'MicroXRCEAgent udp4 -p 8889; bash' &
	@xterm -title "DDS agent :8890" -geometry 90x14 \
		-e bash -c 'MicroXRCEAgent udp4 -p 8890; bash' &
	@sleep 3
	@echo "[3/6] UAV 0 - instance 0 (MAV_SYS_ID 1) at $(UAV0_POSE)"
	@xterm -title "PX4 UAV0 - instance 0" -geometry 120x30 -e bash -c ' \
		cd $(PX4_DIR) && \
		PX4_GZ_STANDALONE=1 \
		PX4_GZ_NO_FOLLOW=1 \
		PX4_GZ_WORLD=$(COASTAL_WORLD) \
		PX4_GZ_MODEL_POSE=$(UAV0_POSE) \
		GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) \
		make px4_sitl gz_x500_lidar_front 2>&1 | tee /tmp/px4_0.log; bash' &
	@sleep $(UAV_BOOT_WAIT)
	@bash $(REPO_ROOT)/scripts/sim/px4_configure.sh 0 uav
	@echo "[4/6] UAV 1 - instance 1 (MAV_SYS_ID 2) at $(UAV1_POSE)"
	@xterm -title "PX4 UAV1 - instance 1" -geometry 120x30 -e bash -c ' \
		cd $(PX4_DIR)/build/px4_sitl_default && \
		PX4_GZ_STANDALONE=1 \
		PX4_GZ_NO_FOLLOW=1 \
		PX4_SYS_AUTOSTART=4017 \
		PX4_SIM_MODEL=gz_x500_lidar_front \
		PX4_GZ_WORLD=$(COASTAL_WORLD) \
		PX4_GZ_MODEL_POSE=$(UAV1_POSE) \
		GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) \
		./bin/px4 -i 1 2>&1 | tee /tmp/px4_1.log; bash' &
	@sleep 12
	@bash $(REPO_ROOT)/scripts/sim/px4_configure.sh 1 uav
	@echo "[5/6] UGV - instance 2 (MAV_SYS_ID 3) at $(COASTAL_UGV_POSE)"
	@xterm -title "PX4 UGV - instance 2" -geometry 120x30 -e bash -c ' \
		cd $(PX4_DIR)/build/px4_sitl_default && \
		PX4_GZ_STANDALONE=1 \
		PX4_GZ_NO_FOLLOW=1 \
		PX4_SYS_AUTOSTART=4009 \
		PX4_SIM_MODEL=gz_r1_rover \
		PX4_GZ_WORLD=$(COASTAL_WORLD) \
		PX4_GZ_MODEL_POSE=$(COASTAL_UGV_POSE) \
		GZ_SIM_RESOURCE_PATH=$(GZ_RESOURCE_PATH) \
		./bin/px4 -i 2 2>&1 | tee /tmp/px4_2.log; bash' &
	@sleep 12
	@bash $(REPO_ROOT)/scripts/sim/px4_configure.sh 2 ugv
	@echo "[6/6] ROS 2 coastal pipeline"
	@bash -c '$(FULL_SOURCE) && ros2 daemon stop && ros2 daemon start' || true
	@bash -c '$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup coastal_pipeline.launch.py'

# ------------------------------------------------------------------------------
# Coordination + scenario layer, over an already-running demo-coastal.
#
# Second step of the coastal case study: start this in a second terminal once
# the vehicles are up, armed and holding their patrol state. Brings up the
# sensing agents, the TB-CSPN chain and the intruder. The intruder holds at its
# spawn point for start_delay_s, so sensing and TB-CSPN are ready before the
# first observation.
#
# Counterfactual runs (IET Sec 5.3) are invocations of this target:
#   make demo-coordination EO=false               # loss of the EO modality
#   RF_LABEL=LikelyCivilianTraffic make demo-coordination   # conflicting RF
# ------------------------------------------------------------------------------
demo-coordination:
	@echo "=========================================="
	@echo "Coastal Coordination + Scenario layer"
	@echo "=========================================="
	@echo "Prereq: 'make demo-coastal' already running (vehicles up)."
	@bash -c '$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup coordination.launch.py'

# ------------------------------------------------------------------------------
# Regenerate the coastal world from its generator (deterministic seed)
# ------------------------------------------------------------------------------
gen-coastal:
	@echo "Regenerating $(GS_WORLDS_DIR)/coastal.sdf ..."
	@python3 $(REPO_ROOT)/scripts/world/gen_coastal.py
	@echo "Done. Verify with: bash scripts/sim/gz_launch.sh coastal"

check-coastal:
	@bash $(REPO_ROOT)/scripts/world/check_coastal.sh

# ------------------------------------------------------------------------------
# Setup: check the Guarded Swarms rover model (r1_rover with lidar)
# ------------------------------------------------------------------------------
setup-ugv:
	@echo "=========================================="
	@echo "Guarded Swarms Rover Assets"
	@echo "=========================================="
	$(CHECK_PX4)
	$(CHECK_UGV)
	@echo "OK: r1_rover model with lidar found at"
	@echo "    $(GS_GZ_MODELS_DIR)/r1_rover/model.sdf"
	@echo "No files are copied into PX4 — resolution is via GZ_SIM_RESOURCE_PATH."

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