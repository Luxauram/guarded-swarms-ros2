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
# Makefile for ROS 2 + PX4 SITL development environment
# ==============================================================================

.PHONY: help show-guide \
        setup-all setup-docker setup-workspace setup-px4 diagnose kill-all \
        demo-coordinator demo-tkinter demo-web coordinator-rebuild \
        docker-start docker-stop docker-restart docker-shell docker-logs \
        docker-status docker-clean \
        ros2-build-ws ros2-clean-ws ros2-rebuild-ws ros2-test-topics \
        ros2-graph ros2-agent ros2-node \
        px4-run px4-kill px4-console px4-gui px4-config px4-reset-params \
        gazebo-test gazebo-worlds \
        web-dev web-stop web-logs web-status web-clean web-shell web-ts-build web-ts-watch

.DEFAULT_GOAL := help
WEB_BACKEND_DIR := src/web_dashboard/backend
WEB_FRONTEND_DIR := src/web_dashboard/frontend

# ==============================================================================
# Help - Command Reference
# ==============================================================================

help:
	@echo ""
	@echo "Guarded Swarms - Command Reference"
	@echo "===================================="
	@echo ""
	@echo "===================================="
	@echo "  GETTING STARTED"
	@echo "===================================="
	@echo ""
	@echo "    make show-guide           Complete usage guide and workflows"
	@echo ""
	@echo "===================================="
	@echo "  SETUP COMMANDS"
	@echo "===================================="
	@echo ""
	@echo "  Option A (automated):"
	@echo "    make setup-all            Run complete setup automatically"
	@echo ""
	@echo "  Option B (manual steps):"
	@echo "    make setup-docker         Build Docker environment"
	@echo "    make setup-workspace      Build ROS 2 packages"
	@echo "    make setup-px4            Clone and build PX4-Autopilot"
	@echo ""
	@echo "===================================="
	@echo "  DOCKER MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make docker-start         Start container"
	@echo "    make docker-stop          Stop container"
	@echo "    make docker-restart       Restart container"
	@echo "    make docker-shell         Open interactive shell inside container"
	@echo "    make docker-logs          View container logs"
	@echo "    make docker-status        Show container status"
	@echo "    make docker-clean         Remove container and volumes"
	@echo ""
	@echo "===================================="
	@echo "  ROS 2 MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make ros2-build-ws        Rebuild ROS 2 workspace"
	@echo "    make ros2-clean-ws        Remove build artifacts"
	@echo "    make ros2-rebuild-ws      Clean and rebuild workspace"
	@echo "    make ros2-test-topics     Verify ROS 2 topics from PX4"
	@echo "    make ros2-graph           Show ROS 2 node/topic graph"
	@echo "    make ros2-agent           Launch micro-ROS bridge"
	@echo "    make ros2-node            Launch offboard control node"
	@echo "    make ro2-coordinator-reb  Quick rebuild coordinator package"
	@echo ""
	@echo "===================================="
	@echo "  PX4 MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make px4-run              Launch PX4 SITL simulator"
	@echo "    make px4-gui              Launch PX4 with Gazebo GUI"
	@echo "    make px4-console          Open PX4 interactive console"
	@echo "    make px4-kill             Kill all PX4 and Gazebo processes"
	@echo "    make px4-config           Set offboard control parameters"
	@echo "    make px4-reset-params     Reset parameters to factory defaults"
	@echo ""
	@echo "===================================="
	@echo "  GAZEBO MANAGEMENT"
	@echo "===================================="
	@echo ""
	@echo "    make gazebo-test          Test Gazebo installation with empty world"
	@echo "    make gazebo-worlds        List available Gazebo worlds"
	@echo ""
	@echo "===================================="
	@echo "  WEB DASHBOARD"
	@echo "===================================="
	@echo ""
	@echo "    make web-dev              Start dashboard server (localhost:8080)"
	@echo "    make web-stop             Stop dashboard server"
	@echo "    make web-status           Check dashboard status and dependencies"
	@echo "    make web-ts-build         Compile TypeScript"
	@echo "    make web-ts-watch         Auto-compile on file changes"
	@echo "    make web-clean            Remove build artifacts"
	@echo ""
	@echo "===================================="
	@echo "  DEMO"
	@echo "===================================="
	@echo ""
	@echo "    make demo-coordinator     Launch token coordination demo"
	@echo "    make demo-tkinter         Launch Tkinter Dashboard"
	@echo "    make demo-web             Launch web dashboard"
	@echo ""
	@echo "===================================="
	@echo "  DIAGNOSTICS & CLEANUP"
	@echo "===================================="
	@echo ""
	@echo "    make diagnose             Run full system diagnostic"
	@echo "    make kill-all             Terminate all processes"
	@echo ""
	@echo "===================================="
	@echo ""
	@echo "For detailed documentation, see README.md"
	@echo ""

# ==============================================================================
# Complete User Guide
# ==============================================================================

show-guide:
	@echo ""
	@echo "======================================="
	@echo "  Guarded Swarms - Complete User Guide"
	@echo "======================================="
	@echo ""
	@echo "======================================="
	@echo "  1. REQUIREMENTS"
	@echo "======================================="
	@echo ""
	@echo "  Software Prerequisites:"
	@echo "    Docker Desktop installed and running"
	@echo ""
	@echo "  	 X Server (for GUI applications):"
	@echo "    	- Windows: VcXsrv (https://sourceforge.net/projects/vcxsrv/)"
	@echo "            Launch with 'Disable access control' enabled"
	@echo "    	- Linux: Run 'xhost +local:docker' before GUI"
	@echo "    	- macOS: XQuartz (https://www.xquartz.org/)"
	@echo ""
	@echo "======================================="
	@echo "  2. INITIAL SETUP (First Time Only)"
	@echo "======================================="
	@echo ""
	@echo "  Quick Setup:"
	@echo "    $$ make setup-all"
	@echo ""
	@echo "  This will:"
	@echo "    1. Build Docker image"
	@echo "    2. Compile ROS2 packages"
	@echo "    3. Clone and build PX4-Autopilot"
	@echo ""
	@echo "  Manual Setup (step-by-step):"
	@echo "    $$ make setup-docker       # Build environment"
	@echo "    $$ make setup-workspace    # Compile ROS2 packages"
	@echo "    $$ make setup-px4          # Setup PX4 simulator"
	@echo ""
	@echo "======================================="
	@echo "  3. AVAILABLE DEMOS & WORKFLOWS"
	@echo "======================================="
	@echo ""
	@echo "================================================================"
	@echo "    A) Token Coordination System (Multi-Agent Demo)             "
	@echo "================================================================"
	@echo ""
	@echo "  What it does:"
	@echo "    - 4 agents request spatial zones with priority levels"
	@echo "    - Coordinator validates and authorizes requests"
	@echo "    - Real-time conflict detection & resolution"
	@echo "    - Supports FCFS, Priority, and Hybrid arbitration"
	@echo ""
	@echo "  Launch the demo:"
	@echo "    $$ make demo-coordinator"
	@echo ""
	@echo "  Visualization options:"
	@echo ""
	@echo "    - Web Dashboard (Modern, Browser-based):"
	@echo "         Terminal 1: $$ make demo-coordinator"
	@echo "         Terminal 2: $$ make demo-web"
	@echo "         Browser:    http://localhost:8080"
	@echo ""
	@echo "    - Tkinter Dashboard (Desktop GUI):"
	@echo "         Terminal 1: $$ make demo-coordinator"
	@echo "         Terminal 2: $$ make demo-tkinter"
	@echo "         (Requires X server running)"
	@echo ""
	@echo "    - RQT Graph (ROS2 topology):"
	@echo "         Terminal 1: $$ make demo-coordinator"
	@echo "         Terminal 2: $$ make ros2-graph"
	@echo ""
	@echo "================================================================"
	@echo "    B) PX4 Offboard Control (Drone Flight)                      "
	@echo "================================================================"
	@echo ""
	@echo "  What it does:"
	@echo "    - Simulated X500 quadcopter in Gazebo"
	@echo "    - Offboard control via ROS2"
	@echo "    - Automatic takeoff to 5m altitude"
	@echo ""
	@echo "  Launch workflow:"
	@echo "    Terminal 1: $$ make ros2-agent     # micro-ROS bridge"
	@echo "    Terminal 2: $$ make px4-run        # PX4 SITL simulator"
	@echo "    Terminal 3: $$ make ros2-node      # Offboard control"
	@echo ""
	@echo "  With Gazebo GUI:"
	@echo "    Terminal 2: $$ make px4-gui        # 3D visualization"
	@echo ""
	@echo "======================================="
	@echo "  4. DEVELOPMENT WORKFLOW"
	@echo "======================================="
	@echo ""
	@echo "  After modifying code:"
	@echo "    $$ make coordinator-rebuild     # Quick rebuild coordinator"
	@echo "    $$ make ros2-rebuild-ws         # Full workspace rebuild"
	@echo ""
	@echo "  Web dashboard development:"
	@echo "    $$ make web-ts-watch            # Auto-compile TypeScript"
	@echo "    $$ make web-dev                 # Start server (hot reload)"
	@echo ""
	@echo "  Debugging:"
	@echo "    $$ make docker-shell            # Enter container"
	@echo "    $$ make ros2-test-topics        # Verify ROS2 communication"
	@echo "    $$ make diagnose                # Full system check"
	@echo ""
	@echo "======================================="
	@echo "  5. FILE LOCATIONS"
	@echo "======================================="
	@echo ""
	@echo "  Demos:"
	@echo "    - Coordination launch:  src/tools/launch/demo.launch.py"
	@echo "    - Tkinter dashboard:    src/tools/visualization/dashboard.py"
	@echo "    - Web dashboard:        src/web_dashboard/"
	@echo ""
	@echo "  ROS2 Packages:"
	@echo "    - Coordinator:          src/guarded_swarms_coordinator/"
	@echo "    - PX4 Control:          src/guarded_swarms_control/"
	@echo ""
	@echo "======================================="
	@echo ""
	@echo "For command reference: make help"
	@echo ""

# ==============================================================================
# Setup Commands
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
	@echo "Cleaning previous build artifacts..."
	@docker exec guarded_swarms bash -c "cd /workspace && rm -rf build/* install/* log/*" 2>/dev/null || true
	@echo ""
	@echo "Building packages (this may take 5-10 minutes for px4_msgs)..."
	docker exec guarded_swarms bash -c "source /opt/ros/humble/setup.bash && cd /workspace && colcon build --symlink-install --parallel-workers 4 --event-handlers console_direct+"
	@echo ""
	@echo "Workspace built successfully."
	@echo ""

setup-px4:
	@echo "=========================================="
	@echo "Setting Up PX4-Autopilot"
	@echo "=========================================="
	@echo ""
	@echo "Stopping any running PX4 instances..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 2>/dev/null || true"
	@docker exec guarded_swarms bash -c "pkill -9 gz 2>/dev/null || true"
	@sleep 2
	@if docker exec guarded_swarms bash -c "test -d /workspace/PX4-Autopilot"; then \
		echo "PX4-Autopilot directory exists. Skipping clone."; \
		echo ""; \
	else \
		echo "Step 1/3: Cloning PX4-Autopilot (latest main branch)..."; \
		docker exec guarded_swarms bash -c "cd /workspace && git clone https://github.com/PX4/PX4-Autopilot.git --recursive --depth 1"; \
		echo "Repository cloned."; \
		echo ""; \
	fi
	@echo "Step 2/3: Installing dependencies..."
	@docker exec guarded_swarms bash -c "cd /workspace/PX4-Autopilot && timeout 300 bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools 2>&1 | grep -v 'debconf'" || true
	@echo "Dependencies installed."
	@echo ""
	@echo "Step 3/3: Building PX4 SITL (this will take some time)..."
	@docker exec guarded_swarms bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"
	@echo ""
	@echo "PX4 setup complete."
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
	@echo "Stopping any existing micro-ROS agent..."
	@docker exec guarded_swarms bash -c "pkill -9 MicroXRCEAgent 2>/dev/null || true" 2>/dev/null || true
	@sleep 1
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
	@echo "Stopping any existing offboard control node..."
	@docker exec guarded_swarms bash -c "pkill -9 -f offboard_control_node 2>/dev/null || true" 2>/dev/null || true
	@sleep 1
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "source /workspace/install/setup.bash && ros2 run guarded_swarms_control offboard_control_node"

ro2-coordinator-reb:
	@echo "Quick rebuild: guarded_swarms_coordinator"
	@docker exec guarded_swarms bash -c "cd /workspace && rm -rf build/guarded_swarms_coordinator install/guarded_swarms_coordinator"
	@docker exec guarded_swarms bash -c "source /opt/ros/humble/setup.bash && cd /workspace && colcon build --packages-select guarded_swarms_coordinator"
	@echo "✓ Rebuild complete. Source workspace: source /workspace/install/setup.bash"

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
	@echo "Stopping any existing PX4 and Gazebo instances..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 -f 'gz sim' 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 ruby 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 gzserver 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 gzclient 2>/dev/null || true" 2>/dev/null || true
	@sleep 3
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

px4-config:
	@echo "=========================================="
	@echo "Configure PX4 for Offboard Control"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites: PX4 must be running (make px4-run or px4-gui)"
	@echo ""
	@echo "Copy-paste these commands at the pxh> prompt:"
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
	@echo "Reset PX4 Parameters to Defaults"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites: PX4 must be running (make px4-run or px4-gui)"
	@echo ""
	@echo "Copy-paste these commands at the pxh> prompt:"
	@echo ""
	@echo "param set COM_ARM_WO_GPS 0"
	@echo "param set SYS_HAS_MAG 1"
	@echo "param set COM_RC_IN_MODE 4"
	@echo "param set NAV_RCL_ACT 2"
	@echo "param set NAV_DLL_ACT 2"
	@echo "param set COM_RCL_EXCEPT 0"
	@echo "param save"
	@echo ""

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

# ==============================================================================
# Web Dashboard Management (Development Only)
# ==============================================================================

web-dev:
	@echo "=========================================="
	@echo "Starting Web Dashboard"
	@echo "=========================================="
	@echo ""
	@echo "Dashboard available at:"
	@echo "  http://localhost:8080"
	@echo ""
	@echo "Features:"
	@echo "  - Real-time token visualization"
	@echo "  - Live statistics and metrics"
	@echo "  - Agent performance monitoring"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - ROS2 workspace must be built (make ros2-build-ws)"
	@echo "  - TypeScript must be compiled (make web-ts-build)"
	@echo ""
	@echo "Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "source /opt/ros/humble/setup.bash && source /workspace/install/setup.bash && cd /workspace/$(WEB_BACKEND_DIR) && python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload"

web-stop:
	@echo "Stopping web dashboard..."
	@docker exec guarded_swarms bash -c "pkill -9 -f 'uvicorn.*app:app'" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 -f 'python3.*uvicorn'" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "fuser -k 8080/tcp" 2>/dev/null || true
	@sleep 1
	@echo "Dashboard stopped."

web-status:
	@echo "=========================================="
	@echo "Web Dashboard Status"
	@echo "=========================================="
	@echo ""
	@echo "[Backend Process]"
	@docker exec guarded_swarms bash -c "ps aux | grep -E 'uvicorn.*app:app' | grep -v grep || echo 'Not running'"
	@echo ""
	@echo "[Port 8080 Check]"
	@docker exec guarded_swarms bash -c "python3 -c \"import socket; s=socket.socket(); s.settimeout(0.5); result=s.connect_ex(('127.0.0.1',8080)); s.close(); print('Port 8080 is open' if result==0 else 'Port 8080 is not accessible')\" 2>/dev/null"
	@echo ""
	@echo "[Runtime Versions]"
	@docker exec guarded_swarms bash -c "python3 --version | sed 's/^/  Python: /'"
	@docker exec guarded_swarms bash -c "bun --version | sed 's/^/  Bun: /'"
	@docker exec guarded_swarms bash -c "tsc --version 2>/dev/null | sed 's/^/  TypeScript: /' || echo '  TypeScript: Not found'"
	@echo ""
	@echo "[ROS2 Environment]"
	@docker exec guarded_swarms bash -c "source /opt/ros/humble/setup.bash && python3 -c 'import rclpy; print(\"rclpy: Available\")' 2>/dev/null || echo 'rclpy: Not available'"
	@docker exec guarded_swarms bash -c "source /opt/ros/humble/setup.bash && source /workspace/install/setup.bash && python3 -c 'import guarded_swarms_coordinator.msg; print(\"guarded_swarms_coordinator: Available\")' 2>/dev/null || echo 'guarded_swarms_coordinator: Not built (run make ros2-build-ws)'"
	@echo ""
	@echo "[TypeScript Build]"
	@docker exec guarded_swarms bash -c "test -d /workspace/$(WEB_FRONTEND_DIR)/dist && echo 'dist/: Built' || echo 'dist/: Not built (run make web-ts-build)'"
	@echo ""
	@echo "[Server Performance]"
	@docker exec guarded_swarms bash -c "ps aux | grep -E 'uvicorn.*app:app' | grep -v grep | awk '{print \"  PID: \" \$$2 \"  |  CPU: \" \$$3 \"%  |  Memory: \" \$$4 \"%\"}' || echo '  Server not running'"
	@echo ""
	@echo "=========================================="
	@echo ""
	@echo "Dashboard URL: http://localhost:8080"
	@echo ""

web-ts-build:
	@echo "Building TypeScript files..."
	@docker exec guarded_swarms bash -c "cd /workspace/$(WEB_FRONTEND_DIR) && bun run build"
	@echo "TypeScript compiled successfully."

web-ts-watch:
	@echo "=========================================="
	@echo "Watching TypeScript Files"
	@echo "=========================================="
	@echo ""
	@echo "Auto-compiling on file changes..."
	@echo "Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "cd /workspace/$(WEB_FRONTEND_DIR) && bun run dev"

web-clean:
	@echo "Cleaning web dashboard artifacts..."
	@docker exec guarded_swarms bash -c "cd /workspace/$(WEB_FRONTEND_DIR) && rm -rf node_modules .bun dist 2>/dev/null || true"
	@docker exec guarded_swarms bash -c "cd /workspace/$(WEB_BACKEND_DIR) && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"
	@echo "Cleanup complete."

# ==============================================================================
# Demos
# ==============================================================================

demo-coordinator:
	@echo "=========================================="
	@echo "Launching Token Coordination Demo"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/install/guarded_swarms_coordinator" 2>/dev/null; then \
		echo "Package not built. Building guarded_swarms_coordinator..."; \
		docker exec guarded_swarms bash -c "cd /workspace && rm -rf build/guarded_swarms_coordinator install/guarded_swarms_coordinator 2>/dev/null || true"; \
		docker exec guarded_swarms bash -c "source /opt/ros/humble/setup.bash && cd /workspace && colcon build --packages-select guarded_swarms_coordinator"; \
		echo ""; \
	fi
	@echo "Starting 4 agents + coordinator..."
	@echo "Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "source /workspace/install/setup.bash && ros2 launch /workspace/src/tools/launch/demo.launch.py"

demo-tkinter:
	@echo "=========================================="
	@echo "Launching Tkinter Dashboard"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites:"
	@echo "X server must be running"
	@echo "demo-coordinator running in Terminal 1"
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/install/guarded_swarms_coordinator" 2>/dev/null; then \
		echo "Error: guarded_swarms_coordinator not built."; \
		echo "Run 'make demo-coordinator' first."; \
		exit 1; \
	fi
	@echo "Opening Tkinter GUI window..."
	@docker exec -it guarded_swarms bash -c "source /workspace/install/setup.bash && python3 /workspace/src/tools/visualization/dashboard.py"

demo-web:
	@echo "=========================================="
	@echo "Launching Web Dashboard"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites:"
	@echo "demo-coordinator running in Terminal 1"
	@echo "TypeScript compiled (run once): make web-ts-build"
	@echo ""
	@if ! docker exec guarded_swarms bash -c "test -d /workspace/install/guarded_swarms_coordinator" 2>/dev/null; then \
		echo "Error: guarded_swarms_coordinator not built."; \
		echo "Run 'make demo-coordinator' first."; \
		exit 1; \
	fi
	@echo "Dashboard will be available at:"
	@echo "http://localhost:8080"
	@echo ""
	@echo "Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms bash -c "source /opt/ros/humble/setup.bash && source /workspace/install/setup.bash && cd /workspace/$(WEB_BACKEND_DIR) && python3 -m uvicorn app:app --host 0.0.0.0 --port 8080"

# ==============================================================================
# Diagnostics
# ==============================================================================

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
	@echo "[1/5] Terminating PX4 SITL processes..."
	@docker exec guarded_swarms bash -c "pkill -9 px4 2>/dev/null || true" 2>/dev/null || true
	@echo "[2/5] Terminating Gazebo processes..."
	@docker exec guarded_swarms bash -c "pkill -9 -f 'gz sim' 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 ruby 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 gzserver 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 gzclient 2>/dev/null || true" 2>/dev/null || true
	@echo "[3/5] Terminating micro-ROS agent..."
	@docker exec guarded_swarms bash -c "pkill -9 MicroXRCEAgent 2>/dev/null || true" 2>/dev/null || true
	@echo "[4/5] Terminating ROS2 nodes..."
	@docker exec guarded_swarms bash -c "pkill -9 -f 'ros2' 2>/dev/null || true" 2>/dev/null || true
	@docker exec guarded_swarms bash -c "pkill -9 python3 2>/dev/null || true" 2>/dev/null || true
	@echo "[5/5] Cleaning up shared memory and lock files..."
	@docker exec guarded_swarms bash -c "rm -rf /tmp/.gazebo* /tmp/.X* /dev/shm/sem.* /dev/shm/fastrtps_* 2>/dev/null || true" 2>/dev/null || true
	@sleep 2
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
