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
# diagnostics.mk - System diagnostics and process cleanup (native Ubuntu)
# ==============================================================================

.PHONY: diagnose kill-all setup-all setup-workspace setup-px4 check-gpu

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------
setup-all: setup-workspace setup-px4
	@echo ""
	@echo "=========================================="
	@echo "Setup Complete"
	@echo "=========================================="
	@echo ""
	@echo "System is ready. Quick start:"
	@echo ""
	@echo "  Coastal case study:  make demo-coastal   (then ./scripts/pipeline/test_pipeline.sh)"
	@echo "  Safety board demo:   make demo-safety-board (+ make demo-safety-sensors)"
	@echo "  Health check:        make check-coastal"
	@echo ""
	@echo "  See 'make help' for the full command reference."
	@echo ""

setup-workspace:
	@echo "=========================================="
	@echo "Building ROS 2 Workspace"
	@echo "=========================================="
	@echo ""
	@echo "Initializing git submodules..."
	@git submodule update --init --recursive
	@echo "Submodules ready."
	@echo ""
	@if [ ! -d "src" ]; then \
		echo "Error: src/ directory not found in project root!"; \
		exit 1; \
	fi
	@echo "Cleaning previous build artifacts..."
	@rm -rf build/ install/ log/ 2>/dev/null || true
	@echo ""
	@echo "Building messages and px4_msgs first..."
	@bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && colcon build --packages-select guarded_swarms_msgs px4_msgs --symlink-install --event-handlers console_direct+"
	@echo ""
	@echo "Building remaining packages..."
	@bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PARALLEL) --packages-select guarded_swarms_safety guarded_swarms_control guarded_swarms_sensing guarded_swarms_tbcspn guarded_swarms_supervisor guarded_swarms_bringup"
	@echo ""
	@echo "Workspace built successfully."
	@echo ""
	@echo "Add this to your ~/.bashrc if not already present:"
	@echo "  source $(INSTALL_DIR)/setup.bash"
	@echo ""

setup-px4:
	@echo "=========================================="
	@echo "Setting Up PX4-Autopilot"
	@echo "=========================================="
	@echo ""
	@if [ -d "$(PX4_DIR)" ]; then \
		CURRENT=$$(git -C $(PX4_DIR) rev-parse HEAD 2>/dev/null || echo unknown); \
		if [ "$$CURRENT" = "$(PX4_COMMIT)" ]; then \
			echo "PX4-Autopilot already at the pinned commit. Skipping clone."; \
			echo ""; \
		else \
			echo "ERROR: PX4-Autopilot is at $$CURRENT, expected $(PX4_COMMIT)."; \
			echo "A mismatched firmware silently breaks uXRCE-DDS topic bridging:"; \
			echo "vehicles arm but never move. To fix:"; \
			echo "  cd $(PX4_DIR)"; \
			echo "  git fetch --unshallow --tags   # only if the clone is shallow"; \
			echo "  git checkout -B $(PX4_BRANCH) $(PX4_COMMIT)"; \
			echo "  git submodule update --init --recursive"; \
			echo "  make distclean && make px4_sitl_default"; \
			exit 1; \
		fi; \
	else \
		echo "Cloning PX4-Autopilot at the pinned commit..."; \
		cd $(HOME) && git clone --filter=blob:none https://github.com/PX4/PX4-Autopilot.git; \
		cd $(PX4_DIR) && git checkout -B $(PX4_BRANCH) $(PX4_COMMIT); \
		cd $(PX4_DIR) && git submodule update --init --recursive; \
		echo "Repository cloned and pinned."; \
		echo ""; \
		echo "Installing dependencies..."; \
		cd $(PX4_DIR) && bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools; \
		echo ""; \
	fi
	@echo "Building PX4 SITL (this will take some time)..."
	@cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_x500_lidar_front
	@echo ""
	@echo "PX4 setup complete."
	@echo "Run 'make setup-ugv' to also enable UGV simulation."
	@echo ""

# ------------------------------------------------------------------------------
# GPU Check
# ------------------------------------------------------------------------------
check-gpu:
	@echo "=========================================="
	@echo "GPU Acceleration Check"
	@echo "=========================================="
	@echo ""
	@if command -v nvidia-smi >/dev/null 2>&1; then \
		echo "  [OK] NVIDIA GPU detected:"; \
		nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | sed 's/^/    /'; \
		echo ""; \
		echo "  To use GPU with Gazebo, launch with:"; \
		echo "    __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia MESA_GL_VERSION_OVERRIDE=4.5 make px4-gui-uav"; \
	else \
		echo "  [NOT FOUND] No NVIDIA GPU detected."; \
		echo "  Lidar sensors in Gazebo will not publish data."; \
		echo "  Use mock sensors instead: make demo-safety-sensors"; \
	fi
	@echo ""

# ------------------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------------------
diagnose:
	@echo "=========================================="
	@echo "System Diagnostic"
	@echo "=========================================="
	@echo ""
	@echo "[1] ROS 2:"
	@if [ -f /opt/ros/humble/setup.bash ]; then \
		echo "  Humble installed at /opt/ros/humble"; \
	else \
		echo "  ROS 2 not found - run install.sh"; \
	fi
	@echo ""
	@echo "[2] ROS 2 Workspace:"
	@if [ -d "$(INSTALL_DIR)" ]; then \
		echo "  Workspace built."; \
	else \
		echo "  Workspace not built - run make setup-workspace"; \
	fi
	@echo ""
	@echo "[3] PX4-Autopilot:"
	@if [ -d "$(PX4_DIR)" ]; then \
		echo "  PX4 directory exists at $(PX4_DIR)"; \
		if [ -f "$(PX4_DIR)/build/px4_sitl_default/bin/px4" ]; then \
			echo "  PX4 built successfully"; \
		else \
			echo "  PX4 not built - run make setup-px4"; \
		fi; \
	else \
		echo "  PX4 not found - run make setup-px4"; \
	fi
	@echo ""
	@echo "[4] Rover assets:"
	@if grep -q "lidar_sensor_link" "$(GS_GZ_MODELS_DIR)/r1_rover/model.sdf" 2>/dev/null; then \
		echo "  r1_rover model with lidar found (resolved via GZ_SIM_RESOURCE_PATH)"; \
	else \
		echo "  MISSING: $(GS_GZ_MODELS_DIR)/r1_rover/model.sdf"; \
	fi
	@echo ""
	@echo "[5] Gazebo:"
	@gz sim --version 2>&1 | head -1 || echo "  Gazebo not installed"
	@echo ""
	@echo "[6] MicroXRCEAgent:"
	@which MicroXRCEAgent >/dev/null 2>&1 && echo "  Installed" || echo "  Not found"
	@echo ""
	@echo "[7] GPU:"
	@if command -v nvidia-smi >/dev/null 2>&1; then \
		nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | sed 's/^/  /'; \
	else \
		echo "  nvidia-smi not installed (install nvidia-utils if needed)"; \
	fi
	@lspci 2>/dev/null | grep -i -E 'vga|3d|display' | sed 's/^/  /' || true
	@echo ""
	@echo "[8] Running Processes:"
	@pgrep -a px4 2>/dev/null || echo "  No PX4 processes running"
	@pgrep -a gz 2>/dev/null || echo "  No Gazebo processes running"
	@pgrep -a MicroXRCE 2>/dev/null || echo "  No micro-ROS agent running"
	@echo ""
	@echo "=========================================="

# ------------------------------------------------------------------------------
# Kill all
# ------------------------------------------------------------------------------
kill-all:
	@$(WORKSPACE_DIR)/scripts/kill_all.sh