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
# ros2.mk - ROS 2 workspace management
# ==============================================================================

.PHONY: ros2-build-ws ros2-clean-ws ros2-rebuild-ws ros2-test-topics \
        ros2-graph ros2-agent ros2-node ros2-coordinator-reb

ros2-build-ws:
	@echo "Rebuilding ROS 2 workspace..."
	@$(DOCKER_EXEC_IT) bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD)"
	@echo "Build complete."

ros2-clean-ws:
	@echo "Cleaning workspace build artifacts..."
	@$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR) && rm -rf build/ install/ log/ 2>/dev/null || true"
	@echo "Workspace cleaned."

ros2-rebuild-ws: ros2-clean-ws ros2-build-ws

ros2-test-topics:
	@echo "Verifying ROS 2 topics from PX4..."
	@echo ""
	@echo "Prerequisites: ros2-agent and px4-run must be running."
	@echo ""
	@$(DOCKER_EXEC_IT) bash -c "$(WORKSPACE_SOURCE) && ros2 topic list | grep fmu || echo 'No PX4 topics found. Ensure agent and SITL are running.'"

ros2-graph:
	@echo "=========================================="
	@echo "ROS 2 Graph Visualization"
	@echo "=========================================="
	@echo ""
	@if ! $(DOCKER_EXEC) bash -c "test -d $(INSTALL_DIR)"; then \
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
	@$(DOCKER_EXEC_IT) bash -c "$(WORKSPACE_SOURCE) && rqt_graph"

ros2-agent:
	@echo "=========================================="
	@echo "Launching micro-ROS Agent"
	@echo "=========================================="
	@echo ""
	@if ! $(DOCKER_EXEC) which MicroXRCEAgent > /dev/null 2>&1; then \
		echo "Error: MicroXRCEAgent not found."; \
		echo "Run 'make setup-docker' to build the environment."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Stopping any existing micro-ROS agent..."
	@$(DOCKER_EXEC) bash -c "$(KILL_MICRO_ROS)" 2>/dev/null || true
	@sleep 1
	@echo "Bridge listening on UDP port 8888."
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@$(DOCKER_EXEC_IT) MicroXRCEAgent udp4 -p 8888

ros2-node:
	@echo "=========================================="
	@echo "Launching Offboard Control Node"
	@echo "=========================================="
	@echo ""
	@if ! $(DOCKER_EXEC) bash -c "test -d $(INSTALL_DIR)/$(CONTROL_PKG)"; then \
		echo "Error: $(CONTROL_PKG) package not built."; \
		echo "Run 'make ros2-build-ws' first."; \
		echo ""; \
		exit 1; \
	fi
	@echo "Prerequisites: Ensure micro-ROS agent and PX4 SITL are running."
	@echo "  Terminal 1: make ros2-agent"
	@echo "  Terminal 2: make px4-run"
	@echo ""
	@echo "Stopping any existing offboard control node..."
	@$(DOCKER_EXEC) bash -c "pkill -9 -f offboard_control_node 2>/dev/null || true" 2>/dev/null || true
	@sleep 1
	@echo "Keep this terminal open. Press Ctrl+C to stop."
	@echo ""
	@$(DOCKER_EXEC_IT) bash -c "$(WORKSPACE_SOURCE) && ros2 run $(CONTROL_PKG) offboard_control_node"

ros2-coordinator-reb:
	@echo "Quick rebuild: $(COORDINATOR_PKG)"
	@$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR) && rm -rf build/$(COORDINATOR_PKG) install/$(COORDINATOR_PKG)"
	@$(DOCKER_EXEC) bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PKG) $(COORDINATOR_PKG)"
	@echo "Rebuild complete. Source workspace: source $(INSTALL_DIR)/setup.bash"
