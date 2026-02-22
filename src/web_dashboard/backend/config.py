"""
Copyright 2026 Luca D'Aurizio

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
@file config.py

Configuration settings for the Guarded Swarms Web Dashboard.

Provides centralized configuration management for server binding, CORS
policies, ROS 2 topic subscriptions, WebSocket behavior, and logging.
All environment-sensitive settings can be overridden via environment
variables, making the application suitable for both local development
and containerized deployment without code changes.

@author Luca D'Aurizio
"""

from typing import List
import os


class Settings:
    """
    Centralized configuration for the Guarded Swarms Web Dashboard.

    Class-level attributes are resolved at import time. Environment
    variables take precedence over the defaults defined here, allowing
    deployment-specific values to be injected without modifying source.
    """

    # ========================================================================
    # Server Configuration
    # ========================================================================

    HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("DASHBOARD_PORT", "8080"))
    RELOAD: bool = os.getenv("DASHBOARD_RELOAD", "true").lower() == "true"

    # ========================================================================
    # CORS Configuration
    # ========================================================================

    ALLOWED_ORIGINS: List[str] = ["*"]

    # ========================================================================
    # ROS 2 Topics
    # ========================================================================

    TOPIC_GEOMETRY_TOKENS: str = "/geometry_tokens"
    TOPIC_AUTH_TOKENS: str = "/auth_tokens"

    # ========================================================================
    # WebSocket Configuration
    # ========================================================================

    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS: int = 100
    WS_MESSAGE_QUEUE_SIZE: int = 100

    # ========================================================================
    # Workspace Configuration
    # ========================================================================

    WORKSPACE_PATH: str = os.getenv("WORKSPACE_PATH", "/workspace")

    ALLOWED_MAKE_COMMANDS: List[str] = [
        "build",
        "test",
        "clean",
        "format",
        "lint",
    ]

    # ========================================================================
    # Logging Configuration
    # ========================================================================

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# ============================================================================
# Global Settings Instance
# ============================================================================

settings = Settings()
