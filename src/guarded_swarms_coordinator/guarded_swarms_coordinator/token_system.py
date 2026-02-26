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
@file token_system.py

Token system for guarded swarms coordination.

This module provides cryptographically-signed token classes for secure
multi-agent coordination in ROS 2 environments. Tokens enable agents to
request spatial areas (GeometryToken) and receive authorization decisions
(AuthToken) from a central coordinator.

The token system implements:
1. Unique identification via UUID4
2. Timestamp-based expiration tracking
3. Digital signature verification using SHA256
4. Spatial overlap detection for conflict resolution
5. Bidirectional ROS 2 message conversion

@author Luca D'Aurizio
"""

import hashlib
import time
import uuid
from typing import Optional, List

from guarded_swarms_coordinator.msg import Token as TokenMsg
from guarded_swarms_coordinator.msg import GeometryToken as GeometryTokenMsg
from guarded_swarms_coordinator.msg import AuthToken as AuthTokenMsg


class Token:
    """
    Base token wrapper with digital signature support.

    Wraps ROS 2 Token messages and provides cryptographic integrity verification.
    All specialized tokens (GeometryToken, AuthToken) inherit from this base class.
    """

    def __init__(self, agent_id: str, token_type: str = "geometry", token_id: Optional[str] = None):
        """
        Initialize a new token.

        @param agent_id Unique identifier of the agent creating this token
        @param token_type Type of token ("geometry" or "authorization")
        @param token_id Optional custom token ID (auto-generated if None)
        """
        self.token_id = token_id if token_id else str(uuid.uuid4())
        self.timestamp = self._get_timestamp_microseconds()
        self.agent_id = agent_id
        self.token_type = token_type
        self.signature = self._generate_signature()

    def _get_timestamp_microseconds(self) -> int:
        """
        Gets current ROS time in microseconds.

        ROS 2 expects timestamps in microseconds since epoch for proper
        time synchronization across the distributed system.

        @return Current time in microseconds
        """
        return int(time.time() * 1_000_000)

    def _generate_signature(self) -> str:
        """
        Generates SHA256 signature for token integrity.

        Creates a cryptographic hash of the token's immutable fields
        (ID, timestamp, agent ID, type) to enable tamper detection.

        @return 64-character hexadecimal SHA256 hash
        """
        payload = f"{self.token_id}{self.timestamp}{self.agent_id}{self.token_type}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def verify_signature(self) -> bool:
        """
        Verifies token signature integrity.

        Recomputes the expected signature and compares against stored value
        to detect tampering or corruption.

        @return True if signature is valid, False otherwise
        """
        expected_signature = hashlib.sha256(
            f"{self.token_id}{self.timestamp}{self.agent_id}{self.token_type}".encode()
        ).hexdigest()
        return self.signature == expected_signature

    def to_msg(self) -> TokenMsg:
        """
        Converts to ROS 2 Token message.

        @return TokenMsg ready for publishing over ROS 2 topics
        """
        msg = TokenMsg()
        msg.token_id = self.token_id
        msg.timestamp = self.timestamp
        msg.agent_id = self.agent_id
        msg.token_type = self.token_type
        msg.signature = self.signature
        return msg

    @staticmethod
    def from_msg(msg: TokenMsg) -> "Token":
        """
        Creates Token from ROS 2 message.

        @param msg ROS 2 TokenMsg instance
        @return Token instance
        """
        token = Token.__new__(Token)
        token.token_id = msg.token_id
        token.timestamp = msg.timestamp
        token.agent_id = msg.agent_id
        token.token_type = msg.token_type
        token.signature = msg.signature
        return token

    def is_expired(self, timeout_ms: int = 300) -> bool:
        """
        Checks if token has exceeded its validity period.

        @param timeout_ms Expiration timeout in milliseconds (default: 300ms)
        @return True if token age exceeds timeout
        """
        current_time = self._get_timestamp_microseconds()
        age_ms = (current_time - self.timestamp) / 1000
        return age_ms > timeout_ms

    def __repr__(self) -> str:
        return (
            f"Token(id={self.token_id[:8]}..., "
            f"agent={self.agent_id}, "
            f"type={self.token_type})"
        )


class GeometryToken(Token):
    """
    Geometry token for spatial area requests.

    Represents an agent's request to occupy a specific 3D volume in space
    for a specified duration. Used by the coordinator to detect and resolve
    spatial conflicts between multiple agents.
    """

    # ========================================================================
    # Constants
    # ========================================================================
    PRIORITY_EMERGENCY = 10
    PRIORITY_HIGH = 7
    PRIORITY_NORMAL = 5
    PRIORITY_LOW = 3
    PRIORITY_MINIMAL = 0

    def __init__(
        self,
        agent_id: str,
        position: List[float],
        dimensions: List[float],
        duration: float,
        priority: int = 5,
        token_id: Optional[str] = None,
    ):
        """
        Initialize geometry token with spatial parameters.

        @param agent_id Agent requesting the spatial area
        @param position [x, y, z] center point in meters
        @param dimensions [width, height, depth] in meters
        @param duration Time needed for this area in seconds
        @param priority Priority level 0-10 (default: 5 = normal)
        @param token_id Optional custom token ID

        @throws ValueError if position/dimensions not 3D or duration invalid
        """
        super().__init__(agent_id, token_type="geometry", token_id=token_id)

        if len(position) != 3:
            raise ValueError("Position must be [x, y, z]")
        if len(dimensions) != 3:
            raise ValueError("Dimensions must be [width, height, depth]")
        if duration <= 0:
            raise ValueError("Duration must be positive")
        if not 0 <= priority <= 10:
            raise ValueError("Priority must be between 0 and 10")

        self.position = position
        self.dimensions = dimensions
        self.duration = duration
        self.priority = priority

    def to_msg(self) -> GeometryTokenMsg:
        """
        Converts to ROS 2 GeometryToken message.

        @return GeometryTokenMsg ready for publishing
        """
        msg = GeometryTokenMsg()
        msg.base_token = super().to_msg()
        msg.position = self.position
        msg.dimensions = self.dimensions
        msg.duration = self.duration
        msg.priority = self.priority
        return msg

    @staticmethod
    def from_msg(msg: GeometryTokenMsg) -> "GeometryToken":
        """
        Creates GeometryToken from ROS 2 message.

        @param msg ROS 2 GeometryTokenMsg instance
        @return GeometryToken instance
        """
        base = Token.from_msg(msg.base_token)
        token = GeometryToken.__new__(GeometryToken)
        token.token_id = base.token_id
        token.timestamp = base.timestamp
        token.agent_id = base.agent_id
        token.token_type = base.token_type
        token.signature = base.signature
        token.position = list(msg.position)
        token.dimensions = list(msg.dimensions)
        token.duration = msg.duration
        token.priority = msg.priority
        return token

    def overlaps_with(self, other: "GeometryToken") -> bool:
        """
        Detects spatial overlap with another geometry token.

        Uses AABB (Axis-Aligned Bounding Box) collision detection to determine
        if two requested volumes intersect in 3D space.

        @param other Another GeometryToken to check against
        @return True if bounding boxes overlap
        """
        self_min = [self.position[i] - self.dimensions[i] / 2 for i in range(3)]
        self_max = [self.position[i] + self.dimensions[i] / 2 for i in range(3)]

        other_min = [other.position[i] - other.dimensions[i] / 2 for i in range(3)]
        other_max = [other.position[i] + other.dimensions[i] / 2 for i in range(3)]

        for i in range(3):
            if self_max[i] < other_min[i] or self_min[i] > other_max[i]:
                return False

        return True

    def __repr__(self) -> str:
        return (
            f"GeometryToken(id={self.token_id[:8]}..., "
            f"agent={self.agent_id}, "
            f"pos={self.position}, "
            f"priority={self.priority})"
        )


class AuthToken(Token):
    """
    Authorization token for coordinator decisions.

    Represents the coordinator's approval or rejection of a spatial request.
    Links back to the original GeometryToken and provides reasoning for
    the decision.
    """

    def __init__(
        self,
        agent_id: str,
        geometry_token_id: str,
        approved: bool,
        coordinator_id: str,
        reason: str = "",
        token_id: Optional[str] = None,
    ):
        """
        Initialize authorization token.

        @param agent_id Agent that made the original geometry request
        @param geometry_token_id ID of the geometry token being authorized
        @param approved True if request approved, False if rejected
        @param coordinator_id ID of coordinator making this decision
        @param reason Human-readable reason for decision
        @param token_id Optional custom token ID
        """
        super().__init__(agent_id, token_type="authorization", token_id=token_id)
        self.geometry_token_id = geometry_token_id
        self.approved = approved
        self.coordinator_id = coordinator_id
        self.reason = reason if reason else ("approved" if approved else "rejected")

    def to_msg(self) -> AuthTokenMsg:
        """
        Converts to ROS 2 AuthToken message.

        @return AuthTokenMsg ready for publishing
        """
        msg = AuthTokenMsg()
        msg.base_token = super().to_msg()
        msg.geometry_token_id = self.geometry_token_id
        msg.approved = self.approved
        msg.coordinator_id = self.coordinator_id
        msg.reason = self.reason
        return msg

    @staticmethod
    def from_msg(msg: AuthTokenMsg) -> "AuthToken":
        """
        Creates AuthToken from ROS 2 message.

        @param msg ROS 2 AuthTokenMsg instance
        @return AuthToken instance
        """
        base = Token.from_msg(msg.base_token)
        token = AuthToken.__new__(AuthToken)
        token.token_id = base.token_id
        token.timestamp = base.timestamp
        token.agent_id = base.agent_id
        token.token_type = base.token_type
        token.signature = base.signature
        token.geometry_token_id = msg.geometry_token_id
        token.approved = msg.approved
        token.coordinator_id = msg.coordinator_id
        token.reason = msg.reason
        return token

    def __repr__(self) -> str:
        status = "✓" if self.approved else "✗"
        return (
            f"AuthToken({status} id={self.token_id[:8]}..., "
            f"geo={self.geometry_token_id[:8]}..., "
            f"by={self.coordinator_id})"
        )


# ============================================================================
# Utility Functions
# ============================================================================
def create_geometry_token(
    agent_id: str,
    x: float,
    y: float,
    z: float,
    width: float,
    height: float,
    depth: float,
    duration: float,
    priority: int = 5,
) -> GeometryToken:
    """
    Convenience function to create a geometry token.

    @param agent_id Agent identifier
    @param x, y, z Position coordinates in meters
    @param width, height, depth Bounding box dimensions in meters
    @param duration Duration in seconds
    @param priority Priority level 0-10 (default: 5)
    @return GeometryToken instance
    """
    return GeometryToken(
        agent_id=agent_id,
        position=[x, y, z],
        dimensions=[width, height, depth],
        duration=duration,
        priority=priority,
    )


def create_auth_token(
    geometry_token: GeometryToken, approved: bool, coordinator_id: str, reason: str = ""
) -> AuthToken:
    """
    Convenience function to create an authorization token.

    @param geometry_token The geometry token being authorized
    @param approved Approval decision
    @param coordinator_id Coordinator making the decision
    @param reason Optional reason string
    @return AuthToken instance
    """
    return AuthToken(
        agent_id=geometry_token.agent_id,
        geometry_token_id=geometry_token.token_id,
        approved=approved,
        coordinator_id=coordinator_id,
        reason=reason,
    )
