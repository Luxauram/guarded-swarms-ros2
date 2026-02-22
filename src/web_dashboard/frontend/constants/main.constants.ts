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
 * @file main.constants.ts
 *
 * Main Dashboard Constants.
 *
 * Configuration values for dashboard UI and behavior.
 *
 * @author Luca D'Aurizio
 */

// ============================================================================
// Event Log Configuration
// ============================================================================

export const EVENT_LOG_CONFIG = {
  MAX_ENTRIES: 50,
  AUTO_SCROLL: true,
} as const;

// ============================================================================
// DOM Element IDs
// ============================================================================

export const ELEMENT_IDS = {
  EVENT_LOG: 'event-log',
  STAT_TOTAL: 'stat-total',
  STAT_APPROVED: 'stat-approved',
  STAT_REJECTED: 'stat-rejected',
  STAT_RATE: 'stat-rate',
  AGENT_STATS: 'agent-stats',
  COMMAND_OUTPUT: 'command-output',
  COMMAND_TEXT: 'command-text',
} as const;

// ============================================================================
// Token Status Configuration
// ============================================================================

export const TOKEN_STATUS = {
  APPROVED: {
    ICON: '[APPROVED]',
    COLOR: 'text-green-600',
    KEYWORD: 'APPROVED',
  },
  REJECTED: {
    ICON: '[REJECTED]',
    COLOR: 'text-red-600',
    KEYWORD: 'REJECTED',
  },
  REVOKED: {
    ICON: '[REVOKED]',
    COLOR: 'text-orange-600',
    KEYWORD: 'REVOKED',
  },
  REQUEST: {
    ICON: '[REQUESTED]',
    COLOR: 'text-blue-600',
    KEYWORD: 'requested',
  },
} as const;

// ============================================================================
// CSS Classes
// ============================================================================

export const CSS_CLASSES = {
  LOG_ENTRY: {
    BASE: 'py-1 border-b border-gray-100',
    DEFAULT_COLOR: 'text-gray-700',
  },
  AGENT_STATS: {
    CONTAINER: 'border-b border-gray-200 pb-3',
    LABEL: 'font-semibold text-gray-700',
    VALUE: 'text-sm text-gray-500',
    PROGRESS_BAR_BG: 'w-full bg-gray-200 rounded-full h-2',
    PROGRESS_BAR_FILL: 'bg-blue-600 h-2 rounded-full',
  },
  HIDDEN: 'hidden',
} as const;

// ============================================================================
// API Endpoints
// ============================================================================

export const API_ENDPOINTS = {
  MAKEFILE_EXECUTE: '/api/makefile/execute',
  SYSTEM_RESET: '/api/system/reset',
  SYSTEM_STATS: '/api/system/stats',
} as const;

// ============================================================================
// Number Formatting
// ============================================================================

export const FORMAT_CONFIG = {
  POSITION_DECIMALS: 1,
  PERCENTAGE_DECIMALS: 0,
} as const;

// ============================================================================
// User Interaction
// ============================================================================

export const UI_MESSAGES = {
  RESET_CONFIRM: 'Reset all statistics?',
  RESET_FAILED: 'Failed to reset statistics: ',
  COMMAND_EXECUTING: 'Executing: make ',
  COMMAND_SUCCESS: '\nSuccess!\n\n',
  COMMAND_FAILED: '\nFailed!\n\n',
  COMMAND_ERROR: '\nError: ',
  UNKNOWN_ERROR: 'Unknown error',
} as const;

// ============================================================================
// Keywords for Status Detection
// ============================================================================

export const STATUS_KEYWORDS = {
  REVOKED: 'revoked',
} as const;
