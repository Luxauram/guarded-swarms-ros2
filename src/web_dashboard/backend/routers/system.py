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
@file system.py

System information and statistics router.

Provides REST API endpoints for retrieving coordination statistics,
recent token event history, processor diagnostics, service health, and
administrative operations such as statistics reset.

Endpoints:
  GET  /api/system/stats   - Current coordination statistics.
  GET  /api/system/events  - Recent token event history.
  POST /api/system/reset   - Reset all statistics and event history.
  GET  /api/system/health  - Service readiness and health check.
  GET  /api/system/state   - Token processor diagnostic snapshot.

@author Luca D'Aurizio
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import SystemStats

logger = logging.getLogger(__name__)

# ============================================================================
# Router Configuration
# ============================================================================

router = APIRouter(prefix="/api/system", tags=["System"])

# ============================================================================
# Global State
# ============================================================================

token_processor = None


def set_token_processor(processor):
    """
    Injects the shared TokenProcessor instance into this router.

    Must be called during application startup before any endpoint receives
    a request, otherwise statistics and event endpoints return empty results.

    @param processor: Initialized TokenProcessor instance from app.py.
    """
    global token_processor
    token_processor = processor
    logger.info("Token processor injected into system router")


# ============================================================================
# Response Models
# ============================================================================


class ResetResponse(BaseModel):
    """Response model returned by the statistics reset endpoint."""

    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")


class HealthResponse(BaseModel):
    """Response model returned by the health check endpoint."""

    status: str = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    processor_active: bool = Field(..., description="Token processor availability")


class StateResponse(BaseModel):
    """Response model returned by the processor state diagnostics endpoint."""

    geometry_history_size: int = Field(..., description="Geometry tokens in history")
    auth_history_size: int = Field(..., description="Auth tokens in history")
    max_history: int = Field(..., description="Maximum history size")
    active_agents: int = Field(..., description="Number of active agents")
    total_events_processed: int = Field(..., description="Total events processed")


# ============================================================================
# Statistics Endpoints
# ============================================================================


@router.get("/stats", response_model=SystemStats)
async def get_statistics():
    """
    Returns current system-wide coordination statistics.

    Delegates to the token processor to compute aggregated metrics including
    approval rates, rejection counts, revocations, and per-agent breakdowns.
    If the processor has not been initialized, returns a zeroed SystemStats
    object rather than raising an error, so the dashboard can render on load
    before any tokens have been received.

    @return: SystemStats populated with live metrics, or all-zero defaults
             if the token processor is not yet available.
    @raises HTTPException: 500 if the processor raises an unexpected error.
    """
    if token_processor is None:
        logger.warning("Statistics requested but token processor not initialized")
        return SystemStats(
            total_requests=0,
            approved=0,
            rejected=0,
            revoked=0,
            approval_rate=0.0,
            agents={},
        )

    try:
        stats = token_processor.get_statistics()
        return SystemStats(**stats)
    except Exception as e:
        logger.error(f"Error retrieving statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/events")
async def get_recent_events(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of events to return")
):
    """
    Returns the most recent token events for timeline display.

    Retrieves a merged, timestamp-sorted list of geometry and authorization
    token events from the processor history. Returns an empty list rather
    than raising an error if the processor is not yet available.

    @param limit: Maximum number of events to return. Clamped to [1, 100].
    @return:      Dictionary containing the event list, its length, and the
                  applied limit.
    @raises HTTPException: 500 if the processor raises an unexpected error.
    """
    if token_processor is None:
        logger.warning("Events requested but token processor not initialized")
        return {"events": []}

    try:
        events = token_processor.get_recent_events(limit=limit)
        return {"events": events, "count": len(events), "limit": limit}
    except Exception as e:
        logger.error(f"Error retrieving events: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve events")


# ============================================================================
# Administrative Endpoints
# ============================================================================


@router.post("/reset", response_model=ResetResponse)
async def reset_statistics():
    """
    Resets all coordination statistics and clears event history.

    Delegates to the processor's reset_statistics method. Returns a
    'skipped' status rather than an error if the processor is unavailable,
    since the effect (empty state) is already equivalent.

    @return:      ResetResponse indicating 'success' or 'skipped'.
    @raises HTTPException: 500 if the processor raises an unexpected error.
    """
    if token_processor is None:
        logger.warning("Reset requested but token processor not initialized")
        return ResetResponse(status="skipped", message="Token processor not available")

    try:
        token_processor.reset_statistics()
        logger.info("Statistics reset successfully")
        return ResetResponse(status="success", message="Statistics and event history cleared")
    except Exception as e:
        logger.error(f"Error resetting statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset statistics")


# ============================================================================
# Health & Diagnostics Endpoints
# ============================================================================


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Service readiness and health check.

    Returns static service metadata alongside a live flag indicating
    whether the token processor dependency has been injected. Suitable
    for use as a Kubernetes readiness probe or uptime monitor.

    @return: HealthResponse with service identity and processor availability.
    """
    return HealthResponse(
        status="healthy",
        service="Guarded Swarms Web Dashboard",
        version="1.0.0",
        processor_active=token_processor is not None,
    )


@router.get("/state", response_model=StateResponse)
async def get_processor_state():
    """
    Returns a diagnostic snapshot of the token processor's internal state.

    Exposes history buffer utilization, active agent count, and cumulative
    event throughput without revealing raw token payloads. Intended for
    debugging and operational monitoring.

    @return:      StateResponse with buffer sizes and processing counters.
    @raises HTTPException: 503 if the token processor has not been initialized.
    @raises HTTPException: 500 if the processor raises an unexpected error.
    """
    if token_processor is None:
        raise HTTPException(status_code=503, detail="Token processor not initialized")

    try:
        state = token_processor.get_state_summary()
        return StateResponse(**state)
    except Exception as e:
        logger.error(f"Error retrieving processor state: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve processor state")
