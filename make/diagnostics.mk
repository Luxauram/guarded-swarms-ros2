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
	@echo "  Mock demo:  make demo-pipeline"
	@echo "  UAV demo:   make demo-px4-uav  (see instructions)"
	@echo "  UGV demo:   make setup-ugv then make demo-px4-rover"
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
	@bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PARALLEL) --packages-select guarded_swarms_coordinator guarded_swarms_safety guarded_swarms_control"
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
		echo "PX4-Autopilot already exists at $(PX4_DIR). Skipping clone."; \
		echo ""; \
	else \
		echo "Cloning PX4-Autopilot..."; \
		cd $(HOME) && git clone https://github.com/PX4/PX4-Autopilot.git --recursive --depth 1; \
		echo "Repository cloned."; \
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
	@bash -c "source /opt/ros/jazzy/setup.bash && ros2 --version 2>/dev/null || echo 'ROS 2 not found'"
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
	@if [ -f "$(PX4_DIR)/ROMFS/px4fmu_common/init.d-posix/airframes/50001_gz_rover_differential_lidar" ]; then \
		echo "  Installed OK"; \
	else \
		echo "  Not installed - run make setup-ugv"; \
	fi
	@echo ""
	@echo "[5] Gazebo:"
	@gz sim --version 2>&1 | head -1 || echo "  Gazebo not installed"
	@echo ""
	@echo "[6] MicroXRCEAgent:"
	@which MicroXRCEAgent >/dev/null 2>&1 && echo "  Installed" || echo "  Not found"
	@echo ""
	@echo "[7] GPU:"
	@nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sed 's/^/  /' || echo "  No NVIDIA GPU"
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
	@echo "Shutting down all processes..."
	@pkill -9 -x px4 2>/dev/null || true
	@pkill -9 gzserver 2>/dev/null || true
	@pkill -9 gzclient 2>/dev/null || true
	@pkill -9 MicroXRCEAgent 2>/dev/null || true
	@pkill -9 -f 'ros2' 2>/dev/null || true
	@pkill -9 -f 'uvicorn.*app:app' 2>/dev/null || true
	@rm -rf /tmp/.gazebo* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true
	@echo "All processes terminated."