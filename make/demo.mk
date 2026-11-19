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

.PHONY: demo-safety demo-safety-board demo-safety-sensors \
        test-resilience-mock

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
	@pkill -INT -f "[m]ock_pipeline.launch.py" 2>/dev/null || true