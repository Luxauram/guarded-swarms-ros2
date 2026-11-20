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
# Guarded Swarms - root Makefile
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
include make/diagnostics.mk

.DEFAULT_GOAL := help

.PHONY: help show-guide

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
	@echo "  SETUP"
	@echo "===================================="
	@echo ""
	@echo "  make setup-all            Build workspace + PX4"
	@echo "  make setup-workspace      Build ROS 2 packages"
	@echo "  make setup-px4            Clone and build PX4-Autopilot"
	@echo "  make setup-ugv            Check the UGV model (r1_rover with lidar)"
	@echo "  make gen-coastal          Generate the coastal case-study world"
	@echo ""
	@echo "===================================="
	@echo "  COASTAL CASE STUDY (main scenario)"
	@echo "===================================="
	@echo ""
	@echo "  make demo-coastal         The world: 2 UAV + 1 UGV (needs a GPU)"
	@echo "  make check-coastal        Health check the coastal scenario"
	@echo ""
	@echo "  Drive the pipeline (in a second terminal):"
	@echo "    ./scripts/pipeline/test_pipeline.sh   Intruder, sensing, TB-CSPN, report"
	@echo "    ./scripts/pipeline/demo_console.sh     Live supervisor-console demonstration"
	@echo ""
	@echo "===================================="
	@echo "  ROS 2 WORKSPACE"
	@echo "===================================="
	@echo ""
	@echo "  make ros2-build-ws        Rebuild the workspace"
	@echo "  make ros2-clean-ws        Remove build artifacts"
	@echo "  make ros2-rebuild-ws      Clean + rebuild"
	@echo "  make ros2-graph           rqt_graph visualization"
	@echo ""
	@echo "===================================="
	@echo "  PX4 / SIMULATION"
	@echo "===================================="
	@echo ""
	@echo "  make px4-kill             Kill PX4, Gazebo and the uXRCE-DDS agents"
	@echo "  make gazebo-test          Test Gazebo with an empty world"
	@echo "  make gazebo-worlds        List available worlds"
	@echo ""
	@echo "  NOTE: Gazebo renders the lidars on the GPU. scripts/sim/gz_launch.sh,"
	@echo "    which starts Gazebo, selects the NVIDIA GPU when its driver is loaded."
	@echo ""
	@echo "===================================="
	@echo "  ANALOG SAFETY BOARD (software-only)"
	@echo "===================================="
	@echo ""
	@echo "  make demo-safety            Safety board scenario overview"
	@echo "  make demo-safety-board      Launch the safety board node"
	@echo "  make demo-safety-sensors    Launch the mock sensor publisher"
	@echo "  make test-resilience-mock   Run the resilience tests of the board"
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
	@echo "For the full documentation, see docs/README.md"
	@echo ""

# ==============================================================================
# Complete user guide
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
	@echo "  - PX4-Autopilot (cloned to ~/PX4-Autopilot, pinned commit)"
	@echo "  - A GPU for Gazebo, which renders the lidars on it (NVIDIA recommended)"
	@echo ""
	@echo "  See docs/getting-started.md for the installation."
	@echo ""
	@echo "======================================="
	@echo "  2. INITIAL SETUP (first time only)"
	@echo "======================================="
	@echo ""
	@echo "  $$ ./install.sh              # every dependency, PX4 and the workspace"
	@echo "  $$ make setup-all            # or, with the dependencies in place:"
	@echo "                               # PX4 and the workspace only"
	@echo ""
	@echo "======================================="
	@echo "  3. GAZEBO GPU ACCELERATION"
	@echo "======================================="
	@echo ""
	@echo "  Gazebo renders the lidars on the GPU. Without their scans the Safety"
	@echo "  Boards have no proximity reading, and veto every command."
	@echo "  scripts/sim/gz_launch.sh, which starts Gazebo, selects the NVIDIA GPU"
	@echo "  when its driver is loaded. Check the GPU: make check-gpu"
	@echo ""
	@echo "======================================="
	@echo "  4. THE COASTAL CASE STUDY"
	@echo "======================================="
	@echo ""
	@echo "  The main scenario: a maritime intruder is sensed by four modalities"
	@echo "  (radar, RF, acoustic, EO), the TB-CSPN layer escalates it to a"
	@echo "  ConfirmedThreat, a human authorises interception, and the swarm acts."
	@echo ""
	@echo "  A) Automated run (sensing -> action, auto-authorised, with a report):"
	@echo "     Terminal 1: make demo-coastal"
	@echo "     Terminal 2: ./scripts/pipeline/test_pipeline.sh"
	@echo "     Health check: make check-coastal"
	@echo ""
	@echo "  B) Supervisor console, a demonstration (see docs/console.md):"
	@echo "     Terminal 1: make demo-coastal"
	@echo "     Terminal 2: rosbridge (workspace sourced)"
	@echo "     Terminal 3: python3 console/console_bridge_node.py"
	@echo "     Terminal 4: ./scripts/pipeline/demo_console.sh"
	@echo "     Then open console/decision_panel.html and press Authorise."
	@echo ""
	@echo "======================================="
	@echo "  5. ANALOG SAFETY BOARD (software-only)"
	@echo "======================================="
	@echo ""
	@echo "  Demonstrate the independent safety veto without PX4/Gazebo:"
	@echo "    Terminal 1: make demo-safety-board"
	@echo "    Terminal 2: make demo-safety-sensors"
	@echo "    Monitor:    ros2 topic echo /actuator_cmd_safe"
	@echo ""
	@echo "  For the command reference: make help"
	@echo ""
