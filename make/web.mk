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
# web.mk - Web dashboard management (Development Only)
# ==============================================================================

.PHONY: web-dev web-stop web-logs web-status web-clean web-shell \
        web-ts-build web-ts-watch

web-dev:
	@echo "=========================================="
	@echo "Starting Web Dashboard"
	@echo "=========================================="
	@echo ""
	@echo "Dashboard available at:"
	@echo "  http://localhost:$(DASHBOARD_PORT)"
	@echo "Prerequisites: TypeScript compiled (make web-ts-build)"
	@echo ""
	@echo "Features:"
	@echo "  - Real-time token visualization"
	@echo "  - Live statistics and metrics"
	@echo "  - Agent performance monitoring"
	@echo ""
	@echo "Press Ctrl+C to stop."
	@echo ""
	@$(DOCKER_EXEC_IT) bash -c "$(FULL_SOURCE) && cd $(WORKSPACE_DIR)/$(WEB_BACKEND_DIR) && python3 -m uvicorn app:app --host 0.0.0.0 --port $(DASHBOARD_PORT) --reload"

web-stop:
	@echo "Stopping web dashboard..."
	@$(DOCKER_EXEC) bash -c "pkill -9 -f 'uvicorn.*app:app'" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "pkill -9 -f 'python3.*uvicorn'" 2>/dev/null || true
	@$(DOCKER_EXEC) bash -c "fuser -k $(DASHBOARD_PORT)/tcp 2>/dev/null || true"
	@sleep 1
	@echo "Dashboard stopped."

web-logs:
	@$(DOCKER_EXEC) bash -c "cat /tmp/web_dashboard.log 2>/dev/null || echo 'No log file found.'"

web-status:
	@echo "=========================================="
	@echo "Web Dashboard Status"
	@echo "=========================================="
	@echo ""
	@echo "[Backend Process]"
	@$(DOCKER_EXEC) bash -c "ps aux | grep -E 'uvicorn.*app:app' | grep -v grep || echo 'Not running'"
	@echo ""
	@echo "[Port $(DASHBOARD_PORT) Check]"
	@$(DOCKER_EXEC) bash -c "python3 -c \"import socket; s=socket.socket(); s.settimeout(0.5); result=s.connect_ex(('127.0.0.1',$(DASHBOARD_PORT))); s.close(); print('Port $(DASHBOARD_PORT) is open' if result==0 else 'Port $(DASHBOARD_PORT) is not accessible')\" 2>/dev/null"
	@echo ""
	@echo "[Runtime Versions]"
	@$(DOCKER_EXEC) bash -c "python3 --version | sed 's/^/  Python: /'"
	@$(DOCKER_EXEC) bash -c "bun --version | sed 's/^/  Bun: /'"
	@$(DOCKER_EXEC) bash -c "tsc --version 2>/dev/null | sed 's/^/  TypeScript: /' || echo '  TypeScript: Not found'"
	@echo ""
	@echo "[ROS2 Environment]"
	@$(DOCKER_EXEC) bash -c "$(ROS2_SOURCE) && python3 -c 'import rclpy; print(\"rclpy: Available\")' 2>/dev/null || echo 'rclpy: Not available'"
	@$(DOCKER_EXEC) bash -c "$(FULL_SOURCE) && python3 -c 'import $(COORDINATOR_PKG).msg; print(\"$(COORDINATOR_PKG): Available\")' 2>/dev/null || echo '$(COORDINATOR_PKG): Not built (run make ros2-build-ws)'"
	@echo ""
	@echo "[TypeScript Build]"
	@$(DOCKER_EXEC) bash -c "test -d $(WORKSPACE_DIR)/$(WEB_FRONTEND_DIR)/dist && echo 'dist/: Built' || echo 'dist/: Not built (run make web-ts-build)'"
	@echo ""
	@echo "[Server Performance]"
	@$(DOCKER_EXEC) bash -c "ps aux | grep -E 'uvicorn.*app:app' | grep -v grep | awk '{print \"  PID: \" \$$2 \"  |  CPU: \" \$$3 \"%  |  Memory: \" \$$4 \"%\"}' || echo '  Server not running'"
	@echo ""
	@echo "=========================================="
	@echo ""
	@echo "Dashboard URL: http://localhost:$(DASHBOARD_PORT)"
	@echo ""

web-clean:
	@echo "Cleaning web dashboard artifacts..."
	@$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR)/$(WEB_FRONTEND_DIR) && rm -rf node_modules .bun dist 2>/dev/null || true"
	@$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR)/$(WEB_BACKEND_DIR) && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"
	@echo "Cleanup complete."

web-shell:
	@$(DOCKER_EXEC_IT) bash -c "cd $(WORKSPACE_DIR)/$(WEB_BACKEND_DIR) && bash"

web-ts-build:
	@echo "Building TypeScript files..."
	@$(DOCKER_EXEC) bash -c "cd $(WORKSPACE_DIR)/$(WEB_FRONTEND_DIR) && bun run build"
	@echo "TypeScript compiled successfully."

web-ts-watch:
	@echo "=========================================="
	@echo "Watching TypeScript Files"
	@echo "=========================================="
	@echo ""
	@echo "Auto-compiling on file changes..."
	@echo "Press Ctrl+C to stop."
	@echo ""
	@$(DOCKER_EXEC_IT) bash -c "cd $(WORKSPACE_DIR)/$(WEB_FRONTEND_DIR) && bun run dev"
