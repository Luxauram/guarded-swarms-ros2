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
# web.mk - Web dashboard management (native Ubuntu)
# ==============================================================================

.PHONY: web-dev web-stop web-status web-clean web-ts-build web-ts-watch

web-dev:
	@echo "=========================================="
	@echo "Starting Web Dashboard"
	@echo "=========================================="
	@echo ""
	@echo "Dashboard available at: http://localhost:$(DASHBOARD_PORT)"
	@echo "Prerequisites: TypeScript compiled (make web-ts-build)"
	@echo ""
	@echo "Press Ctrl+C to stop."
	@echo ""
	@bash -c "$(FULL_SOURCE) && cd $(WEB_BACKEND_DIR) && python3 -m uvicorn app:app --host 0.0.0.0 --port $(DASHBOARD_PORT) --reload"

web-stop:
	@echo "Stopping web dashboard..."
	@pkill -9 -f 'uvicorn.*app:app' 2>/dev/null || true
	@pkill -9 -f 'python3.*uvicorn' 2>/dev/null || true
	@fuser -k $(DASHBOARD_PORT)/tcp 2>/dev/null || true
	@echo "Dashboard stopped."

web-status:
	@echo "=========================================="
	@echo "Web Dashboard Status"
	@echo "=========================================="
	@echo ""
	@echo "[Backend Process]"
	@ps aux | grep -E 'uvicorn.*app:app' | grep -v grep || echo "Not running"
	@echo ""
	@echo "[Port $(DASHBOARD_PORT)]"
	@python3 -c "import socket; s=socket.socket(); s.settimeout(0.5); r=s.connect_ex(('127.0.0.1',$(DASHBOARD_PORT))); s.close(); print('Open' if r==0 else 'Not accessible')" 2>/dev/null
	@echo ""
	@echo "[TypeScript Build]"
	@test -d $(WEB_FRONTEND_DIR)/dist && echo "dist/: Built" || echo "dist/: Not built (run make web-ts-build)"
	@echo ""
	@echo "Dashboard URL: http://localhost:$(DASHBOARD_PORT)"

web-clean:
	@echo "Cleaning web dashboard artifacts..."
	@cd $(WEB_FRONTEND_DIR) && rm -rf node_modules .bun dist 2>/dev/null || true
	@find $(WEB_BACKEND_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleanup complete."

web-ts-build:
	@echo "Building TypeScript files..."
	@cd $(WEB_FRONTEND_DIR) && bun run build
	@echo "TypeScript compiled successfully."

web-ts-watch:
	@echo "Watching TypeScript files (auto-compile on change)..."
	@echo "Press Ctrl+C to stop."
	@cd $(WEB_FRONTEND_DIR) && bun run dev