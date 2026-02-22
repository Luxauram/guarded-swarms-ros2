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
@file token.py

Pydantic data models for token validation and serialization.

Provides type-safe data models for ROS 2 token messages, WebSocket events,
and system statistics. All models include automatic validation, JSON
serialization, and OpenAPI schema generation for FastAPI.

@author Luca D'Aurizio
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict
from enum import Enum


# ============================================================================
# Enums
# ============================================================================


class TokenType(str, Enum):
    """Token type enumeration."""

    GEOMETRY = "geometry"
    AUTHORIZATION = "authorization"


class EventType(str, Enum):
    """WebSocket event type enumeration."""

    GEOMETRY = "geometry"
    AUTH = "auth"
    STATS_UPDATE = "stats_update"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


# ============================================================================
# Base Token Models
# ============================================================================


class TokenBase(BaseModel):
    """
    Base token model with cryptographic signature.

    Contains common fields present in all token types, including
    unique identification, timestamp, and SHA256 signature.
    """

    token_id: str = Field(
        ..., description="Unique token identifier (UUID4)", min_length=36, max_length=36
    )
    timestamp: int = Field(..., description="Token creation time in microseconds since epoch", gt=0)
    agent_id: str = Field(
        ..., description="Identifier of the agent that created this token", min_length=1
    )
    token_type: TokenType = Field(..., description="Type of token: geometry or authorization")
    signature: str = Field(
        ...,
        description="SHA256 cryptographic signature (64 hex chars)",
        min_length=64,
        max_length=64,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "token_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": 1771152466606232,
                "agent_id": "agent_A",
                "token_type": "geometry",
                "signature": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2",
            }
        }


# ============================================================================
# Geometry Token Model
# ============================================================================


class GeometryTokenModel(BaseModel):
    """
    Geometry token representing spatial area request.

    Contains position, dimensions, duration, and priority level for
    a requested operational volume in 3D space.
    """

    base_token: TokenBase = Field(..., description="Base token metadata")
    position: List[float] = Field(
        ..., description="Center position [x, y, z] in meters", min_length=3, max_length=3
    )
    dimensions: List[float] = Field(
        ..., description="Bounding box [width, height, depth] in meters", min_length=3, max_length=3
    )
    duration: float = Field(..., description="Requested duration in seconds", gt=0)
    priority: int = Field(..., description="Priority level (0=minimal, 10=emergency)", ge=0, le=10)

    @field_validator("position", "dimensions")
    @classmethod
    def validate_3d_vector(cls, v: List[float]) -> List[float]:
        """Validates 3D vector has exactly 3 components."""
        if len(v) != 3:
            raise ValueError("Must be a 3D vector [x, y, z]")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "base_token": {
                    "token_id": "550e8400-e29b-41d4-a716-446655440000",
                    "timestamp": 1771152466606232,
                    "agent_id": "agent_A",
                    "token_type": "geometry",
                    "signature": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                },
                "position": [10.5, -3.2, 5.0],
                "dimensions": [5.0, 5.0, 3.0],
                "duration": 10.5,
                "priority": 7,
            }
        }


# ============================================================================
# Authorization Token Model
# ============================================================================


class AuthTokenModel(BaseModel):
    """
    Authorization token representing coordinator decision.

    Links to a geometry token and indicates approval/rejection with
    reasoning from the coordination system.
    """

    base_token: TokenBase = Field(..., description="Base token metadata")
    geometry_token_id: str = Field(
        ..., description="ID of the geometry token being authorized", min_length=36, max_length=36
    )
    approved: bool = Field(..., description="True if request approved, False if rejected")
    coordinator_id: str = Field(
        ..., description="Identifier of the coordinator making this decision", min_length=1
    )
    reason: str = Field(..., description="Human-readable reason for the decision", min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "base_token": {
                    "token_id": "660e8400-e29b-41d4-a716-446655440001",
                    "timestamp": 1771152467606232,
                    "agent_id": "agent_A",
                    "token_type": "authorization",
                    "signature": "b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7",
                },
                "geometry_token_id": "550e8400-e29b-41d4-a716-446655440000",
                "approved": True,
                "coordinator_id": "coordinator_R1",
                "reason": "approved",
            }
        }


# ============================================================================
# WebSocket Event Models
# ============================================================================


class TokenEvent(BaseModel):
    """
    Token event for WebSocket streaming.

    Wraps token data with event type and timestamp for client consumption.
    """

    event_type: EventType = Field(..., description="Type of event being transmitted")
    timestamp: int = Field(..., description="Event timestamp in microseconds", gt=0)
    data: Dict = Field(..., description="Event payload (token data or statistics)")

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "geometry",
                "timestamp": 1771152466606232,
                "data": {"agent_id": "agent_A", "position": [10.5, -3.2, 5.0], "priority": 7},
            }
        }


# ============================================================================
# Statistics Models
# ============================================================================


class AgentStats(BaseModel):
    """Per-agent statistics."""

    requests: int = Field(..., description="Total requests made by this agent", ge=0)
    approved: int = Field(..., description="Number of approved requests", ge=0)
    rejected: int = Field(..., description="Number of rejected requests", ge=0)
    approval_rate: float = Field(
        ..., description="Approval rate as percentage (0-100)", ge=0, le=100
    )


class SystemStats(BaseModel):
    """
    System-wide coordination statistics.

    Aggregates metrics across all agents including approval rates,
    rejection counts, and per-agent breakdowns.
    """

    total_requests: int = Field(..., description="Total number of geometry token requests", ge=0)
    approved: int = Field(..., description="Total approved requests", ge=0)
    rejected: int = Field(..., description="Total rejected requests", ge=0)
    revoked: int = Field(..., description="Total revoked approvals (preemptions)", ge=0)
    approval_rate: float = Field(
        ..., description="Overall approval rate as percentage (0-100)", ge=0, le=100
    )
    agents: Dict[str, AgentStats] = Field(..., description="Per-agent statistics breakdown")

    class Config:
        json_schema_extra = {
            "example": {
                "total_requests": 142,
                "approved": 98,
                "rejected": 38,
                "revoked": 6,
                "approval_rate": 69.01,
                "agents": {
                    "agent_A": {
                        "requests": 36,
                        "approved": 32,
                        "rejected": 4,
                        "approval_rate": 88.89,
                    },
                    "agent_B": {
                        "requests": 35,
                        "approved": 20,
                        "rejected": 15,
                        "approval_rate": 57.14,
                    },
                },
            }
        }
