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
@file websocket.py

WebSocket router for real-time token streaming.

Manages WebSocket connection lifecycle, broadcasts token events to all
connected clients, and handles client-initiated keepalive messages.

Protocol:
  - Client connects to /ws.
  - Server sends a connection confirmation message.
  - Server broadcasts geometry, auth, and stats_update events automatically
    as they arrive from the ROS 2 bridge.
  - Client may send {"type": "ping"} for keepalive; server responds with
    {"type": "pong", "timestamp": <ms>}.

@author Luca D'Aurizio
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Set
import json
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


# ============================================================================
# Router Configuration
# ============================================================================

router = APIRouter(tags=["WebSocket"])


# ============================================================================
# Connection Manager
# ============================================================================


class ConnectionManager:
    """
    Manages the pool of active WebSocket connections.

    Handles connection acceptance, graceful and forced disconnection,
    broadcast to all clients, and targeted messaging to individual clients.
    Disconnected clients discovered during broadcast are removed from the
    pool automatically.
    """

    def __init__(self):
        """
        Initializes the manager with an empty connection pool and
        a timestamp registry for connection duration tracking.
        """
        self.active_connections: List[WebSocket] = []
        self.connection_timestamps: dict = {}
        logger.info("Connection manager initialized")

    async def connect(self, websocket: WebSocket):
        """
        Accepts a new WebSocket connection and registers it in the pool.

        @param websocket: The incoming WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_timestamps[id(websocket)] = time.time()
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """
        Removes a WebSocket connection from the active pool.

        Checks for existence before removal to make the operation idempotent.
        Logs the connection duration if a timestamp record is found.

        @param websocket: The WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            conn_id = id(websocket)
            if conn_id in self.connection_timestamps:
                duration = time.time() - self.connection_timestamps[conn_id]
                del self.connection_timestamps[conn_id]
                logger.info(
                    f"Client disconnected after {duration:.1f}s. "
                    f"Remaining connections: {len(self.active_connections)}"
                )

    async def broadcast(self, message: dict):
        """
        Serializes and sends a message to every connected client.

        Clients that fail to receive the message are collected and removed
        from the pool after the broadcast loop completes, preventing
        mid-iteration mutation of the connection list.

        @param message: Dictionary to serialize as JSON and send to all clients.
        """
        if not self.active_connections:
            return

        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to broadcast to client: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, message: dict, websocket: WebSocket):
        """
        Sends a message to a single specific client.

        Disconnects and removes the client from the pool if the send fails.

        @param message:   Dictionary to serialize as JSON and send.
        @param websocket: The target WebSocket connection.
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
            self.disconnect(websocket)

    async def close_all_connections(self):
        """
        Gracefully closes every active WebSocket connection.

        Iterates over a snapshot of the connection list so that removals
        triggered by disconnect() do not interfere with the loop. Intended
        for use during application shutdown.
        """
        logger.info(f"Closing {len(self.active_connections)} active connections")

        for connection in self.active_connections[:]:
            try:
                await connection.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self.disconnect(connection)

    def get_connection_count(self) -> int:
        """
        Gets current number of active connections.

        @return Number of connected clients
        """
        return len(self.active_connections)


# ============================================================================
# Global Manager Instance
# ============================================================================

manager = ConnectionManager()


# ============================================================================
# WebSocket Endpoint
# ============================================================================


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time token event streaming.

    Accepts the connection, sends an initial confirmation message, and
    then enters a receive loop. Incoming client messages are dispatched
    by type: "ping" receives a "pong" reply; "subscribe" is acknowledged
    via debug logging; unknown types are silently ignored with a warning.
    The loop terminates cleanly on WebSocketDisconnect and on any other
    unhandled exception, both of which trigger client removal from the pool.

    @param websocket: The WebSocket connection instance provided by FastAPI.
    """
    await manager.connect(websocket)

    try:
        await manager.send_personal(
            {
                "type": "connection",
                "status": "connected",
                "timestamp": int(time.time() * 1000),
                "message": "Connected to Guarded Swarms Dashboard",
            },
            websocket,
        )

        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                message_type = message.get("type")

                if message_type == "ping":
                    await manager.send_personal(
                        {"type": "pong", "timestamp": int(time.time() * 1000)}, websocket
                    )
                    logger.debug("Responded to client ping")

                elif message_type == "subscribe":
                    logger.debug(f"Client subscription request: {message}")

                else:
                    logger.debug(f"Unhandled message type: {message_type}")

            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from client: {data}")
            except Exception as e:
                logger.error(f"Error handling client message: {e}")

    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
        manager.disconnect(websocket)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# Broadcast Function
# ============================================================================


async def broadcast_event(event: dict):
    """
    Broadcasts a token or statistics event to all connected WebSocket clients.

    Called by app.py whenever a ROS 2 callback produces a new event payload.

    @param event: Event dictionary to serialize and broadcast.
    """
    await manager.broadcast(event)


async def close_all_connections():
    """
    Closes all active WebSocket connections via the global manager.

    Called by the FastAPI shutdown handler for graceful teardown.
    """
    await manager.close_all_connections()


# ============================================================================
# Utility Functions
# ============================================================================


def get_connection_count() -> int:
    """
    Returns the current number of active WebSocket connections.

    @return: Integer count of connected clients.
    """
    return manager.get_connection_count()
