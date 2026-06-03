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
# Guarded Swarms - Root Makefile
#
# Native Ubuntu installation.
# Requires: Ubuntu 22.04, ROS 2 Humble, PX4, Gazebo Harmonic.
#
# This file only wires together the sub-makefiles in make/.
# ==============================================================================

include make/vars.mk
include make/ros2.mk
include make/px4.mk
include make/demo.mk
include make/web.mk
include make/diagnostics.mk

.DEFAULT_GOAL := help

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo ""
	@echo "Guarded Swarms - Command Reference"
	@echo "===================================="
	@echo ""
	@echo "  make show-guide           Complete usage guide and workflows"
	@echo ""
	@echo "===================================="
	@echo "  SETUP COMMANDS"
	@echo "===================================="
	@echo ""
	@echo "  make setup-all            Build workspace + PX4"
	@echo "  make setup-workspace      Build ROS 2 packages"
	@echo "  make setup-px4            Clone and build PX4-Autopilot"
	@echo "  make setup-ugv            Install UGV airframe+model (run once)"
	@echo "  make setup-worlds         Install Guarded Swarms world files into PX4"
	@echo ""
	@echo "===================================="
	@echo "  ROS 2"
	@echo "===================================="
	@echo ""
	@echo "  make ros2-build-ws        Rebuild workspace"
	@echo "  make ros2-clean-ws        Remove build artifacts"
	@echo "  make ros2-rebuild-ws      Clean + rebuild"
	@echo "  make ros2-test-topics     Verify ROS 2 / PX4 topics"
	@echo "  make ros2-graph           rqt_graph visualization"
	@echo "  make ros2-agent           Launch micro-ROS bridge"
	@echo "  make ros2-node            Launch offboard control node"
	@echo "  make ros2-coordinator-reb Quick rebuild coordinator package"
	@echo ""
	@echo "===================================="
	@echo "  PX4 / SIMULATION"
	@echo "===================================="
	@echo ""
	@echo "  make px4-run-uav          UAV  - x500 quadcopter + lidar  [headless]"
	@echo "  make px4-run-ugv          UGV  - differential rover + lidar [headless]"
	@echo "  make px4-gui-uav          UAV  - Gazebo GUI"
	@echo "  make px4-gui-ugv          UGV  - Gazebo GUI"
	@echo "  make px4-kill             Kill all PX4 / Gazebo processes"
	@echo "  make px4-config           Print arming parameter commands"
	@echo "  make px4-reset-params     Print parameter reset commands"
	@echo "  make gazebo-test          Test Gazebo with empty world"
	@echo "  make gazebo-worlds        List available worlds"
	@echo ""
	@echo "  NOTE: For GPU-accelerated Gazebo rendering (required for lidar):"
	@echo "    __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia MESA_GL_VERSION_OVERRIDE=4.5 make px4-gui-uav"
	@echo ""
	@echo "===================================="
	@echo "  DEMOS"
	@echo "===================================="
	@echo ""
	@echo "  make demo-coordinator       Token coordination (4 agents)"
	@echo "  make demo-tkinter           Tkinter dashboard"
	@echo "  make demo-web               Web dashboard  (localhost:$(DASHBOARD_PORT))"
	@echo "  make demo-safety            Safety board scenario overview"
	@echo "  make demo-safety-board      Launch safety board node"
	@echo "  make demo-safety-sensors    Launch mock sensor publisher"
	@echo "  make demo-bridge            Launch command bridge node"
	@echo "  make demo-pipeline          Full pipeline (mock sensors)"
	@echo "  make demo-px4-bridge        PX4->SafetyBoard bridge (UAV)"
	@echo "  make demo-px4-bridge-rover  PX4->SafetyBoard bridge (UGV)"
	@echo "  make demo-safety-board-uav  Safety board tuned for UAV"
	@echo "  make demo-safety-board-rover Safety board tuned for UGV"
	@echo "  make demo-px4-uav           Full UAV pipeline instructions"
	@echo "  make demo-px4-rover         Full UGV pipeline instructions"
	@echo "  make demo-px4-uav-urban    UAV Urban full pipeline - R1 (one command)"
	@echo "  make demo-px4-ugv-urban    UGV Urban full pipeline - R2 (one command)"
	@echo "  make demo-record-uav       Record UAV urban demo to bag file"
	@echo "  make demo-record-ugv       Record UGV urban demo to bag file"
	@echo "  make demo-record-mock      Record mock pipeline to bag file"
	@echo "  make demo-replay           Replay a recorded bag"
	@echo "  make demo-bag-info         Show info about a recorded bag"
	@echo ""
	@echo "===================================="
	@echo "  WEB DASHBOARD"
	@echo "===================================="
	@echo ""
	@echo "  make web-dev              Start dashboard server (localhost:$(DASHBOARD_PORT))"
	@echo "  make web-stop             Stop dashboard server"
	@echo "  make web-status           Check dashboard status"
	@echo "  make web-clean            Remove build artifacts"
	@echo "  make web-ts-build         Compile TypeScript"
	@echo "  make web-ts-watch         Auto-compile on file changes"
	@echo ""
	@echo "===================================="
	@echo "  DIAGNOSTICS & CLEANUP"
	@echo "===================================="
	@echo ""
	@echo "  make diagnose             Full system diagnostic"
	@echo "  make check-gpu            Check GPU support"
	@echo "  make kill-all             Terminate all processes"
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
	@echo "  - Ubuntu 22.04 LTS (native install)"
	@echo "  - ROS 2 Humble"
	@echo "  - Gazebo Harmonic"
	@echo "  - PX4-Autopilot (cloned to ~/PX4-Autopilot)"
	@echo "  - NVIDIA GPU (recommended for Gazebo lidar)"
	@echo ""
	@echo "  See README.md for full installation instructions."
	@echo ""
	@echo "======================================="
	@echo "  2. INITIAL SETUP (First Time Only)"
	@echo "======================================="
	@echo ""
	@echo "  $$ make setup-all"
	@echo ""
	@echo "  Or manually:"
	@echo "    $$ make setup-workspace   # Build ROS 2 packages"
	@echo "    $$ make setup-px4         # Setup PX4 simulator"
	@echo "    $$ make setup-ugv         # Install UGV assets (optional)"
	@echo ""
	@echo "======================================="
	@echo "  3. GAZEBO GPU ACCELERATION"
	@echo "======================================="
	@echo ""
	@echo "  Gazebo lidar sensors require GPU rendering."
	@echo "  Without GPU, proximity reads 999.0m (no obstacles)."
	@echo ""
	@echo "  GPU flags are embedded in all px4-gui-* targets automatically."
	@echo ""
	@echo "  Check GPU: make check-gpu"
	@echo ""
	@echo "======================================="
	@echo "  4. AVAILABLE DEMOS"
	@echo "======================================="
	@echo ""
	@echo "  A) Token Coordination (no PX4):"
	@echo "    Terminal 1: make demo-coordinator"
	@echo "    Terminal 2: make demo-web  ->  http://localhost:$(DASHBOARD_PORT)"
	@echo ""
	@echo "  B) Safety Board with Mock Sensors (no PX4):"
	@echo "    Terminal 1: make demo-safety-board"
	@echo "    Terminal 2: make demo-safety-sensors"
	@echo "    Monitor:    ros2 topic echo /actuator_cmd_safe"
	@echo ""
	@echo "  C) Full Pipeline Mock (all layers, no PX4):"
	@echo "    Terminal 1: make demo-coordinator"
	@echo "    Terminal 2: make demo-bridge"
	@echo "    Terminal 3: make demo-safety-board"
	@echo "    Terminal 4: make demo-safety-sensors"
	@echo ""
	@echo "  D) UAV Urban Scenario (R1 from paper) - single command:"
	@echo "    make demo-px4-uav-urban"
	@echo "    (opens Gazebo + micro-ROS automatically, drone auto-arms)"
	@echo "    Monitor: ros2 topic echo /actuator_cmd_safe"
	@echo ""
	@echo "  E) UGV Urban Scenario (R2 from paper) - single command:"
	@echo "    make setup-ugv  (run once)"
	@echo "    make demo-px4-ugv-urban"
	@echo "    (opens Gazebo + micro-ROS automatically)"
	@echo "    Monitor: ros2 topic echo /actuator_cmd_safe"
	@echo ""
	@echo ""
	@echo "  For command reference: make help"
	@echo ""
