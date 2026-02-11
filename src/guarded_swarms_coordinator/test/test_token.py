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
@file test_token_system.py

Unit tests for the token system.

Comprehensive test suite covering:
- UUID generation and custom ID assignment
- SHA256 signature generation and verification
- Token expiration logic with configurable timeouts
- ROS 2 message bidirectional conversion
- AABB spatial overlap detection
- Authorization token creation and reasoning

@author Luca D'Aurizio
"""

import time
import unittest
from guarded_swarms_coordinator.token import Token, GeometryToken, AuthToken
from guarded_swarms_coordinator.token import create_geometry_token, create_auth_token


class TestToken(unittest.TestCase):
    """Test suite for base Token class functionality."""

    def test_token_creation(self):
        """Verifies auto-generated UUID4 tokens are created correctly."""
        token = Token(agent_id="agent_A")

        self.assertIsNotNone(token.token_id)
        self.assertEqual(len(token.token_id), 36)
        self.assertEqual(token.agent_id, "agent_A")
        self.assertEqual(token.token_type, "geometry")
        self.assertIsNotNone(token.signature)
        self.assertEqual(len(token.signature), 64)

    def test_custom_token_id(self):
        """Verifies custom token IDs override auto-generation."""
        custom_id = "custom-token-123"
        token = Token(agent_id="agent_B", token_id=custom_id)

        self.assertEqual(token.token_id, custom_id)

    def test_signature_generation(self):
        """Verifies SHA256 signature integrity and tamper detection."""
        token = Token(agent_id="agent_C")

        original_sig = token.signature
        self.assertTrue(token.verify_signature())

        token.signature = "invalid_signature"
        self.assertFalse(token.verify_signature())

        token.signature = original_sig
        self.assertTrue(token.verify_signature())

    def test_token_expiration(self):
        """Verifies timeout-based expiration logic."""
        token = Token(agent_id="agent_D")

        self.assertFalse(token.is_expired(timeout_ms=300))

        token.timestamp = token.timestamp - 500_000
        self.assertTrue(token.is_expired(timeout_ms=300))

    def test_to_from_msg(self):
        """Verifies lossless ROS 2 message serialization."""
        original = Token(agent_id="agent_E", token_type="authorization")

        msg = original.to_msg()
        restored = Token.from_msg(msg)

        self.assertEqual(original.token_id, restored.token_id)
        self.assertEqual(original.timestamp, restored.timestamp)
        self.assertEqual(original.agent_id, restored.agent_id)
        self.assertEqual(original.token_type, restored.token_type)
        self.assertEqual(original.signature, restored.signature)


class TestGeometryToken(unittest.TestCase):
    """Test suite for GeometryToken spatial functionality."""

    def test_geometry_token_creation(self):
        """Verifies geometry tokens store spatial parameters correctly."""
        token = GeometryToken(
            agent_id="agent_A", position=[1.0, 2.0, 3.0], dimensions=[0.5, 0.5, 1.0], duration=10.0
        )

        self.assertEqual(token.position, [1.0, 2.0, 3.0])
        self.assertEqual(token.dimensions, [0.5, 0.5, 1.0])
        self.assertEqual(token.duration, 10.0)
        self.assertEqual(token.token_type, "geometry")

    def test_invalid_position(self):
        """Verifies position must be 3D vector."""
        with self.assertRaises(ValueError):
            GeometryToken(
                agent_id="agent_B",
                position=[1.0, 2.0],
                dimensions=[0.5, 0.5, 1.0],
                duration=5.0,
            )

    def test_invalid_duration(self):
        """Verifies duration must be positive."""
        with self.assertRaises(ValueError):
            GeometryToken(
                agent_id="agent_C",
                position=[0.0, 0.0, 0.0],
                dimensions=[1.0, 1.0, 1.0],
                duration=-5.0,
            )

    def test_overlap_detection_no_overlap(self):
        """Verifies AABB correctly detects non-overlapping volumes."""
        token1 = GeometryToken(
            agent_id="agent_A", position=[0.0, 0.0, 0.0], dimensions=[1.0, 1.0, 1.0], duration=5.0
        )

        token2 = GeometryToken(
            agent_id="agent_B", position=[5.0, 5.0, 5.0], dimensions=[1.0, 1.0, 1.0], duration=5.0
        )

        self.assertFalse(token1.overlaps_with(token2))
        self.assertFalse(token2.overlaps_with(token1))

    def test_overlap_detection_overlap(self):
        """Verifies AABB correctly detects intersecting volumes."""
        token1 = GeometryToken(
            agent_id="agent_A", position=[0.0, 0.0, 0.0], dimensions=[2.0, 2.0, 2.0], duration=5.0
        )

        token2 = GeometryToken(
            agent_id="agent_B", position=[1.0, 1.0, 1.0], dimensions=[2.0, 2.0, 2.0], duration=5.0
        )

        self.assertTrue(token1.overlaps_with(token2))
        self.assertTrue(token2.overlaps_with(token1))

    def test_overlap_detection_edge_touch(self):
        """Verifies AABB treats edge contact as overlap for safety."""
        token1 = GeometryToken(
            agent_id="agent_A", position=[0.0, 0.0, 0.0], dimensions=[1.0, 1.0, 1.0], duration=5.0
        )

        token2 = GeometryToken(
            agent_id="agent_B", position=[1.0, 0.0, 0.0], dimensions=[1.0, 1.0, 1.0], duration=5.0
        )

        self.assertTrue(token1.overlaps_with(token2))

    def test_geometry_to_from_msg(self):
        """Verifies lossless ROS 2 message serialization for geometry tokens."""
        original = create_geometry_token(
            agent_id="agent_X", x=1.0, y=2.0, z=3.0, width=0.5, height=0.5, depth=1.0, duration=15.0
        )

        msg = original.to_msg()
        restored = GeometryToken.from_msg(msg)

        self.assertEqual(original.token_id, restored.token_id)
        self.assertEqual(original.position, restored.position)
        self.assertEqual(original.dimensions, restored.dimensions)
        self.assertEqual(original.duration, restored.duration)


class TestAuthToken(unittest.TestCase):
    """Test suite for AuthToken authorization functionality."""

    def test_auth_token_creation(self):
        """Verifies authorization tokens link to geometry requests."""
        geo_token = create_geometry_token(
            agent_id="agent_A", x=0.0, y=0.0, z=0.0, width=1.0, height=1.0, depth=1.0, duration=10.0
        )

        auth_token = create_auth_token(
            geometry_token=geo_token,
            approved=True,
            coordinator_id="coordinator_R1",
            reason="approved",
        )

        self.assertEqual(auth_token.agent_id, "agent_A")
        self.assertEqual(auth_token.geometry_token_id, geo_token.token_id)
        self.assertTrue(auth_token.approved)
        self.assertEqual(auth_token.coordinator_id, "coordinator_R1")
        self.assertEqual(auth_token.reason, "approved")
        self.assertEqual(auth_token.token_type, "authorization")

    def test_auth_token_rejection(self):
        """Verifies authorization tokens can represent rejections."""
        geo_token = create_geometry_token(
            agent_id="agent_B", x=0.0, y=0.0, z=0.0, width=1.0, height=1.0, depth=1.0, duration=10.0
        )

        auth_token = create_auth_token(
            geometry_token=geo_token,
            approved=False,
            coordinator_id="coordinator_R2",
            reason="conflict_detected",
        )

        self.assertFalse(auth_token.approved)
        self.assertEqual(auth_token.reason, "conflict_detected")

    def test_auth_token_default_reason(self):
        """Verifies default reasons are assigned when omitted."""
        geo_token = create_geometry_token(
            agent_id="agent_C", x=0.0, y=0.0, z=0.0, width=1.0, height=1.0, depth=1.0, duration=10.0
        )

        auth_approved = AuthToken(
            agent_id=geo_token.agent_id,
            geometry_token_id=geo_token.token_id,
            approved=True,
            coordinator_id="coordinator_R1",
        )
        self.assertEqual(auth_approved.reason, "approved")

        auth_rejected = AuthToken(
            agent_id=geo_token.agent_id,
            geometry_token_id=geo_token.token_id,
            approved=False,
            coordinator_id="coordinator_R2",
        )
        self.assertEqual(auth_rejected.reason, "rejected")

    def test_auth_to_from_msg(self):
        """Verifies lossless ROS 2 message serialization for auth tokens."""
        geo_token = create_geometry_token(
            agent_id="agent_D", x=1.0, y=2.0, z=3.0, width=1.0, height=1.0, depth=1.0, duration=5.0
        )

        original = create_auth_token(
            geometry_token=geo_token,
            approved=True,
            coordinator_id="coordinator_R1",
            reason="no_conflicts",
        )

        msg = original.to_msg()
        restored = AuthToken.from_msg(msg)

        self.assertEqual(original.token_id, restored.token_id)
        self.assertEqual(original.geometry_token_id, restored.geometry_token_id)
        self.assertEqual(original.approved, restored.approved)
        self.assertEqual(original.coordinator_id, restored.coordinator_id)
        self.assertEqual(original.reason, restored.reason)


# ============================================================================
# Test Runner
# ============================================================================

if __name__ == "__main__":
    unittest.main()
