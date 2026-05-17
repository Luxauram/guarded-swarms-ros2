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
# docker.mk - Docker container management
#
# SUPPORTED PLATFORM: Ubuntu host (any LTS: 22.04 or 24.04) + Docker Engine.
# The container runs Ubuntu 22.04 + ROS 2 Humble internally regardless of
# the host Ubuntu version.
#
# Windows and macOS are NOT supported:
#   - Gazebo requires direct OpenGL/GPU access that Docker cannot provide
#     reliably on those platforms.
#   - On Windows (WSL2): Gazebo renders at unusable framerates.
#   - On macOS: Apple dropped NVIDIA GPU support in 2019; lidar will not work.
# ==============================================================================

.PHONY: docker-start docker-stop docker-restart docker-shell docker-logs \
        docker-status docker-clean \
        docker-start-nvidia docker-stop-nvidia

docker-start:
	@echo "Starting container..."
	@cd $(DOCKER_DIR) && docker-compose up -d
	@sleep 1
	@echo "Container started. Use 'make docker-shell' to access shell."

docker-stop:
	@echo "Stopping container..."
	@cd $(DOCKER_DIR) && docker-compose down
	@echo "Container stopped."

docker-restart: docker-stop docker-start

docker-shell:
	@echo "Opening interactive shell in container."
	@echo "Type 'exit' to return to host."
	@echo ""
	@$(DOCKER_EXEC_IT) bash

docker-logs:
	@cd $(DOCKER_DIR) && docker-compose logs --tail=100

docker-status:
	@echo "Container status:"
	@echo ""
	@docker ps -a | grep $(CONTAINER_NAME) || echo "Container not found."

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
	@cd $(DOCKER_DIR) && docker-compose down -v
	@echo "Cleanup complete."

# ------------------------------------------------------------------------------
# NVIDIA GPU (Ubuntu + NVIDIA GPU only)
# Not supported on macOS. Not supported on Windows/WSL2.
# ------------------------------------------------------------------------------

docker-start-nvidia:
	@echo "=========================================="
	@echo "Starting container with NVIDIA GPU support"
	@echo "=========================================="
	@echo ""
	@echo "Requirements:"
	@echo "  - Ubuntu host (22.04 or 24.04)"
	@echo "  - NVIDIA GPU (GeForce, Quadro, or Tesla)"
	@echo "  - NVIDIA drivers installed on the host"
	@echo "  - NVIDIA Container Toolkit installed"
	@echo "    https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
	@echo ""
	@echo "NOT supported on macOS (Apple dropped NVIDIA support in 2019)."
	@echo "NOT supported on Windows/WSL2 (GPU passthrough is unreliable for Gazebo)."
	@echo ""
	@echo "Run 'make check-gpu' to verify your system before proceeding."
	@echo ""
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.yml -f docker-compose.nvidia.yml up -d
	@sleep 1
	@echo ""
	@echo "Container started with GPU acceleration."
	@echo "Use 'make docker-shell' to access shell."
	@echo "Use 'make px4-gui-uav' or 'make px4-gui-ugv' to launch with full lidar support."

docker-stop-nvidia:
	@echo "Stopping NVIDIA container..."
	@cd $(DOCKER_DIR) && docker-compose -f docker-compose.yml -f docker-compose.nvidia.yml down
	@echo "Container stopped."
