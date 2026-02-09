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
# Guarded Swarms - Build Automation
# Professional Makefile for ROS 2 + PX4 SITL development environment
# ==============================================================================

.PHONY: help \
        setup-all setup-docker setup-workspace setup-px4 display-guide diagnose\
        docker-start docker-stop docker-restart docker-shell docker-logs \
        docker-status docker-clean \
        ros2-build-ws ros2-clean-ws ros2-rebuild-ws ros2-test-topics \
        ros2-graph ros2-agent ros2-node \
        px4-run px4-kill px4-console px4-gui \
        gazebo-test gazebo-worlds

.DEFAULT_GOAL := help

# ==============================================================================
# Help & Documentation
# ==============================================================================

help:
	@echo ""
	@echo "Guarded Swarms - Available Commands"
	@echo "===================================="
	@echo ""
	@echo "===================================="
	@echo "  REQUIREMENTS"
	@echo "===================================="
	@echo ""
	@echo "    1. Docker installed and running"
	@echo "    2. X Server for GUI support:"
	@echo "        - Windows: VcXsrv (https://sourceforge.net/projects/vcxsrv/)"
	@echo "        - Linux:   Run 'xhost +local:docker' before using GUI"
	@echo "        - macOS:   XQuartz (https://www.xquartz.org/)"
	@echo ""
	@echo "===================================="
	@echo "  INITIAL SETUP"
	@echo "===================================="
	@echo ""
	@echo "  Option A (automated):"
	@echo "    make setup-all            Run complete setup automatically"
	@echo ""
	@echo "  Option B (manual steps):"
	@echo "    make setup-docker         1. Build Docker environment"
	@echo "    make setup-workspace      2. Build ROS 2 packages"
	@echo "    make setup-px4            3. Clone and build PX4-Autopilot"
	@echo ""
	@echo "===================================="
	@echo "  SYSTEM CONTROL"
	@echo "===================================="
	@echo ""
	@echo "    make display-guide        Display X server configuration guide"
	@echo "    make diagnose             Run full system diagnostic check"
	@echo "    make kill-all             Terminate all processes and stop container"
	@echo ""
	@echo "===================================="
	@echo "  DOCKER MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make docker-start         Start development container"
	@echo "    make docker-stop          Stop container"
	@echo "    make docker-restart       Restart container"
	@echo "    make docker-shell         Open interactive shell inside container"
	@echo "    make docker-logs          View container logs"
	@echo "    make docker-status        Show container status"
	@echo "    make docker-clean         Remove container and volumes (destructive)"
	@echo ""
	@echo "===================================="
	@echo "  ROS 2 MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make ros2-build-ws        Rebuild ROS 2 workspace after code changes"
	@echo "    make ros2-clean-ws        Remove build artifacts"
	@echo "    make ros2-rebuild-ws      Clean and rebuild workspace"
	@echo "    make ros2-test-topics     Verify ROS 2 topics from PX4"
	@echo "    make ros2-graph           Show ROS 2 node/topic graph (requires X)"
	@echo "    make ros2-agent           Launch micro-ROS bridge"
	@echo "    make ros2-node            Launch offboard control node"
	@echo ""
	@echo "===================================="
	@echo "  PX4 MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make px4-run              Launch PX4 SITL simulator"
	@echo "    make px4-gui              Launch PX4 with Gazebo 3D interface"
	@echo "    make px4-console          Open PX4 interactive console"
	@echo "    make px4-kill             Kill all PX4 and Gazebo processes"
	@echo ""
	@echo "===================================="
	@echo "  GAZEBO MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make gazebo-test          Test Gazebo installation with empty world"
	@echo "    make gazebo-worlds        List available Gazebo worlds"
	@echo ""
	@echo "===================================="
	@echo "  RUNTIME WORKFLOW"
	@echo "===================================="
	@echo ""
	@echo "  To run the complete system, open 3 separate terminals:"
	@echo ""
	@echo "    Terminal 1:  make ros2-agent       (micro-ROS bridge)"
	@echo "    Terminal 2:  make px4-run          (PX4 SITL simulator)"
	@echo "    Terminal 3:  make ros2-node        (offboard control node)"
	@echo ""
	@echo "  After launching, the drone will:"
	@echo "    1. Wait 5 seconds for initialization"
	@echo "    2. Enable offboard mode"
	@echo "    3. Arm and takeoff to 5 meters altitude"
	@echo "    4. Hover at target position"
	@echo ""
	@echo "===================================="
	@echo ""
	@echo "For detailed documentation, see README.md"
	@echo ""

# ==============================================================================
# Initial Setup
# ==============================================================================

setup-all: setup-docker setup-workspace setup-px4
	@echo ""
	@echo "=========================================="
	@echo "Setup Complete"
	@echo "=========================================="
	@echo ""
	@echo "System is ready. To run the demo:"
	@echo ""
	@echo "  1. Terminal 1: make ros2-agent"
	@echo "  2. Terminal 2: make px4-run"
	@echo "  3. Terminal 3: make ros2-node"
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
	@cd docker && docker-compose build
	@echo ""
	@echo "Starting container..."
	@cd docker && docker-compose up -d
	@sleep 2
	@echo ""
	@echo "Docker environment ready."
	@echo ""

setup-workspace:
	@echo "=========================================="
	@echo "Building ROS 2 Workspace"
	@echo "=========================================="
	@echo ""
	@echo "Checking workspace structure on host..."
	@if [ ! -d "src" ]; then \
		echo "Error: src/ directory not found in project root!"; \
		echo ""; \
		echo "Please create your ROS 2 workspace structure:"; \
		echo "  mkdir -p src/guarded_swarms_control/src"; \
		echo ""; \
		exit 1; \
	fi
	@echo "Host workspace structure verified."
	@echo ""
	@echo "Verifying container mount..."
	@sleep 2
	@docker exec guarded_swarms bash -c "ls -la /workspace/src" > /dev/null 2>&1 || \
		(echo "Error: /workspace/src not accessible in container!" && exit 1)
	@echo "Container mount verified."
	@echo ""
	@echo "Building packages..."
	@docker exec guarded_swarms bash -c "source /opt/ros/humble/setup.bash && cd /workspace && colcon build --symlink-install"
	@echo ""
	@echo "Workspace built successfully."
	@echo ""

setup-px4:
	@echo "=========================================="
	@echo "Setting Up PX4-Autopilot"
	@echo "=========================================="
	@echo ""
	@echo "Stopping any running PX4 instances..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 || true"
	@docker exec guarded_swarms bash -c "pkill -9 gz || true"
	@sleep 2
	@if docker exec guarded_swarms bash -c "test -d /workspace/PX4-Autopilot"; then \
		echo "PX4-Autopilot directory exists. Skipping clone."; \
		echo ""; \
	else \
		echo "Step 1/3: Cloning PX4-Autopilot (latest main branch)..."; \
		docker exec guarded_swarms bash -c "cd /workspace && git clone https://github.com/PX4/PX4-Autopilot.git --recursive"; \
		echo "Repository cloned."; \
		echo ""; \
	fi
	@echo "Step 2/3: Installing dependencies..."
	@docker exec guarded_swarms bash -c "cd /workspace/PX4-Autopilot && bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools" > /dev/null 2>&1 || true
	@echo "Dependencies installed."
	@echo ""
	@echo "Step 3/3: Building PX4 SITL (this will take some time)..."
	@docker exec guarded_swarms bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"
	@echo ""
	@echo "PX4 setup complete."
	@echo ""

# ==============================================================================
# System Control
# ==============================================================================

display-guide:
	@echo "=========================================="
	@echo "X Server Display Configuration"
	@echo "=========================================="
	@echo ""
	@echo "Default configuration: host.docker.internal:0.0 (Windows/Docker Desktop)"
	@echo ""
	@echo "Platform-specific requirements:"
	@echo ""
	@echo "[Windows + Docker Desktop]"
	@echo "  1. Install VcXsrv: https://sourceforge.net/projects/vcxsrv/"
	@echo "  2. Launch XLaunch with the following settings:"
	@echo "     - Display number: 0"
	@echo "     - Start no client"
	@echo "     - Disable access control: ENABLED"
	@echo "  3. Default DISPLAY value is pre-configured"
	@echo ""
	@echo "[Linux]"
	@echo "  1. Grant Docker access to X server:"
	@echo "     $$ xhost +local:docker"
	@echo "  2. Override DISPLAY before starting container:"
	@echo "     $$ export DISPLAY=:0"
	@echo "     $$ make docker-start"
	@echo ""
	@echo "[macOS]"
	@echo "  1. Install XQuartz: https://www.xquartz.org/"
	@echo "  2. Enable network clients in XQuartz preferences (Security tab)"
	@echo "  3. Override DISPLAY before starting container:"
	@echo "     $$ export DISPLAY=\$$(ipconfig getifaddr en0):0"
	@echo "     $$ xhost + \$$(ipconfig getifaddr en0)"
	@echo "     $$ make docker-start"
	@echo ""
	@echo "Current configuration:"
	@docker exec guarded_swarms printenv DISPLAY 2>/dev/null || echo "  Container not running - unable to check"
	@echo ""
	@echo "=========================================="

diagnose:
	@echo "=========================================="
	@echo "System Diagnostic"
	@echo "=========================================="
	@echo ""
	@echo "[1] Container Status:"
	@docker ps -a | grep guarded_swarms || echo "Container not found"
	@echo ""
	@echo "[2] Display Configuration:"
	@if docker exec guarded_swarms printenv DISPLAY 2>/dev/null; then \
		echo "DISPLAY variable set"; \
	else \
		echo "DISPLAY not set"; \
	fi
	@echo ""
	@echo "[3] ROS 2 Workspace:"
	@docker exec guarded_swarms bash -c '\
		if [ -d /workspace/src ]; then \
			echo "Source directory exists"; \
			if [ -d /workspace/install ]; then \
				echo "Workspace built successfully"; \
			else \
				echo "Workspace not yet built - run make ros2-build-ws"; \
			fi; \
		else \
			echo "Source directory missing - check volume mount"; \
		fi'
	@echo ""
	@echo "[4] PX4-Autopilot:"
	@docker exec guarded_swarms bash -c '\
		if [ -d /workspace/PX4-Autopilot ]; then \
			echo "PX4 directory exists"; \
			if [ -f /workspace/PX4-Autopilot/build/px4_sitl_default/bin/px4 ]; then \
				echo "PX4 built successfully"; \
			else \
				echo "PX4 not built - run make setup-px4"; \
			fi; \
		else \
			echo "PX4 not cloned - run make setup-px4"; \
		fi'
	@echo ""
	@echo "[5] Gazebo:"
	@docker exec guarded_swarms bash -c "gz sim --version 2>&1 | head -1" || echo "Gazebo not installed"
	@echo ""
	@echo "[6] Running Processes:"
	@docker exec guarded_swarms bash -c "pgrep -a px4 || echo '  No PX4 processes running'"
	@docker exec guarded_swarms bash -c "pgrep -a gz || echo '  No Gazebo processes running'"
	@docker exec guarded_swarms bash -c "pgrep -a MicroXRCE || echo '  No micro-ROS agent running'"
	@echo ""
	@echo "=========================================="

kill-all:
	@echo "=========================================="
	@echo "Shutting Down All Processes"
	@echo "=========================================="
	@echo ""
	@echo "Stopping all running processes..."
	@echo ""
	@echo "[1/3] Terminating PX4 SITL processes..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 || true" 2>/dev/null || true
	@echo "[2/3] Terminating Gazebo processes..."
	@docker exec guarded_swarms bash -c "pkill -9 gz || true" 2>/dev/null || true
	@echo "[3/3] Terminating micro-ROS agent..."
	@docker exec guarded_swarms bash -c "pkill -9 MicroXRCEAgent || true" 2>/dev/null || true
	@sleep 1
	@echo ""
	@echo "Stopping Docker container..."
	@cd docker && docker-compose down 2>/dev/null || true
	@echo ""
	@echo "=========================================="
	@echo "Shutdown Complete"
	@echo "=========================================="
	@echo ""
	@echo "All processes terminated and container stopped."
	@echo "To restart: make docker-start"
	@echo ""

# ==============================================================================
# Docker Management
# ==============================================================================

docker-start:
	@echo "Starting container..."
	@cd docker && docker-compose up -d
	@sleep 1
	@echo "Container started. Use 'make docker-shell' to access shell."

docker-stop:
	@echo "Stopping container..."
	@cd docker && docker-compose down
	@echo "Container stopped."

docker-restart: docker-stop docker-start

docker-shell:
	@echo "Opening interactive shell in container."
	@echo "Type 'exit' to return to host."
	@echo ""
	@docker exec -it guarded_swarms bash

docker-logs:
	@cd docker && docker-compose logs --tail=100

docker-status:
	@echo "Container status:"
	@echo ""
	@docker ps -a | grep guarded_swarms || echo "Container not found."

docker-clean:
	@echo "=========================================="
	@echo "WARNING: Destructive Operation"
	@echo "=========================================="
	@echo ""
	@echo "This will remove the container and all Docker volumes."
	@echo "Source code and PX4-Autopilot will NOT be deleted."
	@echo ""
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@echo ""
	@cd docker && docker-compose down -v
	@echo "Cleanup complete."

# ==============================================================================
# ROS 2 Management
# ==============================================================================

ros2-build-ws:
	@echo "Rebuilding ROS 2 workspace..."
	@docker exec -it guarded_swarms bash -c "source /opt/ros/humble/setup.bash && cd /workspace && colcon build --symlink-install"
	@echo "Build complete."

ros2-clean-ws:
	@echo "Cleaning workspace build artifacts..."
	@docker exec guarded_swarms bash -c "cd /workspace && rm -rf build/ install/ log/ 2>/dev/null || true"
	@echo "Workspace cleaned."

ros2-rebuild-ws: ros2-clean-ws ros2-build-ws

ros2-test-topics:
	@echo "Verifying ROS 2 topics from PX4..."
	@echo ""
	@echo "Prerequisites: ros2-agent and px4-run must be running."
	@echo ""
	@docker exec -it guarded_swarms bash -c "source /workspace/install/setup.bash && ros2 topic list | grep fmu || echo 'No PX4 topics found. Ensure agent and SITL are running.'"

ros2-graph:
	@echo "=========================================="
	@echo "ROS 2 Graph Visualization"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/install"; then \
		echo "Error: ROS 2 workspace not built."; \
		echo "Run 'make ros2-build-ws' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Prerequisites:"
	@echo "  - X server must be running"
	@echo "  - System should be running (agent, px4-run, node)"
	@echo ""
	@echo "Opening rqt_graph window..."
	@docker exec -it guarded_swarms bash -c "source /workspace/install/setup.bash && rqt_graph"

ros2-agent:
	@echo "=========================================="
	@echo "Launching micro-ROS Agent"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms which MicroXRCEAgent > /dev/null 2>&1; then \
		echo "Error: MicroXRCEAgent not found."; \
		echo "Run 'make setup-docker' to build the environment."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Bridge listening on UDP port 8888."
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms MicroXRCEAgent udp4 -p 8888

ros2-node:
	@echo "=========================================="
	@echo "Launching Offboard Control Node"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/install/guarded_swarms_control"; then \
		echo "Error: guarded_swarms_control package not built."; \
		echo "Run 'make ros2-build-ws' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Prerequisites: Ensure micro-ROS agent and PX4 SITL are running."
	@echo "  Terminal 1: make ros2-agent"
	@echo "  Terminal 2: make px4-run"
	@echo ""
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "source /workspace/install/setup.bash && ros2 run guarded_swarms_control offboard_control_node"

# ==============================================================================
# PX4 Management
# ==============================================================================

px4-run:
	@echo "=========================================="
	@echo "Launching PX4 SITL"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/PX4-Autopilot"; then \
		echo "Error: PX4-Autopilot not found."; \
		echo "Run 'make setup-px4' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Stopping any existing PX4 instances..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 || true"
	@sleep 1
	@echo "Starting Gazebo simulation (headless mode)."
	@echo "Keep this terminal open."
	@echo ""
	@echo "For manual arming at pxh> prompt:"
	@echo "  commander arm -f"
	@echo "  commander mode offboard"
	@echo ""
	@docker exec -it guarded_swarms bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"

px4-gui:
	@echo "=========================================="
	@echo "Launching PX4 SITL with Gazebo GUI"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/PX4-Autopilot"; then \
		echo "Error: PX4-Autopilot not found."; \
		echo "Run 'make setup-px4' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Stopping any existing PX4 instances..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 || true"
	@docker exec guarded_swarms bash -c "pkill -9 gz || true"
	@sleep 2
	@echo "Prerequisites:"
	@echo "  - X server must be running"
	@echo "  - Windows: VcXsrv with 'Disable access control' enabled"
	@echo "  - Linux: Run 'xhost +local:docker'"
	@echo ""
	@echo "Starting Gazebo with 3D visualization..."
	@echo "Gazebo window will open on your desktop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "cd /workspace/PX4-Autopilot && make px4_sitl gz_x500"

px4-console:
	@echo "Opening PX4 interactive console..."
	@echo ""
	@if ! docker exec guarded_swarms test -d /workspace/PX4-Autopilot; then \
		echo "Error: PX4-Autopilot not found."; \
		echo "Run 'make setup-px4' first."; \
		echo ""; \
		exit 1; \
	fi
	@docker exec -it guarded_swarms bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"

px4-kill:
	@echo "Killing all PX4 and Gazebo processes..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 || true"
	@docker exec guarded_swarms bash -c "pkill -9 gz || true"
	@docker exec guarded_swarms bash -c "pkill -9 MicroXRCEAgent || true"
	@echo "All processes stopped."

# ==============================================================================
# Gazebo Management
# ==============================================================================

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
	@docker exec -it guarded_swarms bash -c "gz sim worlds/empty.sdf"

gazebo-worlds:
	@echo "Available Gazebo worlds:"
	@echo ""
	@docker exec guarded_swarms bash -c "ls -1 /workspace/PX4-Autopilot/Tools/simulation/gz/worlds/ 2>/dev/null || echo 'PX4-Autopilot not found. Run make setup-px4 first.'"
	@echo ""
	@echo "To launch a specific world:"
	@echo "  make docker-shell"
	@echo "  gz sim /workspace/PX4-Autopilot/Tools/simulation/gz/worlds/<world_name>.sdf"
