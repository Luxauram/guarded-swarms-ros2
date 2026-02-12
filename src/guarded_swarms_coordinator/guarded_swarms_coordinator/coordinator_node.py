#!/usr/bin/env python3
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
@file coordinator_node.py

Coordinator node for token validation and spatial arbitration.

This node implements the central coordination logic for guarded swarms,
managing spatial conflict resolution and authorization decisions across
multiple monitoring agents.

The coordination workflow:
1. Subscribe to geometry tokens from all agents
2. Validate cryptographic signatures (SHA256)
3. Buffer tokens within 300ms concurrency window
4. Detect spatial conflicts using AABB collision detection
5. Apply first-come-first-serve arbitration policy
6. Publish authorization tokens (approve/reject decisions)

Typical usage:
    ros2 run guarded_swarms_coordinator coordinator_node \\
        --ros-args -p coordinator_id:=coordinator_R1

@author Luca D'Aurizio
"""

import rclpy
from rclpy.node import Node
from guarded_swarms_coordinator.msg import GeometryToken as GeometryTokenMsg
from guarded_swarms_coordinator.msg import AuthToken as AuthTokenMsg
from guarded_swarms_coordinator.token import GeometryToken, create_auth_token
from collections import deque
import time


class CoordinatorNode(Node):
    """
    ROS 2 coordinator node for multi-agent spatial coordination.

    Manages temporal and spatial arbitration using a sliding window buffer
    and AABB-based conflict detection. Enforces one active token per agent
    with automatic replacement on new requests.
    """

    # ========================================================================
    # Constants
    # ========================================================================

    TOPIC_GEOMETRY_TOKENS = "/geometry_tokens"
    TOPIC_AUTH_TOKENS = "/auth_tokens"
    QUEUE_SIZE = 10

    CONCURRENCY_WINDOW_MS = 300
    BUFFER_CLEANUP_RATE_HZ = 10

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(self, coordinator_id: str = "coordinator_R1"):
        """
        Initialize coordinator node with arbitration structures.

        @param coordinator_id Unique coordinator identifier
        """
        super().__init__(f"{coordinator_id}_node")

        self.coordinator_id = coordinator_id

        self.token_buffer = deque()
        self.approved_tokens = {}

        self.geometry_subscriber = self.create_subscription(
            GeometryTokenMsg,
            self.TOPIC_GEOMETRY_TOKENS,
            self.geometry_token_callback,
            self.QUEUE_SIZE,
        )

        self.auth_publisher = self.create_publisher(
            AuthTokenMsg, self.TOPIC_AUTH_TOKENS, self.QUEUE_SIZE
        )

        cleanup_period = 1.0 / self.BUFFER_CLEANUP_RATE_HZ
        self.cleanup_timer = self.create_timer(cleanup_period, self.cleanup_expired_tokens)

        self.get_logger().info(
            f"{self.coordinator_id} initialized. "
            f"Concurrency window: {self.CONCURRENCY_WINDOW_MS}ms"
        )

    # ========================================================================
    # Token Processing
    # ========================================================================

    def geometry_token_callback(self, msg: GeometryTokenMsg):
        """
        Processes incoming geometry token and makes authorization decision.

        Validates signature, checks expiration, detects spatial conflicts,
        and publishes authorization result.

        @param msg Incoming GeometryTokenMsg from agent
        """
        token = GeometryToken.from_msg(msg)

        self.get_logger().info(
            f"Received token from {token.agent_id}: "
            f"id={token.token_id[:8]}..., "
            f"pos={token.position}"
        )

        if not self._validate_signature(token):
            self._reject_token(token, "invalid_signature")
            return

        if token.is_expired(timeout_ms=self.CONCURRENCY_WINDOW_MS):
            self._reject_token(token, "expired")
            return

        self.token_buffer.append(token)

        conflict_detected, conflicting_token = self._detect_conflict(token)

        if conflict_detected:
            self._reject_token(token, f"conflict_with_{conflicting_token.agent_id}")
        else:
            self._approve_token(token)

    def _validate_signature(self, token: GeometryToken) -> bool:
        """
        Validates token cryptographic signature.

        @param token GeometryToken to validate
        @return True if signature is valid, False otherwise
        """
        is_valid = token.verify_signature()

        if not is_valid:
            self.get_logger().warn(
                f"Invalid signature detected for token {token.token_id[:8]}... "
                f"from {token.agent_id}"
            )

        return is_valid

    def _detect_conflict(self, token: GeometryToken) -> tuple[bool, GeometryToken | None]:
        """
        Detects spatial conflicts with currently approved tokens.

        Uses AABB collision detection to check if requested volume intersects
        with any active approved volumes from other agents.

        @param token GeometryToken to check for conflicts
        @return Tuple of (conflict_detected, conflicting_token)
        """
        for approved_id, approved_token in self.approved_tokens.items():
            if approved_token.agent_id == token.agent_id:
                continue

            if approved_token.is_expired(timeout_ms=int(approved_token.duration * 1000)):
                continue

            if token.overlaps_with(approved_token):
                self.get_logger().warn(
                    f"Conflict detected: {token.agent_id} overlaps with "
                    f"{approved_token.agent_id} (token {approved_id[:8]}...)"
                )
                return True, approved_token

        return False, None

    # ========================================================================
    # Authorization Decisions
    # ========================================================================

    def _approve_token(self, token: GeometryToken):
        """
        Approves geometry token and publishes authorization.

        Automatically replaces any previous token from the same agent,
        enforcing the one-token-per-agent policy.

        @param token GeometryToken to approve
        """
        old_tokens = [
            tid for tid, t in self.approved_tokens.items() if t.agent_id == token.agent_id
        ]

        for old_tid in old_tokens:
            removed = self.approved_tokens.pop(old_tid)
            self.get_logger().debug(
                f"Auto-replaced old token {old_tid[:8]}... from {token.agent_id}"
            )

        self.approved_tokens[token.token_id] = token

        auth_token = create_auth_token(
            geometry_token=token,
            approved=True,
            coordinator_id=self.coordinator_id,
            reason="approved",
        )

        auth_msg = auth_token.to_msg()
        self.auth_publisher.publish(auth_msg)

        self.get_logger().info(
            f"✓ APPROVED: {token.agent_id} token {token.token_id[:8]}... "
            f"at pos={token.position}"
        )

    def _reject_token(self, token: GeometryToken, reason: str):
        """
        Rejects geometry token and publishes denial.

        @param token GeometryToken to reject
        @param reason Human-readable rejection reason
        """
        auth_token = create_auth_token(
            geometry_token=token,
            approved=False,
            coordinator_id=self.coordinator_id,
            reason=reason,
        )

        auth_msg = auth_token.to_msg()
        self.auth_publisher.publish(auth_msg)

        self.get_logger().warn(
            f"✗ REJECTED: {token.agent_id} token {token.token_id[:8]}... " f"reason: {reason}"
        )

    # ========================================================================
    # Buffer Management
    # ========================================================================

    def cleanup_expired_tokens(self):
        """
        Removes expired tokens from buffer and approved list.

        Maintains buffer hygiene by removing tokens older than the concurrency
        window and approved tokens that have exceeded their duration.
        """
        current_time_us = int(time.time() * 1_000_000)

        while self.token_buffer:
            oldest_token = self.token_buffer[0]
            age_ms = (current_time_us - oldest_token.timestamp) / 1000

            if age_ms > self.CONCURRENCY_WINDOW_MS:
                self.token_buffer.popleft()
            else:
                break

        expired_tokens = []
        for token_id, token in self.approved_tokens.items():
            duration_ms = token.duration * 1000
            if token.is_expired(timeout_ms=int(duration_ms)):
                expired_tokens.append(token_id)

        for token_id in expired_tokens:
            removed_token = self.approved_tokens.pop(token_id)
            self.get_logger().debug(
                f"Removed expired approval: {removed_token.agent_id} " f"token {token_id[:8]}..."
            )

    # ========================================================================
    # Diagnostics
    # ========================================================================

    def get_buffer_stats(self) -> dict:
        """
        Gets current buffer statistics for monitoring.

        @return Dictionary with buffer size and approved token count
        """
        return {
            "buffer_size": len(self.token_buffer),
            "approved_count": len(self.approved_tokens),
            "coordinator_id": self.coordinator_id,
        }


# ============================================================================
# Main Function
# ============================================================================


def main(args=None):
    """
    Main entry point for coordinator node.

    Initializes ROS 2, parses coordinator ID from parameters, and spins
    the node until shutdown. Prints final statistics on exit.

    @param args Command line arguments (unused, handled by ROS 2)
    """
    rclpy.init(args=args)

    temp_node = rclpy.create_node("temp_param_reader")
    temp_node.declare_parameter("coordinator_id", "coordinator_R1")
    coordinator_id = temp_node.get_parameter("coordinator_id").value
    temp_node.destroy_node()

    node = CoordinatorNode(coordinator_id=coordinator_id)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info(f"{coordinator_id} shutting down")
    finally:
        stats = node.get_buffer_stats()
        node.get_logger().info(
            f"Final stats: {stats['buffer_size']} in buffer, " f"{stats['approved_count']} approved"
        )
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
