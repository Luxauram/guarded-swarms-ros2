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
# demo.mk - Demo and pipeline launch targets (native Ubuntu)
# ==============================================================================

.PHONY: demo-coordinator demo-coordinator-batch demo-tkinter \
        demo-safety demo-safety-board demo-safety-sensors \
        demo-bridge demo-pipeline \
        demo-px4-bridge demo-px4-bridge-rover \
        demo-px4-uav demo-px4-rover \
        demo-safety-board-uav demo-safety-board-rover \
        demo-px4-ugv-urban demo-px4-uav-urban \
        demo-ugv-urban-pipeline demo-uav-urban-pipeline \
        demo-record-uav demo-record-ugv demo-record-mock \
        demo-replay demo-bag-info \
        test-resilience-mock

# ------------------------------------------------------------------------------
# Token coordination
# ------------------------------------------------------------------------------
demo-coordinator:
	@echo "=========================================="
	@echo "Launching Token Coordination Demo"
	@echo "=========================================="
	@echo ""
	@if [ ! -d "$(INSTALL_DIR)/$(COORDINATOR_PKG)" ]; then \
		echo "Package not built. Building $(COORDINATOR_PKG)..."; \
		bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PKG) $(COORDINATOR_PKG)"; \
		echo ""; \
	fi
	@echo "Step 1/3: Number of Agents"; \
	echo ""; \
	read -p "How many agents to launch? [1-4, default=4]: " num_agents; \
	num_agents=$${num_agents:-4}; \
	if [ $$num_agents -lt 1 ] || [ $$num_agents -gt 4 ]; then \
		echo "Invalid number. Must be 1-4. Using 4."; \
		num_agents=4; \
	fi; \
	echo ""; \
	echo "Step 2/3: Arbitration Mode"; \
	echo "  1) FCFS (First-Come-First-Serve)"; \
	echo "  2) Priority-based (default)"; \
	echo "  3) Hybrid"; \
	read -p "Choice [1-3, default=2]: " mode_choice; \
	mode_choice=$${mode_choice:-2}; \
	case $$mode_choice in \
		1) arb_mode="fcfs" ;; \
		2) arb_mode="priority" ;; \
		3) arb_mode="hybrid" ;; \
		*) echo "Invalid choice. Using priority mode."; arb_mode="priority" ;; \
	esac; \
	echo ""; \
	echo "Step 3/3: Agent Priorities (0-10)"; \
	prio_a=5; prio_b=5; prio_c=5; prio_d=5; \
	read -p "  Agent A priority [default=5]: " input_a; \
	prio_a=$${input_a:-5}; \
	if [ $$num_agents -ge 2 ]; then \
		read -p "  Agent B priority [default=5]: " input_b; \
		prio_b=$${input_b:-5}; \
	fi; \
	if [ $$num_agents -ge 3 ]; then \
		read -p "  Agent C priority [default=5]: " input_c; \
		prio_c=$${input_c:-5}; \
	fi; \
	if [ $$num_agents -ge 4 ]; then \
		read -p "  Agent D priority [default=5]: " input_d; \
		prio_d=$${input_d:-5}; \
	fi; \
	echo ""; \
	echo "Launch Configuration:"; \
	echo "  - Agents: $$num_agents"; \
	echo "  - Mode: $$arb_mode"; \
	echo -n "  - Priorities: A=$$prio_a"; \
	if [ $$num_agents -ge 2 ]; then echo -n ", B=$$prio_b"; fi; \
	if [ $$num_agents -ge 3 ]; then echo -n ", C=$$prio_c"; fi; \
	if [ $$num_agents -ge 4 ]; then echo -n ", D=$$prio_d"; fi; \
	echo ""; \
	echo ""; \
	read -p "Proceed? [Y/n]: " confirm; \
	confirm=$${confirm:-Y}; \
	if [ "$$confirm" != "Y" ] && [ "$$confirm" != "y" ]; then \
		echo "Cancelled."; \
		exit 0; \
	fi; \
	echo ""; \
	echo "Starting demo..."; \
	echo "Press Ctrl+C to stop."; \
	echo ""; \
	bash -c "$(WORKSPACE_SOURCE) && ros2 launch $(WORKSPACE_DIR)/$(TOOLS_LAUNCH_DIR)/demo.launch.py \
		arbitration_mode:=$$arb_mode \
		priority_A:=$$prio_a \
		priority_B:=$$prio_b \
		priority_C:=$$prio_c \
		priority_D:=$$prio_d \
		num_agents:=$$num_agents"
 
demo-coordinator-batch:
	@if [ ! -d "$(INSTALL_DIR)/$(COORDINATOR_PKG)" ]; then \
		bash -c "$(ROS2_SOURCE) && cd $(WORKSPACE_DIR) && $(COLCON_BUILD_PKG) $(COORDINATOR_PKG)"; \
	fi
	@echo "Launching demo in background..."
	@bash -c " \
		$(WORKSPACE_SOURCE) && \
		nohup ros2 launch $(WORKSPACE_DIR)/$(TOOLS_LAUNCH_DIR)/demo.launch.py \
			arbitration_mode:=$(ARB_MODE) \
			priority_A:=$(PRIO_A) \
			priority_B:=$(PRIO_B) \
			priority_C:=$(PRIO_C) \
			priority_D:=$(PRIO_D) \
			num_agents:=$(NUM_AGENTS) \
			> /tmp/demo.log 2>&1 & \
		echo Demo launched with PID \$$! \
	"

# ------------------------------------------------------------------------------
# Visualization
# ------------------------------------------------------------------------------
demo-tkinter:
	@echo "=========================================="
	@echo "Launching Tkinter Dashboard"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites: demo-coordinator running in Terminal 1"
	@echo ""
	@bash -c "$(WORKSPACE_SOURCE) && python3 $(WORKSPACE_DIR)/$(TOOLS_VIZ_DIR)/dashboard.py"

# ------------------------------------------------------------------------------
# Safety board (mock sensors)
# ------------------------------------------------------------------------------
demo-safety:
	@echo "=========================================="
	@echo "Safety Board Demo - Scenario Overview"
	@echo "=========================================="
	@echo ""
	@echo "Terminal 1: make demo-safety-board    # enforcement node"
	@echo "Terminal 2: make demo-safety-sensors  # mock sensor publisher"
	@echo ""
	@echo "Scenarios (10s each):"
	@echo "  0 - NOMINAL          (all safe)"
	@echo "  1 - PROXIMITY        (obstacle at 0.8m < threshold 1.5m)"
	@echo "  2 - ATTITUDE         (pitch 45deg > threshold 30deg)"
	@echo "  3 - BATTERY LOW      (10% < threshold 15%)"
	@echo "  4 - ALTITUDE HIGH    (60m > threshold 50m)"
	@echo "  5 - NOMINAL RECOVERY"
	@echo ""
	@echo "Monitor:"
	@echo "  ros2 topic echo /actuator_cmd_safe   # 0.6=cleared 0.0=vetoed"
	@echo "  ros2 topic echo /safety_status       # 1.0=safe    0.0=unsafe"
	@echo ""
 
demo-safety-board:
	@bash -c "$(WORKSPACE_SOURCE) && ros2 run $(SAFETY_PKG) safety_board_node"
 
demo-safety-sensors:
	@bash -c "$(WORKSPACE_SOURCE) && ros2 run $(SAFETY_PKG) mock_sensor_publisher"
 
# ------------------------------------------------------------------------------
# Command bridge
# ------------------------------------------------------------------------------
demo-bridge:
	@bash -c "$(WORKSPACE_SOURCE) && ros2 run $(CONTROL_PKG) command_bridge_node"
 
# ------------------------------------------------------------------------------
# Full pipeline (mock sensors, no PX4)
# ------------------------------------------------------------------------------
demo-pipeline:
	@echo "=========================================="
	@echo "Full Pipeline Demo"
	@echo "=========================================="
	@echo ""
	@echo "Open 4 terminals in order:"
	@echo ""
	@echo "  Terminal 1: make demo-coordinator      # agent -> coordinator -> AuthToken"
	@echo "  Terminal 2: make demo-bridge           # AuthToken -> /actuator_cmd_raw"
	@echo "  Terminal 3: make demo-safety-board     # /actuator_cmd_raw -> /actuator_cmd_safe"
	@echo "  Terminal 4: make demo-safety-sensors   # mock sensor scenarios"
	@echo ""
	@echo "Monitor:"
	@echo "  ros2 topic echo /actuator_cmd_raw      # 0.6 when token approved"
	@echo "  ros2 topic echo /actuator_cmd_safe     # 0.6=cleared  0.0=vetoed"
	@echo "  ros2 topic echo /safety_status         # 1.0=safe      0.0=unsafe"
	@echo ""

# ------------------------------------------------------------------------------
# PX4 bridge (real Gazebo sensors)
# ------------------------------------------------------------------------------
demo-px4-bridge:
	@bash -c "$(WORKSPACE_SOURCE) && \
		ros2 run $(CONTROL_PKG) px4_safety_bridge_node \
		--ros-args -p lidar_topic:=/world/default/model/x500_lidar_front_0/link/lidar_sensor_link/sensor/lidar/scan"
 
demo-px4-bridge-rover:
	@bash -c "$(WORKSPACE_SOURCE) && \
		ros2 run $(CONTROL_PKG) px4_safety_bridge_node \
		--ros-args \
		-p lidar_topic:=/world/rover/model/rover_differential_lidar_0/link/lidar_sensor_link/sensor/lidar/scan"
 
demo-safety-board-uav:
	@bash -c "$(WORKSPACE_SOURCE) && \
		ros2 run $(SAFETY_PKG) safety_board_node \
		--ros-args -p sensor_staleness_s:=5.0"
 
demo-safety-board-rover:
	@bash -c "$(WORKSPACE_SOURCE) && \
		ros2 run $(SAFETY_PKG) safety_board_node \
		--ros-args \
		-p min_altitude_m:=-1.0 \
		-p max_altitude_m:=999.0 \
		-p sensor_staleness_s:=5.0"

# ------------------------------------------------------------------------------
# Full UAV pipeline instructions
# ------------------------------------------------------------------------------
demo-px4-uav:
	@echo "=========================================="
	@echo "UAV Full Pipeline with PX4 Sensors"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites (start in order):"
	@echo "  Terminal 1: make px4-run-uav"
	@echo "              -> wait for pxh>, then run px4-config commands"
	@echo "              -> commander takeoff"
	@echo "  Terminal 2: make ros2-agent"
	@echo "  Terminal 3: make ros2-node"
	@echo "  Terminal 4: ros2 run ros_gz_bridge parameter_bridge \\"
	@echo "                /world/default/model/x500_lidar_front_0/link/lidar_sensor_link/sensor/lidar/scan\\"
	@echo "                @sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"
	@echo "  Terminal 5: make demo-px4-bridge"
	@echo "  Terminal 6: make demo-safety-board-uav"
	@echo "  Terminal 7: make demo-bridge"
	@echo "  Terminal 8: make demo-coordinator"
	@echo ""

# ------------------------------------------------------------------------------
# Full UGV pipeline instructions
# ------------------------------------------------------------------------------
demo-px4-rover:
	@echo "=========================================="
	@echo "UGV Full Pipeline with PX4 Sensors"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites (start in order):"
	@echo "  Terminal 1: make px4-run-ugv"
	@echo "  Terminal 2: make ros2-agent"
	@echo "  Terminal 3: ros2 run ros_gz_bridge parameter_bridge \\"
	@echo "                /world/rover/model/rover_differential_lidar_0/link/lidar_sensor_link/sensor/lidar/scan\\"
	@echo "                @sensor_msgs/msg/LaserScan[gz.msgs.LaserScan"
	@echo "  Terminal 4: make demo-px4-bridge-rover"
	@echo "  Terminal 5: make demo-safety-board-rover"
	@echo "  Terminal 6: make demo-bridge"
	@echo "  Terminal 7: make demo-coordinator"
	@echo ""

# ------------------------------------------------------------------------------
# UGV Urban pipeline - single command launch
# ------------------------------------------------------------------------------
demo-px4-ugv-urban:
	@echo "=========================================="
	@echo "UGV Urban Pipeline (R2) - Full Launch"
	@echo "=========================================="
	@echo ""
	@echo "Opening support terminals..."
	@xterm -title "PX4 UGV Urban" -geometry 120x30 -e bash -c "cd $(WORKSPACE_DIR) && source ~/.bashrc && make px4-gui-ugv-urban; bash" &
	@sleep 12
	@xterm -title "micro-ROS Agent" -geometry 120x15 -e bash -c "cd $(WORKSPACE_DIR) && source ~/.bashrc && make ros2-agent; bash" &
	@sleep 6
	@echo "Launching ROS2 pipeline (this window)..."
	@bash -c "$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup ugv_urban_pipeline.launch.py"

demo-ugv-urban-pipeline:
	@bash -c "$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup ugv_urban_pipeline.launch.py"

# ------------------------------------------------------------------------------
# UAV Urban pipeline - single command launch
# ------------------------------------------------------------------------------
demo-px4-uav-urban:
	@echo "=========================================="
	@echo "UAV Urban Pipeline (R1) - Full Launch"
	@echo "=========================================="
	@echo ""
	@echo "Opening support terminals..."
	@xterm -title "PX4 UAV Urban" -geometry 120x30 -e bash -c "cd $(WORKSPACE_DIR) && source ~/.bashrc && make px4-gui-uav-urban; bash" &
	@sleep 35
	@xterm -title "micro-ROS Agent" -geometry 120x15 -e bash -c "cd $(WORKSPACE_DIR) && source ~/.bashrc && make ros2-agent; bash" &
	@sleep 10
	@xterm -title "Offboard Control" -geometry 120x15 -e bash -c "cd $(WORKSPACE_DIR) && source ~/.bashrc && make ros2-node; bash" &
	@sleep 10
	@echo "Launching ROS2 pipeline (this window)..."
	@bash -c "$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup uav_urban_pipeline.launch.py"

demo-uav-urban-pipeline:
	@bash -c "$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup uav_urban_pipeline.launch.py"

# ------------------------------------------------------------------------------
# ROS 2 bag recording
# ------------------------------------------------------------------------------
demo-record-uav:
	@echo "=========================================="
	@echo "Recording UAV Urban Demo (R1)"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites: make demo-px4-uav-urban already running."
	@echo "Press Ctrl+C to stop recording."
	@echo ""
	@bash -c "$(WORKSPACE_DIR)/scripts/record/record_demo.sh uav"
 
demo-record-ugv:
	@echo "=========================================="
	@echo "Recording UGV Urban Demo (R2)"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites: make demo-px4-ugv-urban already running."
	@echo "Press Ctrl+C to stop recording."
	@echo ""
	@bash -c "$(WORKSPACE_DIR)/scripts/record/record_demo.sh ugv"
 
demo-record-mock:
	@echo "=========================================="
	@echo "Recording Mock Pipeline Demo"
	@echo "=========================================="
	@echo ""
	@echo "Prerequisites: mock pipeline already running."
	@echo "Press Ctrl+C to stop recording."
	@echo ""
	@bash -c "$(WORKSPACE_DIR)/scripts/record/record_demo.sh mock"
 
demo-replay:
	@echo "=========================================="
	@echo "Replay a recorded bag"
	@echo "=========================================="
	@echo ""
	@echo "Available bags:"
	@ls -1 $(WORKSPACE_DIR)/bags/ 2>/dev/null || echo "  No bags found - run make demo-record-uav or demo-record-ugv first."
	@echo ""
	@read -p "Bag name to replay (from list above): " bag_name; \
	bash -c "$(WORKSPACE_SOURCE) && ros2 bag play $(WORKSPACE_DIR)/bags/$$bag_name"
 
demo-bag-info:
	@echo "Available bags:"
	@ls -1 $(WORKSPACE_DIR)/bags/ 2>/dev/null || echo "  No bags found."
	@echo ""
	@read -p "Bag name to inspect: " bag_name; \
	bash -c "$(WORKSPACE_SOURCE) && ros2 bag info $(WORKSPACE_DIR)/bags/$$bag_name"

# ------------------------------------------------------------------------------
# Resilience tests
# ------------------------------------------------------------------------------
test-resilience-mock:
	@echo "=========================================="
	@echo "Resilience Tests - Mock Pipeline"
	@echo "=========================================="
	@echo ""
	@echo "Starting mock pipeline in background..."
	@bash -c "$(FULL_SOURCE) && ros2 launch guarded_swarms_bringup mock_pipeline.launch.py > /tmp/mock_pipeline.log 2>&1 &"
	@sleep 8
	@echo "Running resilience tests..."
	@echo ""
	@bash -c "$(WORKSPACE_SOURCE) && $(RESILIENCE_DIR)/test_runner.sh mock"
	@echo ""
	@echo "Stopping mock pipeline..."
	@pkill -TERM -f "[m]ock_pipeline.launch.py" 2>/dev/null || true