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
@file app.py

FastAPI application for the Guarded Swarms Web Dashboard.

Provides the main application entry point for the real-time token
visualization dashboard. Integrates ROS 2 subscriptions with WebSocket
broadcasting to deliver live coordination data to web clients.

Architecture:
  1. FastAPI handles HTTP and WebSocket endpoints.
  2. ROS 2 bridge subscribes to token topics in a background thread.
  3. TokenProcessor transforms ROS 2 messages into web-friendly payloads.
  4. WebSocket router broadcasts events to all connected clients.
  5. Static file serving delivers the frontend SPA.

Typical usage via uvicorn:
  uvicorn app:app --host 0.0.0.0 --port 8765

@author Luca D'Aurizio
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import asyncio
import os
from pathlib import Path
import logging

from config import settings
from routers import websocket, makefile, system, demo
from services.ros2_bridge import start_ros2_bridge
from services.token_processor import TokenProcessor


# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL), format=settings.LOG_FORMAT)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Guarded Swarms Dashboard",
    description="Real-time visualization and control for token-based coordination",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================================
# Middleware Configuration
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Global State
# ============================================================================

processor = TokenProcessor()
system.set_token_processor(processor)
demo.set_token_processor(processor)

# ============================================================================
# ROS 2 Callback Handlers
# ============================================================================


async def on_geometry_token(data: dict):
    """
    Handles an incoming geometry token forwarded by the ROS 2 bridge.

    Passes the raw token data through the processor to produce a
    structured event, then broadcasts the result to all connected
    WebSocket clients. Errors are caught and logged without
    interrupting the event loop.

    @param data: Raw geometry token payload received from the ROS 2 topic.
    """
    try:
        event = processor.process_geometry_token(data)
        await websocket.broadcast_event(event)
    except Exception as e:
        logger.error(f"Error processing geometry token: {e}")


async def on_auth_token(data: dict):
    """
    Handles an incoming authorization token forwarded by the ROS 2 bridge.

    Passes the raw token data through the processor, broadcasts the
    resulting authorization event, and immediately follows it with an
    updated statistics snapshot so all clients stay in sync. Errors are
    caught and logged without interrupting the event loop.

    @param data: Raw authorization token payload received from the ROS 2 topic.
    """
    try:
        event = processor.process_auth_token(data)
        await websocket.broadcast_event(event)

        stats = processor.get_statistics()
        await websocket.broadcast_event({"event_type": "stats_update", "data": stats})
    except Exception as e:
        logger.error(f"Error processing auth token: {e}")


# ============================================================================
# Application Lifecycle
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """
    Initializes the application on startup.

    Starts the ROS 2 bridge on the running event loop and registers the
    geometry and authorization token callbacks. Logs the dashboard and
    API documentation URLs once the bridge is ready. Raises any exception
    that prevents the bridge from starting so that uvicorn aborts cleanly.
    """
    logger.info("Starting Guarded Swarms Web Dashboard...")
    logger.info(f"Subscribing to ROS 2 topics:")
    logger.info(f"   - {settings.TOPIC_GEOMETRY_TOKENS}")
    logger.info(f"   - {settings.TOPIC_AUTH_TOKENS}")

    try:
        loop = asyncio.get_running_loop()
        start_ros2_bridge(on_geometry_token, on_auth_token, event_loop=loop)

        logger.info(f"Dashboard ready at http://{settings.HOST}:{settings.PORT}")
        logger.info(f"API documentation at http://{settings.HOST}:{settings.PORT}/docs")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleans up resources on application shutdown.

    Closes all active WebSocket connections and terminates any demo
    process that may still be running. Cleanup errors are logged as
    warnings rather than raised, to allow the remaining shutdown steps
    to complete.
    """
    logger.info("Shutting down dashboard...")

    await websocket.close_all_connections()

    try:
        from routers import demo

        demo.kill_existing_demo()
        logger.info("Demo processes cleaned up")
    except Exception as e:
        logger.warning(f"Error cleaning up demo: {e}")

    logger.info("Shutdown complete")


# ============================================================================
# Router Registration
# ============================================================================

app.include_router(websocket.router, tags=["WebSocket"])
app.include_router(makefile.router, tags=["Build System"])
app.include_router(system.router, tags=["System"])
app.include_router(demo.router, tags=["Demo Control"])


# ============================================================================
# Static File Serving
# ============================================================================

frontend_path = Path(__file__).parent.parent / "frontend"

if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        """
        Serves the frontend SPA entry point.

        @return: FileResponse wrapping the compiled index.html.
        """
        return FileResponse(str(frontend_path / "index.html"))

    logger.info(f"Serving frontend from: {frontend_path}")
else:

    @app.get("/")
    async def root():
        """
        Fallback endpoint returned when the compiled frontend is not present.

        Provides basic API discovery information so that the backend remains
        usable in API-only deployments or during frontend build steps.

        @return: Dictionary containing the API version and key endpoint paths.
        """
        logger.warning("Frontend not found, serving API info only")
        return {
            "message": "Guarded Swarms Web Dashboard API",
            "version": "1.0.0",
            "endpoints": {
                "docs": "/docs",
                "websocket": "/ws",
                "health": "/health",
            },
        }


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
