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
@file ros2_bridge.py

ROS 2 to WebSocket bridge service.

Provides a thread-safe bridge between ROS 2 topic subscriptions and the
async WebSocket layer of the FastAPI application. ROS 2 spin runs in a
dedicated background daemon thread, while message forwarding is handled
via asyncio.run_coroutine_threadsafe to safely schedule async callbacks
on the main event loop without blocking the ROS 2 spin.

Architecture:
  1. ROS 2 node spins in a dedicated background daemon thread.
  2. Subscription callbacks receive raw ROS 2 messages and transform
     them into plain dictionaries suitable for JSON serialization.
  3. asyncio.run_coroutine_threadsafe schedules the async handler on
     the FastAPI event loop from within the ROS 2 thread.
  4. FastAPI handles WebSocket broadcasting in the main async context.

Thread safety:
  The event loop must be obtained from asyncio.get_running_loop() inside
  the FastAPI startup handler and passed explicitly to start_ros2_bridge.
  Passing None raises ValueError immediately to surface misconfiguration
  before the application reaches a broken state at runtime.

@author Luca D'Aurizio
"""

import rclpy
from rclpy.node import Node
from guarded_swarms_msgs.msg import GeometryToken, AuthToken
from typing import Callable, Optional
import asyncio
import threading
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# ROS 2 Bridge Node
# ============================================================================


class ROS2Bridge(Node):
    """
    ROS 2 node that bridges token topic subscriptions to the async WebSocket layer.

    Subscribes to geometry and authorization token topics, transforms each
    incoming ROS 2 message into a plain dictionary, and schedules the
    corresponding async callback on the FastAPI event loop using
    asyncio.run_coroutine_threadsafe.
    """

    # ========================================================================
    # Constants
    # ========================================================================

    QUEUE_SIZE = 10

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(
        self,
        geometry_callback: Callable,
        auth_callback: Callable,
        event_loop: asyncio.AbstractEventLoop,
        topic_geometry: str = "/geometry_tokens",
        topic_auth: str = "/auth_tokens",
    ):
        """
        Initializes the bridge node and creates both topic subscriptions.

        @param geometry_callback: Async callable invoked with the serialized
                                  geometry token dictionary on each message.
        @param auth_callback:     Async callable invoked with the serialized
                                  authorization token dictionary on each message.
        @param event_loop:        The running asyncio event loop obtained from
                                  the FastAPI startup handler. Used to schedule
                                  callbacks thread-safely.
        @param topic_geometry:    Full ROS 2 topic name for geometry tokens.
        @param topic_auth:        Full ROS 2 topic name for authorization tokens.
        """
        super().__init__("web_dashboard_bridge")

        self.geometry_callback = geometry_callback
        self.auth_callback = auth_callback
        self.event_loop = event_loop

        self.geometry_sub = self.create_subscription(
            GeometryToken, topic_geometry, self._on_geometry_token, self.QUEUE_SIZE
        )

        self.auth_sub = self.create_subscription(
            AuthToken, topic_auth, self._on_auth_token, self.QUEUE_SIZE
        )

        logger.info(f"ROS 2 Bridge initialized")
        logger.info(f"  Subscribed to: {topic_geometry}")
        logger.info(f"  Subscribed to: {topic_auth}")

    # ========================================================================
    # ROS 2 Callbacks
    # ========================================================================

    def _on_geometry_token(self, msg: GeometryToken):
        """
        Handles an incoming GeometryToken message from the ROS 2 subscription.

        Transforms the ROS 2 message into a plain dictionary and schedules
        the geometry async callback on the FastAPI event loop. Errors are
        caught and logged without re-raising to keep the spin loop alive.

        @param msg: The ROS 2 GeometryToken message received from the topic.
        """
        try:
            data = {
                "base_token": {
                    "token_id": msg.base_token.token_id,
                    "timestamp": int(msg.base_token.timestamp),
                    "agent_id": msg.base_token.agent_id,
                    "token_type": msg.base_token.token_type,
                    "signature": msg.base_token.signature,
                },
                "position": [float(x) for x in msg.position],
                "dimensions": [float(x) for x in msg.dimensions],
                "duration": float(msg.duration),
                "priority": int(msg.priority),
            }

            asyncio.run_coroutine_threadsafe(self.geometry_callback(data), self.event_loop)

        except Exception as e:
            logger.error(f"Error processing geometry token: {e}")

    def _on_auth_token(self, msg: AuthToken):
        """
        Handles an incoming AuthToken message from the ROS 2 subscription.

        Transforms the ROS 2 message into a plain dictionary and schedules
        the authorization async callback on the FastAPI event loop. Errors are
        caught and logged without re-raising to keep the spin loop alive.

        @param msg: The ROS 2 AuthToken message received from the topic.
        """
        try:
            data = {
                "base_token": {
                    "token_id": msg.base_token.token_id,
                    "timestamp": msg.base_token.timestamp,
                    "agent_id": msg.base_token.agent_id,
                    "token_type": msg.base_token.token_type,
                    "signature": msg.base_token.signature,
                },
                "geometry_token_id": msg.geometry_token_id,
                "approved": bool(msg.approved),
                "coordinator_id": msg.coordinator_id,
                "reason": msg.reason,
            }

            asyncio.run_coroutine_threadsafe(self.auth_callback(data), self.event_loop)

        except Exception as e:
            logger.error(f"Error processing auth token: {e}")


# ============================================================================
# Bridge Initialization
# ============================================================================


def start_ros2_bridge(
    geometry_cb: Callable,
    auth_cb: Callable,
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
    topic_geometry: str = "/geometry_tokens",
    topic_auth: str = "/auth_tokens",
) -> ROS2Bridge:
    """
    Initializes ROS 2 and starts the bridge node in a background daemon thread.

    Calls rclpy.init(), instantiates the ROS2Bridge node, and launches the
    spin loop in a named daemon thread so it is automatically terminated when
    the main process exits. The event_loop parameter is mandatory: omitting it
    raises ValueError immediately to surface the misconfiguration before the
    application reaches a broken runtime state.

    @param geometry_cb:    Async callable forwarded to ROS2Bridge for geometry tokens.
    @param auth_cb:        Async callable forwarded to ROS2Bridge for auth tokens.
    @param event_loop:     Running asyncio event loop from the FastAPI startup handler.
                           Must not be None.
    @param topic_geometry: Full ROS 2 topic name for geometry tokens.
    @param topic_auth:     Full ROS 2 topic name for authorization tokens.
    @return:               The initialized ROS2Bridge instance.
    @raises ValueError:    If event_loop is None.
    @raises Exception:     Re-raises any error thrown by rclpy.init().
    """
    if event_loop is None:
        raise ValueError(
            "event_loop is required. Must pass asyncio.get_running_loop() "
            "from FastAPI startup event to ensure thread-safe operation."
        )

    logger.info("Initializing ROS 2 bridge...")

    try:
        rclpy.init()
    except Exception as e:
        logger.error(f"Failed to initialize ROS 2: {e}")
        raise

    bridge = ROS2Bridge(geometry_cb, auth_cb, event_loop, topic_geometry, topic_auth)

    def spin():
        """
        Entry point for the ROS 2 background spin thread.

        Runs rclpy.spin until interrupted or until an unhandled exception
        occurs. All outcomes are logged to aid post-mortem diagnosis.
        """
        try:
            logger.info("Starting ROS 2 spin in background thread...")
            rclpy.spin(bridge)
        except KeyboardInterrupt:
            logger.info("ROS 2 spin interrupted")
        except Exception as e:
            logger.error(f"ROS 2 spin error: {e}")
        finally:
            logger.info("ROS 2 spin stopped")

    thread = threading.Thread(target=spin, daemon=True, name="ROS2BridgeThread")
    thread.start()

    logger.info("ROS 2 bridge started successfully")

    return bridge


# ============================================================================
# Shutdown Handler
# ============================================================================


def shutdown_ros2_bridge(bridge: ROS2Bridge):
    """
    Gracefully shuts down the ROS 2 bridge node and the rclpy context.

    Destroys the node and calls rclpy.shutdown() to release all ROS 2
    resources. Errors are caught and logged rather than re-raised so that
    a failed shutdown does not prevent the rest of the application teardown
    from completing.

    @param bridge: The ROS2Bridge instance to destroy.
    """
    try:
        logger.info("Shutting down ROS 2 bridge...")
        bridge.destroy_node()
        rclpy.shutdown()
        logger.info("ROS 2 bridge shutdown complete")
    except Exception as e:
        logger.error(f"Error during ROS 2 bridge shutdown: {e}")
