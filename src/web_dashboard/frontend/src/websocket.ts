/**
 * Copyright 2026 Luca D'Aurizio
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @file websocket.ts
 *
 * WebSocket Manager.
 *
 * Handles the real-time connection to the backend, including connection
 * lifecycle management, inbound message routing, automatic reconnection
 * on disconnect, and connection status UI updates.
 *
 * Exposes a minimal debug API on {@link window.wsDebug} for console-based
 * inspection and manual control during development.
 *
 * @author Luca D'Aurizio
 */

import type {
  WebSocketMessage,
  GeometryTokenData,
  AuthTokenData,
  Statistics,
  ConnectionStatus,
} from '../types/websocket.types';
import {
  CONNECTION_CONFIG,
  UI_CONFIG,
  MESSAGE_TYPES,
  LOG_CONFIG,
} from '../constants/websocket.constants';

// ============================================================================
// State Management
// ============================================================================

let ws: WebSocket | null = null;
let reconnectInterval: number | null = null;
let currentStatus: ConnectionStatus = 'disconnected';

// ============================================================================
// WebSocket Connection
// ============================================================================

/**
 * Creates a new WebSocket connection to the backend endpoint, automatically
 * selecting the secure (`wss`) or insecure (`ws`) protocol based on the
 * current page protocol. Registers all lifecycle event handlers and sets
 * the connection status to `connecting` before the handshake completes.
 *
 * @returns void
 */
function connectWebSocket(): void {
  const protocol =
    window.location.protocol === 'https:'
      ? CONNECTION_CONFIG.PROTOCOLS.SECURE
      : CONNECTION_CONFIG.PROTOCOLS.INSECURE;
  const wsUrl = `${protocol}//${window.location.host}${CONNECTION_CONFIG.ENDPOINT_PATH}`;

  if (LOG_CONFIG.VERBOSE) {
    console.log(`${LOG_CONFIG.PREFIXES.CONNECTION} Connecting to:`, wsUrl);
  }

  setConnectionStatus('connecting');
  ws = new WebSocket(wsUrl);

  ws.onopen = handleWebSocketOpen;
  ws.onmessage = handleWebSocketMessage;
  ws.onerror = handleWebSocketError;
  ws.onclose = handleWebSocketClose;
}

/**
 * Handles the WebSocket `open` event. Updates the connection status to
 * `connected` and clears any pending reconnect interval.
 *
 * @returns void
 */
function handleWebSocketOpen(): void {
  if (LOG_CONFIG.VERBOSE) {
    console.log(`${LOG_CONFIG.PREFIXES.CONNECTION} Connected successfully`);
  }

  setConnectionStatus('connected');
  clearReconnectInterval();
}

/**
 * Handles incoming WebSocket messages by parsing the raw JSON payload and
 * forwarding the structured message to {@link routeMessage}. Logs a console
 * error if the payload cannot be parsed.
 *
 * @param event - The native {@link MessageEvent} containing the raw message data.
 * @returns void
 */
function handleWebSocketMessage(event: MessageEvent): void {
  try {
    const message: WebSocketMessage = JSON.parse(event.data);

    if (LOG_CONFIG.VERBOSE) {
      console.log(`${LOG_CONFIG.PREFIXES.MESSAGE}`, message.event_type);
    }

    routeMessage(message);
  } catch (error) {
    console.error(
      `${LOG_CONFIG.PREFIXES.ERROR} Failed to parse message:`,
      error,
    );
  }
}

/**
 * Handles the WebSocket `error` event by logging the error and updating
 * the connection status to `error`.
 *
 * @param error - The native {@link Event} emitted by the WebSocket on error.
 * @returns void
 */
function handleWebSocketError(error: Event): void {
  console.error(`${LOG_CONFIG.PREFIXES.ERROR}`, error);
  setConnectionStatus('error');
}

/**
 * Handles the WebSocket `close` event by updating the connection status
 * to `disconnected` and scheduling an automatic reconnection attempt.
 *
 * @returns void
 */
function handleWebSocketClose(): void {
  if (LOG_CONFIG.VERBOSE) {
    console.log(`${LOG_CONFIG.PREFIXES.CONNECTION} Disconnected`);
  }

  setConnectionStatus('disconnected');
  scheduleReconnect();
}

// ============================================================================
// Message Routing
// ============================================================================

/**
 * Routes a parsed WebSocket message to the appropriate global handler based
 * on its `event_type` field. Supported types are defined in {@link MESSAGE_TYPES}.
 * Unknown types trigger a console warning and are otherwise ignored.
 *
 * @param message - The parsed {@link WebSocketMessage} to dispatch.
 * @returns void
 */
function routeMessage(message: WebSocketMessage): void {
  const { event_type, data } = message;

  switch (event_type) {
    case MESSAGE_TYPES.GEOMETRY:
      (window as any).handleGeometryToken(data as GeometryTokenData);
      break;

    case MESSAGE_TYPES.AUTH:
      (window as any).handleAuthToken(data as AuthTokenData);
      break;

    case MESSAGE_TYPES.STATS_UPDATE:
      (window as any).updateStatistics(data as Statistics);
      break;

    case MESSAGE_TYPES.CONNECTION:
      if (LOG_CONFIG.VERBOSE) {
        console.log(`${LOG_CONFIG.PREFIXES.CONNECTION} Confirmed:`, message);
      }
      break;

    default:
      const _exhaustive: never = event_type;
      console.warn(`${LOG_CONFIG.PREFIXES.MESSAGE} Unknown type:`, message);
  }
}

// ============================================================================
// Reconnection Logic
// ============================================================================

/**
 * Schedules a periodic reconnection attempt using the interval defined in
 * {@link CONNECTION_CONFIG.RECONNECT_INTERVAL_MS}. If a reconnect interval
 * is already active, this function is a no-op to prevent duplicate timers.
 *
 * @returns void
 */
function scheduleReconnect(): void {
  if (reconnectInterval !== null) {
    return;
  }

  if (LOG_CONFIG.VERBOSE) {
    console.log(
      `${LOG_CONFIG.PREFIXES.CONNECTION} Scheduling reconnect in ${CONNECTION_CONFIG.RECONNECT_INTERVAL_MS}ms`,
    );
  }

  reconnectInterval = setInterval((): void => {
    if (LOG_CONFIG.VERBOSE) {
      console.log(
        `${LOG_CONFIG.PREFIXES.CONNECTION} Attempting to reconnect...`,
      );
    }
    connectWebSocket();
  }, CONNECTION_CONFIG.RECONNECT_INTERVAL_MS);
}

function clearReconnectInterval(): void {
  if (reconnectInterval !== null) {
    clearInterval(reconnectInterval);
    reconnectInterval = null;
  }
}

// ============================================================================
// Connection Status Management
// ============================================================================

/**
 * Updates the internal connection status state and triggers a UI refresh
 * to reflect the new status.
 *
 * @param status - The new {@link ConnectionStatus} value to apply.
 * @returns void
 */
function setConnectionStatus(status: ConnectionStatus): void {
  currentStatus = status;
  updateConnectionStatusUI(status);
}

function updateConnectionStatusUI(status: ConnectionStatus): void {
  const statusEl = document.getElementById(
    UI_CONFIG.ELEMENTS.CONNECTION_STATUS,
  );

  if (!statusEl) {
    console.warn('Connection status element not found');
    return;
  }

  const statusConfig =
    UI_CONFIG.STATUS_STYLES[
      status.toUpperCase() as keyof typeof UI_CONFIG.STATUS_STYLES
    ];

  if (!statusConfig) {
    console.warn(`Unknown status: ${status}`);
    return;
  }

  statusEl.innerHTML = `
    <span class="${UI_CONFIG.STATUS_CLASSES.INDICATOR_BASE} ${statusConfig.INDICATOR}"></span>
    <span class="${UI_CONFIG.STATUS_CLASSES.TEXT_BASE} ${statusConfig.TEXT}">${statusConfig.LABEL}</span>
  `;
}

// ============================================================================
// Cleanup
// ============================================================================

/**
 * Gracefully closes the active WebSocket connection, cancels any pending
 * reconnect interval, nullifies the socket reference, and sets the status
 * to `disconnected`. Should be called before page unload or when intentionally
 * terminating the session.
 *
 * @returns void
 */
function disconnectWebSocket(): void {
  clearReconnectInterval();

  if (ws) {
    ws.close();
    ws = null;
  }

  setConnectionStatus('disconnected');

  if (LOG_CONFIG.VERBOSE) {
    console.log(`${LOG_CONFIG.PREFIXES.CONNECTION} Cleanup completed`);
  }
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Returns the current WebSocket connection status without triggering any
 * side effects.
 *
 * @returns The current {@link ConnectionStatus} value.
 */
function getConnectionStatus(): ConnectionStatus {
  return currentStatus;
}

/**
 * Forces an immediate reconnection by first closing the current connection
 * and cancelling any active reconnect timer, then opening a new one.
 * Primarily intended for use during development and debugging.
 *
 * @returns void
 */
function forceReconnect(): void {
  if (LOG_CONFIG.VERBOSE) {
    console.log(`${LOG_CONFIG.PREFIXES.CONNECTION} Force reconnect requested`);
  }

  disconnectWebSocket();
  connectWebSocket();
}

// ============================================================================
// Initialization
// ============================================================================

window.addEventListener('DOMContentLoaded', (): void => {
  connectWebSocket();
});

// Cleanup on page unload
window.addEventListener('beforeunload', (): void => {
  disconnectWebSocket();
});

// ============================================================================
// Global API (for debugging in console)
// ============================================================================

(window as any).wsDebug = {
  status: getConnectionStatus,
  reconnect: forceReconnect,
  disconnect: disconnectWebSocket,
};
