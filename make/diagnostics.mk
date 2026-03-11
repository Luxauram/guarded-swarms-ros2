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
# diagnostics.mk - System diagnostics and process cleanup
# ==============================================================================

.PHONY: diagnose kill-all setup-all setup-docker setup-workspace setup-px4

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------
setup-all: setup-docker setup-workspace setup-px4
	@echo ""
	@echo "=========================================="
	@echo "Setup Complete"
	@echo "=========================================="
	@echo ""
	@echo "System is ready. Quick start:"
	@echo ""
	@echo "  Terminal 1: UAV demo =>   make px4-run-uav   (then make demo-px4-uav)"
	@echo "  Terminal 2: Rover demo => make setup-rover   (once) then make px4-run-rover"
	@echo "  Terminal 3: Mock demo =>  make demo-pipeline"
	@echo ""
	@echo "Manual arming (if automatic arming fails):"
	@echo "  In terminal 2 at pxh> prompt:"
	@echo "    commander arm -f"
	@echo "    commander mode offboard"
	@echo ""

setup-docker:
	@echo "=========================================="
	@echo "Building Docker Environment"
	@echo "=========================================="
	@echo ""
	@echo "Building Docker image. This may take some time on first run."
	@echo ""
	@cd $(DOCKER_DIR) && docker-compose build
	@echo ""
	@echo "Starting container..."
	@cd $(DOCKER_DIR) && docker-compose up -d
	@sleep 2
	@echo ""
	@echo "Docker environment ready."
	@echo ""

setup-workspace:
	@echo "=========================================="
	@echo "Building ROS 2 Workspace"
	@echo "=========================================="
	@echo ""
	@echo "Initializing git submodules (px4_msgs, px4_ros_com)..."
	@git submodule update --init --recursive
	@echo "Submodules ready."
	@echo ""
	@echo "Checking workspace structure on host..."
	@if [ ! -d "src" ]; then \
		echo "Error: src/ directory not found in project root!"; \
		echo ""; \
		echo "Please create your ROS 2 workspace structure:"; \
		echo "  mkdir -p src/$(CONTROL_PKG)/src"; \
		echo ""; \
		exit 1; \
	fi
	@echo "Host workspace structure verified."
	@echo ""
	@echo "Verifying container mount..."
	@sleep 2
	@$(DOCKER_EXEC) bash -c "ls -la $(SRC_DIR)" > /dev/null 2>&1 || \
		(echo "Error: $(SRC_DIR) not accessible in container!" && exit 1)
	@echo "Container mount verified."
	@echo ""
	@echo "Cleaning previous build artifacts..."
	@$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR) && rm -rf build/* install/* log/*" 2>/dev/null || true
	@echo ""
	@echo "Building packages (this may take 5-10 minutes for px4_msgs)..."
	@$(DOCKER_EXEC) bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PARALLEL)"
	@echo ""
	@echo "Setting executable permissions on Python nodes..."
	@$(DOCKER_EXEC) bash -c "find $(INSTALL_DIR) -name '*.py' -path '*/lib/*' -exec chmod +x {} \;"
	@echo ""
	@echo "Workspace built successfully."
	@echo ""

setup-px4:
	@echo "=========================================="
	@echo "Setting Up PX4-Autopilot"
	@echo "=========================================="
	@echo ""
	@echo "Stopping any running PX4 instances..."
	@$(DOCKER_EXEC) bash -c "$(KILL_PX4)"
	@$(DOCKER_EXEC) bash -c "$(KILL_GAZEBO)"
	@sleep 2
	@if $(DOCKER_EXEC) bash -c "test -d $(PX4_DIR)"; then \
		echo "PX4-Autopilot directory exists. Skipping clone."; \
		echo ""; \
	else \
		echo "Step 1/3: Cloning PX4-Autopilot (latest main branch)..."; \
		$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR) && git clone https://github.com/PX4/PX4-Autopilot.git --recursive --depth 1"; \
		echo "Repository cloned."; \
		echo ""; \
	fi
	@echo "Step 2/3: Installing dependencies..."
	@$(DOCKER_EXEC) bash -c "cd $(PX4_DIR) && timeout 300 bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools 2>&1 | grep -v 'debconf'" || true
	@echo "Dependencies installed."
	@echo ""
	@echo "Step 3/3: Building PX4 SITL (this will take some time)..."
	@$(DOCKER_EXEC) bash -c "cd $(PX4_DIR) && HEADLESS=1 make px4_sitl gz_x500"
	@echo ""
	@echo "PX4 setup complete."
	@echo ""
	@echo "NOTE: Run 'make setup-rover' to also enable UGV simulation."
	@echo ""

# ------------------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------------------
diagnose:
	@echo "=========================================="
	@echo "System Diagnostic"
	@echo "=========================================="
	@echo ""
	@echo "[1] Container Status:"
	@docker ps -a | grep $(CONTAINER_NAME) || echo "Container not found"
	@echo ""
	@echo "[2] Display Configuration:"
	@if $(DOCKER_EXEC) printenv DISPLAY 2>/dev/null; then \
		echo "DISPLAY variable set"; \
	else \
		echo "DISPLAY not set"; \
	fi
	@echo ""
	@echo "[3] ROS 2 Workspace:"
	@$(DOCKER_EXEC) bash -c '\
		if [ -d $(SRC_DIR) ]; then \
			echo "Source directory exists"; \
			if [ -d $(INSTALL_DIR) ]; then \
				echo "Workspace built successfully"; \
			else \
				echo "Workspace not yet built - run make ros2-build-ws"; \
			fi; \
		else \
			echo "Source directory missing - check volume mount"; \
		fi'
	@echo ""
	@echo "[4] PX4-Autopilot:"
	@$(DOCKER_EXEC) bash -c '\
		if [ -d $(PX4_DIR) ]; then \
			echo "PX4 directory exists"; \
			if [ -f $(PX4_DIR)/build/px4_sitl_default/bin/px4 ]; then \
				echo "PX4 built successfully"; \
			else \
				echo "PX4 not built - run make setup-px4"; \
			fi; \
		else \
			echo "PX4 not cloned - run make setup-px4"; \
		fi'
	@echo ""
	@echo "[5] Rover assets:"
	@$(DOCKER_EXEC) bash -c '\
		if [ -f $(PX4_DIR)/ROMFS/px4fmu_common/init.d-posix/airframes/50001_gz_rover_differential_lidar ]; \
		then echo "  Installed OK"; \
		else echo "  Not installed - run make setup-rover"; fi'
	@echo ""
	@echo "[6] Gazebo:"
	@$(DOCKER_EXEC) bash -c "gz sim --version 2>&1 | head -1" || echo "Gazebo not installed"
	@echo ""
	@echo "[7] Running Processes:"
	@$(DOCKER_EXEC) bash -c "pgrep -a px4 || echo '  No PX4 processes running'"
	@$(DOCKER_EXEC) bash -c "pgrep -a gz || echo '  No Gazebo processes running'"
	@$(DOCKER_EXEC) bash -c "pgrep -a MicroXRCE || echo '  No micro-ROS agent running'"
	@echo ""
	@echo "=========================================="

# ------------------------------------------------------------------------------
# Kill all
# ------------------------------------------------------------------------------
kill-all:
	@echo "=========================================="
	@echo "Shutting Down All Processes"
	@echo "=========================================="
	@echo ""
	@echo "Stopping all running processes..."
	@echo ""
	@echo "[1/5] Terminating PX4 SITL processes..."
	@$(DOCKER_EXEC) bash -c "$(KILL_PX4)" 2>/dev/null || true
	@echo "[2/5] Terminating Gazebo processes..."
	@$(DOCKER_EXEC) bash -c "pkill -9 -f 'gz sim' 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 ruby 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 gzserver 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 gzclient 2>/dev/null || true" 2>/dev/null || true
	@echo "[3/5] Terminating micro-ROS agent..."
	@$(DOCKER_EXEC) bash -c "$(KILL_MICRO_ROS)" 2>/dev/null || true
	@echo "[4/5] Terminating ROS2 nodes..."
	@$(DOCKER_EXEC) bash -c "pkill -9 -f 'ros2' 2>/dev/null || true" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 python3 2>/dev/null || true" 2>/dev/null || true
	@echo "[5/5] Cleaning up shared memory and lock files..."
	@$(DOCKER_EXEC) bash -c "$(CLEANUP_TMP)" 2>/dev/null || true
	@sleep 2
	@echo ""
	@echo "Stopping Docker container..."
	@cd $(DOCKER_DIR) && docker-compose down 2>/dev/null || true
	@echo ""
	@echo "=========================================="
	@echo "Shutdown Complete"
	@echo "=========================================="
	@echo ""
	@echo "All processes terminated and container stopped."
	@echo "To restart: make docker-start"
	@echo ""
