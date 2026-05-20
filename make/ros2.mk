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
# ros2.mk - ROS 2 workspace management (native Ubuntu)
# ==============================================================================

.PHONY: ros2-build-ws ros2-clean-ws ros2-rebuild-ws ros2-test-topics \
        ros2-graph ros2-agent ros2-node ros2-coordinator-reb

ros2-build-ws:
	@echo "Rebuilding ROS 2 workspace..."
	@bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD)"
	@echo "Build complete."

ros2-clean-ws:
	@echo "Cleaning workspace build artifacts..."
	@cd $(WORKSPACE_DIR) && rm -rf build/ install/ log/ 2>/dev/null || true
	@echo "Workspace cleaned."

ros2-rebuild-ws: ros2-clean-ws ros2-build-ws

ros2-test-topics:
	@echo "Verifying ROS 2 topics from PX4..."
	@echo ""
	@echo "Prerequisites: ros2-agent and px4-run must be running."
	@echo ""
	@bash -c "$(WORKSPACE_SOURCE) && ros2 topic list | grep fmu || echo 'No PX4 topics found. Ensure agent and SITL are running.'"

ros2-graph:
	@echo "=========================================="
	@echo "ROS 2 Graph Visualization"
	@echo "=========================================="
	@echo ""
	@if [ ! -d "$(INSTALL_DIR)" ]; then \
		echo "Error: ROS 2 workspace not built."; \
		echo "Run 'make ros2-build-ws' first."; \
		exit 1; \
	fi
	@echo "Opening rqt_graph..."
	@bash -c "$(WORKSPACE_SOURCE) && rqt_graph"

ros2-agent:
	@echo "=========================================="
	@echo "Launching micro-ROS Agent"
	@echo "=========================================="
	@echo ""
	@if ! which MicroXRCEAgent > /dev/null 2>&1; then \
		echo "Error: MicroXRCEAgent not found."; \
		echo "Run 'make setup-microros' to install it."; \
		exit 1; \
	fi
	@echo "Stopping any existing micro-ROS agent..."
	@bash -c "$(KILL_MICRO_ROS)" 2>/dev/null || true
	@sleep 1
	@echo "Bridge listening on UDP port 8888."
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@MicroXRCEAgent udp4 -p 8888

ros2-node:
	@echo "=========================================="
	@echo "Launching Offboard Control Node"
	@echo "=========================================="
	@echo ""
	@if [ ! -d "$(INSTALL_DIR)/$(CONTROL_PKG)" ]; then \
		echo "Error: $(CONTROL_PKG) package not built."; \
		echo "Run 'make ros2-build-ws' first."; \
		exit 1; \
	fi
	@echo "Prerequisites: Ensure micro-ROS agent and PX4 SITL are running."
	@echo "  Terminal 1: make ros2-agent"
	@echo "  Terminal 2: make px4-run-uav"
	@echo ""
	@echo "Stopping any existing offboard control node..."
	@pkill -9 -x offboard_control_node 2>/dev/null || true
	@sleep 1
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@bash -c "$(WORKSPACE_SOURCE) && ros2 run $(CONTROL_PKG) offboard_control_node"

ros2-coordinator-reb:
	@echo "Quick rebuild: $(COORDINATOR_PKG)"
	@cd $(WORKSPACE_DIR) && rm -rf build/$(COORDINATOR_PKG) install/$(COORDINATOR_PKG)
	@bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PKG) $(COORDINATOR_PKG)"
	@echo "Rebuild complete."