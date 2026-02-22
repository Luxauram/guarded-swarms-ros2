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
 * @file websocket.constants.ts
 *
 * WebSocket Constants.
 *
 * Configuration values for WebSocket connections.
 *
 * @author Luca D'Aurizio
 */

// ============================================================================
// Connection Configuration
// ============================================================================

export const CONNECTION_CONFIG = {
  RECONNECT_INTERVAL_MS: 3000,
  PROTOCOLS: {
    SECURE: 'wss:',
    INSECURE: 'ws:',
  } as const,
  ENDPOINT_PATH: '/ws',
} as const;

// ============================================================================
// UI Configuration
// ============================================================================

export const UI_CONFIG = {
  ELEMENTS: {
    CONNECTION_STATUS: 'connection-status',
  } as const,
  STATUS_CLASSES: {
    INDICATOR_BASE: 'h-3 w-3 rounded-full mr-2',
    TEXT_BASE: 'text-sm',
  } as const,
  STATUS_STYLES: {
    CONNECTED: {
      INDICATOR: 'bg-green-500 animate-pulse',
      TEXT: 'text-green-600 font-semibold',
      LABEL: 'Connected',
    },
    DISCONNECTED: {
      INDICATOR: 'bg-red-500',
      TEXT: 'text-red-600',
      LABEL: 'Disconnected',
    },
    CONNECTING: {
      INDICATOR: 'bg-yellow-500 animate-pulse',
      TEXT: 'text-yellow-600',
      LABEL: 'Connecting...',
    },
    ERROR: {
      INDICATOR: 'bg-red-500',
      TEXT: 'text-red-600',
      LABEL: 'Connection Error',
    },
  } as const,
} as const;

// ============================================================================
// Message Types
// ============================================================================

export const MESSAGE_TYPES = {
  GEOMETRY: 'geometry',
  AUTH: 'auth',
  STATS_UPDATE: 'stats_update',
  CONNECTION: 'connection',
} as const;

// ============================================================================
// Logging Configuration
// ============================================================================

export const LOG_CONFIG = {
  VERBOSE: true,
  PREFIXES: {
    CONNECTION: '[WebSocket]',
    MESSAGE: '[WS Message]',
    ERROR: '[WS Error]',
  } as const,
} as const;
