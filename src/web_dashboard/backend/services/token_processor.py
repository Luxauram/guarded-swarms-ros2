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
@file token_processor.py

Token aggregation and statistics service.

Processes incoming token streams from ROS 2, maintains rolling event
history, and computes real-time coordination statistics for dashboard
display. Designed for concurrent access from both the ROS 2 bridge
thread and FastAPI WebSocket handlers.

Features:
  - Rolling event history with configurable maximum size.
  - Per-agent and system-wide statistics tracking.
  - Approval rate computation using decision count as denominator,
    preventing rates above 100% when auth tokens arrive faster than
    geometry tokens.
  - Recent event retrieval for timeline display.

@author Luca D'Aurizio
"""

from collections import defaultdict, deque
from typing import Dict, List, Optional
import time
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Token Processor Service
# ============================================================================


class TokenProcessor:
    """
    Aggregates and analyzes token streams for real-time analytics.

    Maintains a rolling history of geometry and authorization token
    events and computes coordination statistics including system-wide
    approval rates and per-agent performance breakdowns.
    """

    # ========================================================================
    # Constants
    # ========================================================================

    DEFAULT_MAX_HISTORY = 100
    DEFAULT_RECENT_LIMIT = 20

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY):
        """
        Initializes the processor with empty history and zeroed counters.

        @param max_history: Maximum number of events retained in each
                            rolling history deque before the oldest entry
                            is evicted. Defaults to DEFAULT_MAX_HISTORY.
        """
        self.max_history = max_history

        self.geometry_tokens = deque(maxlen=max_history)
        self.auth_tokens = deque(maxlen=max_history)

        self.stats = {
            "total_requests": 0,
            "approved": 0,
            "rejected": 0,
            "revoked": 0,
        }

        self.agent_stats = defaultdict(lambda: {"requests": 0, "approved": 0, "rejected": 0})

        logger.info(f"Token processor initialized (max_history={max_history})")

    # ========================================================================
    # Token Processing
    # ========================================================================

    def process_geometry_token(self, data: dict) -> dict:
        """
        Records a geometry token and prepares its WebSocket broadcast payload.

        Appends the token to the rolling history, increments the system-wide
        request counter, and updates the issuing agent's request count.
        Raises any exception after logging so the caller can decide whether
        to suppress or propagate the error.

        @param data: Raw geometry token payload forwarded by the ROS 2 bridge.
        @return:     WebSocket event dictionary containing the event type,
                     a millisecond-precision UNIX timestamp, and the original data.
        @raises Exception: Re-raises any parsing or key-access error after logging.
        """
        try:
            self.geometry_tokens.append(data)

            agent_id = data["base_token"]["agent_id"]
            self.stats["total_requests"] += 1
            self.agent_stats[agent_id]["requests"] += 1

            return {
                "event_type": "geometry",
                "timestamp": int(time.time() * 1000),
                "data": data,
            }

        except Exception as e:
            logger.error(f"Error processing geometry token: {e}")
            raise

    def process_auth_token(self, data: dict) -> dict:
        """
        Records an authorization token and prepares its WebSocket broadcast payload.

        Appends the token to the rolling history and categorizes the decision
        as approved, rejected, or revoked. Revoked tokens increment only the
        revoked counter and do not affect per-agent approved/rejected counts.
        Raises any exception after logging so the caller can decide whether
        to suppress or propagate the error.

        @param data: Raw authorization token payload forwarded by the ROS 2 bridge.
        @return:     WebSocket event dictionary containing the event type,
                     a millisecond-precision UNIX timestamp, and the original data.
        @raises Exception: Re-raises any parsing or key-access error after logging.
        """
        try:
            self.auth_tokens.append(data)

            agent_id = data["base_token"]["agent_id"]
            approved = data["approved"]
            reason = data["reason"]

            if "revoked" in reason:
                self.stats["revoked"] += 1
            elif approved:
                self.stats["approved"] += 1
                self.agent_stats[agent_id]["approved"] += 1
            else:
                self.stats["rejected"] += 1
                self.agent_stats[agent_id]["rejected"] += 1

            return {
                "event_type": "auth",
                "timestamp": int(time.time() * 1000),
                "data": data,
            }

        except Exception as e:
            logger.error(f"Error processing auth token: {e}")
            raise

    # ========================================================================
    # Statistics Retrieval
    # ========================================================================

    def get_statistics(self) -> dict:
        """
        Computes and returns current system-wide coordination statistics.

        The approval rate is computed using the sum of approved and rejected
        decisions as the denominator rather than total_requests. This prevents
        the rate from exceeding 100% in scenarios where authorization tokens
        arrive faster than their corresponding geometry tokens.

        @return: Dictionary containing system-wide counters (total_requests,
                 approved, rejected, revoked, approval_rate) and a per-agent
                 breakdown under the "agents" key. Approval rates are rounded
                 to one decimal place.
        """
        approved = self.stats["approved"]
        rejected = self.stats["rejected"]
        total_decisions = approved + rejected

        approval_rate = (approved / total_decisions * 100) if total_decisions > 0 else 0.0

        agents_with_rates = {}
        for agent_id, stats in self.agent_stats.items():
            agent_approved = stats["approved"]
            agent_rejected = stats["rejected"]
            agent_decisions = agent_approved + agent_rejected
            agent_rate = (agent_approved / agent_decisions * 100) if agent_decisions > 0 else 0.0

            agents_with_rates[agent_id] = {
                "requests": stats["requests"],
                "approved": stats["approved"],
                "rejected": stats["rejected"],
                "approval_rate": round(agent_rate, 1),
            }

        return {
            "total_requests": self.stats["total_requests"],
            "approved": approved,
            "rejected": rejected,
            "revoked": self.stats["revoked"],
            "approval_rate": round(approval_rate, 1),
            "agents": agents_with_rates,
        }

    def get_recent_events(self, limit: int = DEFAULT_RECENT_LIMIT) -> List[dict]:
        """
        Retrieves the most recent token events for timeline display.

        Merges the last `limit` entries from both the geometry and
        authorization history deques into a single list, sorts by
        timestamp in descending order, and returns the top `limit` results.

        @param limit: Maximum number of events to return. Defaults to
                      DEFAULT_RECENT_LIMIT.
        @return:      List of event dictionaries sorted by timestamp,
                      newest first. Each entry contains at minimum
                      "type", "timestamp", and "agent_id" keys.
        """
        all_events = []

        for token in list(self.geometry_tokens)[-limit:]:
            all_events.append(
                {
                    "type": "geometry",
                    "timestamp": token["base_token"]["timestamp"],
                    "agent_id": token["base_token"]["agent_id"],
                    "priority": token["priority"],
                    "position": token["position"],
                }
            )

        for token in list(self.auth_tokens)[-limit:]:
            all_events.append(
                {
                    "type": "auth",
                    "timestamp": token["base_token"]["timestamp"],
                    "agent_id": token["base_token"]["agent_id"],
                    "approved": token["approved"],
                    "reason": token["reason"],
                }
            )

        all_events.sort(key=lambda x: x["timestamp"], reverse=True)

        return all_events[:limit]

    # ========================================================================
    # State Management
    # ========================================================================

    def reset_statistics(self):
        """
        Resets all counters to zero and clears both event history deques.

        Intended for use between coordination sessions or during testing.
        After this call the processor behaves as if freshly instantiated,
        but retains the original max_history configuration.
        """
        logger.info("Resetting token processor statistics")

        self.stats = {
            "total_requests": 0,
            "approved": 0,
            "rejected": 0,
            "revoked": 0,
        }

        self.agent_stats.clear()
        self.geometry_tokens.clear()
        self.auth_tokens.clear()

    def get_state_summary(self) -> dict:
        """
        Returns a snapshot of processor state for diagnostic purposes.

        Provides insight into current history utilization and total event
        throughput without exposing the full token payloads.

        @return: Dictionary containing geometry and auth history sizes,
                 the configured max_history limit, the number of active
                 agents seen, and the cumulative count of all processed events.
        """
        return {
            "geometry_history_size": len(self.geometry_tokens),
            "auth_history_size": len(self.auth_tokens),
            "max_history": self.max_history,
            "active_agents": len(self.agent_stats),
            "total_events_processed": (
                self.stats["total_requests"]
                + self.stats["approved"]
                + self.stats["rejected"]
                + self.stats["revoked"]
            ),
        }
