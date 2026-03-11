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
# ==============================================================================

.PHONY: docker-start docker-stop docker-restart docker-shell docker-logs \
        docker-status docker-clean

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
