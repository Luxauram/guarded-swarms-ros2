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

.PHONY: help setup-all setup-docker setup-workspace setup-px4 \
        start stop restart enter logs status clean \
        build-workspace clean-workspace rebuild-workspace \
        agent px4-run px4-console node test-topics

.DEFAULT_GOAL := help

# ==============================================================================
# Help & Documentation
# ==============================================================================

help:
	@echo ""
	@echo "Guarded Swarms - Available Commands"
	@echo "===================================="
	@echo ""
	@echo "FIRST-TIME SETUP:"
	@echo "  Option A (automated):"
	@echo "    make setup-all          Run complete setup automatically"
	@echo ""
	@echo "  Option B (manual steps):"
	@echo "    make setup-docker       1. Build Docker environment"
	@echo "    make setup-workspace    2. Build ROS 2 packages"
	@echo "    make setup-px4          3. Clone and build PX4-Autopilot"
	@echo ""
	@echo "DOCKER MANAGEMENT:"
	@echo "  make start              Start development container"
	@echo "  make stop               Stop container"
	@echo "  make restart            Restart container"
	@echo "  make enter              Open shell inside container"
	@echo "  make logs               View container logs"
	@echo "  make status             Show container status"
	@echo "  make clean              Remove container and volumes (destructive)"
	@echo ""
	@echo "DEVELOPMENT WORKFLOW:"
	@echo "  make build-workspace    Rebuild ROS 2 packages after code changes"
	@echo "  make clean-workspace    Remove build artifacts"
	@echo "  make rebuild-workspace  Clean and rebuild workspace"
	@echo ""
	@echo "RUNTIME (requires 3 separate terminals):"
	@echo "  Terminal 1: make agent       Launch micro-ROS bridge"
	@echo "  Terminal 2: make px4-run     Launch PX4 SITL simulator"
	@echo "  Terminal 3: make node        Launch offboard control node"
	@echo ""
	@echo "TESTING & DEBUGGING:"
	@echo "  make test-topics        Verify ROS 2 topics from PX4"
	@echo "  make px4-console        Open PX4 interactive console"
	@echo ""
	@echo "For detailed documentation, see README.md"
	@echo ""

# ==============================================================================
# Automated Setup
# ==============================================================================

setup-all: setup-docker setup-workspace setup-px4
	@echo ""
	@echo "=========================================="
	@echo "Setup Complete"
	@echo "=========================================="
	@echo ""
	@echo "System is ready. To run the demo:"
	@echo ""
	@echo "  1. Open three terminal windows"
	@echo "  2. In terminal 1, run: make agent"
	@echo "  3. In terminal 2, run: make px4-run"
	@echo "  4. In terminal 3, run: make node"
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
	@echo "Building packages: px4_msgs, px4_ros_com, guarded_swarms_control"
	@echo ""
	@docker exec -it guarded_swarms_dev bash -c "cd /workspace && colcon build"
	@echo ""
	@echo "ROS 2 workspace ready."
	@echo ""

setup-px4:
	@echo "=========================================="
	@echo "Setting Up PX4-Autopilot"
	@echo "=========================================="
	@echo ""
	@if docker exec guarded_swarms_dev test -d /workspace/PX4-Autopilot; then \
		echo "PX4-Autopilot directory exists. Skipping clone."; \
		echo ""; \
	else \
		echo "Step 1/3: Cloning PX4-Autopilot repository (includes submodules)..."; \
		docker exec guarded_swarms_dev bash -c "cd /workspace && git clone https://github.com/PX4/PX4-Autopilot.git --recursive"; \
		echo "Repository cloned."; \
		echo ""; \
	fi
	@echo "Step 2/3: Installing dependencies..."
	@docker exec guarded_swarms_dev bash -c "cd /workspace/PX4-Autopilot && bash ./Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools > /dev/null 2>&1"
	@echo "Dependencies installed."
	@echo ""
	@echo "Step 3/3: Building PX4 SITL (this will take some time)..."
	@docker exec guarded_swarms_dev bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"
	@echo ""
	@echo "PX4 setup complete."
	@echo ""

# ==============================================================================
# Docker Operations
# ==============================================================================

start:
	@echo "Starting container..."
	@cd docker && docker-compose up -d
	@sleep 1
	@echo "Container started. Use 'make enter' to access shell."

stop:
	@echo "Stopping container..."
	@cd docker && docker-compose down
	@echo "Container stopped."

restart: stop start

enter:
	@echo "Entering container. Type 'exit' to return to host."
	@echo ""
	@docker exec -it guarded_swarms_dev bash

logs:
	@cd docker && docker-compose logs --tail=100

status:
	@echo "Container status:"
	@echo ""
	@docker ps -a | grep guarded_swarms_dev || echo "Container not found."

clean:
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
# Development Workflow
# ==============================================================================

build-workspace:
	@echo "Rebuilding ROS 2 workspace..."
	@docker exec -it guarded_swarms_dev bash -c "cd /workspace && colcon build"
	@echo "Build complete."

clean-workspace:
	@echo "Cleaning workspace build artifacts..."
	@docker exec guarded_swarms_dev bash -c "cd /workspace && rm -rf build/ install/ log/ 2>/dev/null || true"
	@echo "Workspace cleaned."

rebuild-workspace: clean-workspace build-workspace

# ==============================================================================
# Runtime (Multi-Terminal Workflow)
# ==============================================================================

agent:
	@echo "=========================================="
	@echo "Launching micro-ROS Agent"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms_dev which MicroXRCEAgent > /dev/null 2>&1; then \
		echo "Error: MicroXRCEAgent not found."; \
		echo "Run 'make setup-docker' to build the environment."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Bridge listening on UDP port 8888."
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms_dev MicroXRCEAgent udp4 -p 8888

px4-run:
	@echo "=========================================="
	@echo "Launching PX4 SITL"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms_dev test -d /workspace/PX4-Autopilot; then \
		echo "Error: PX4-Autopilot not found."; \
		echo "Run 'make setup-px4' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Starting Gazebo simulation (headless mode)."
	@echo "Keep this terminal open."
	@echo ""
	@echo "For manual arming at pxh> prompt:"
	@echo "  commander arm -f"
	@echo "  commander mode offboard"
	@echo ""
	@docker exec -it guarded_swarms_dev bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"

px4-console:
	@echo "Opening PX4 interactive console..."
	@echo ""
	@if ! docker exec guarded_swarms_dev test -d /workspace/PX4-Autopilot; then \
		echo "Error: PX4-Autopilot not found."; \
		echo "Run 'make setup-px4' first."; \
		echo ""; \
		exit 1; \
	fi
	@docker exec -it guarded_swarms_dev bash -c "cd /workspace/PX4-Autopilot && HEADLESS=1 make px4_sitl gz_x500"

node:
	@echo "=========================================="
	@echo "Launching Offboard Control Node"
	@echo "=========================================="
	@echo ""
	@if ! docker exec guarded_swarms_dev test -f /workspace/install/setup.bash; then \
		echo "Error: ROS 2 workspace not built."; \
		echo "Run 'make setup-workspace' or 'make build-workspace' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Prerequisites: Ensure micro-ROS agent and PX4 SITL are running."
	@echo "  Terminal 1: make agent"
	@echo "  Terminal 2: make px4-run"
	@echo ""
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@docker exec -it guarded_swarms_dev bash -c "source /workspace/install/setup.bash && ros2 run guarded_swarms_control offboard_control_node"

# ==============================================================================
# Testing & Debugging
# ==============================================================================

test-topics:
	@echo "Verifying ROS 2 topics from PX4..."
	@echo ""
	@echo "Prerequisites: micro-ROS agent and PX4 SITL must be running."
	@echo "Run 'make agent' and 'make px4-run' in separate terminals first."
	@echo ""
	@docker exec -it guarded_swarms_dev bash -c "source /workspace/install/setup.bash && ros2 topic list | grep fmu || echo 'No PX4 topics found. Ensure agent and SITL are running.'"
