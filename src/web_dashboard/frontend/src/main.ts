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
 * @file main.ts
 *
 * Main Dashboard Logic.
 *
 * Handles token events, statistics updates, and user interactions.
 * Exposes global functions for HTML onclick handlers and manages
 * real-time event logging, agent statistics, and Makefile command execution.
 *
 * @author Luca D'Aurizio
 */

import type {
  GeometryTokenData,
  AuthTokenData,
  Statistics,
  AgentStats,
  MakeCommandResult,
  LogEventConfig,
} from '../types/main.types';
import {
  EVENT_LOG_CONFIG,
  ELEMENT_IDS,
  TOKEN_STATUS,
  CSS_CLASSES,
  API_ENDPOINTS,
  FORMAT_CONFIG,
  UI_MESSAGES,
  STATUS_KEYWORDS,
} from '../constants/main.constants';

// ============================================================================
// External Function Declarations
// ============================================================================

declare function updatePriorityChart(priority: number): void;
declare function updateTimelineChart(approved: number, rejected: number): void;

// ============================================================================
// Event Handlers
// ============================================================================

/**
 * Handles an incoming geometry token event by formatting the agent's position
 * and priority into a human-readable log entry, then updating the priority chart.
 *
 * @param data - The geometry token payload containing agent ID, position, and priority.
 * @returns void
 */
function handleGeometryToken(data: GeometryTokenData): void {
  console.log('Geometry token received:', data);

  const agent = data.base_token.agent_id;
  const priority = data.priority;
  const [x, y, z] = data.position;

  const formattedPos = [x, y, z]
    .map((coord) => coord.toFixed(FORMAT_CONFIG.POSITION_DECIMALS))
    .join(', ');

  const message = `${TOKEN_STATUS.REQUEST.ICON} ${agent} ${TOKEN_STATUS.REQUEST.KEYWORD} zone at [${formattedPos}] (priority=${priority})`;

  addEventLog(message, TOKEN_STATUS.REQUEST.COLOR);
  console.log('Updating priority chart with:', priority);
  updatePriorityChart(priority);
}

/**
 * Handles an incoming authorization token event by determining the token status
 * (approved, rejected, or revoked) and appending the formatted result to the event log.
 *
 * @param data - The authorization token payload containing agent ID, approval status, and reason.
 * @returns void
 */
function handleAuthToken(data: AuthTokenData): void {
  const agent = data.base_token.agent_id;
  const approved = data.approved;
  const reason = data.reason;

  const config = determineTokenStatus(approved, reason);
  const message = formatAuthMessage(agent, reason, config);

  addEventLog(message, config.color);
}

/**
 * Determines the display configuration for a token event based on its
 * approval status and reason string. Revoked tokens take precedence over
 * the boolean approval flag.
 *
 * @param approved - Whether the token was approved by the arbitrator.
 * @param reason   - The reason string associated with the token decision.
 * @returns A {@link LogEventConfig} object containing the icon, color, and label for the event.
 */
function determineTokenStatus(
  approved: boolean,
  reason: string,
): LogEventConfig {
  if (reason.includes(STATUS_KEYWORDS.REVOKED)) {
    return {
      icon: TOKEN_STATUS.REVOKED.ICON,
      color: TOKEN_STATUS.REVOKED.COLOR,
      text: TOKEN_STATUS.REVOKED.KEYWORD,
    };
  }

  if (approved) {
    return {
      icon: TOKEN_STATUS.APPROVED.ICON,
      color: TOKEN_STATUS.APPROVED.COLOR,
      text: TOKEN_STATUS.APPROVED.KEYWORD,
    };
  }

  return {
    icon: TOKEN_STATUS.REJECTED.ICON,
    color: TOKEN_STATUS.REJECTED.COLOR,
    text: TOKEN_STATUS.REJECTED.KEYWORD,
  };
}

/**
 * Formats a human-readable authorization message based on the agent identity,
 * decision reason, and resolved log configuration. The output format varies
 * depending on whether the token was revoked, approved, or rejected.
 *
 * @param agent  - The agent identifier string.
 * @param reason - The reason string associated with the authorization decision.
 * @param config - The {@link LogEventConfig} resolved by {@link determineTokenStatus}.
 * @returns A formatted string ready to be displayed in the event log.
 */
function formatAuthMessage(
  agent: string,
  reason: string,
  config: LogEventConfig,
): string {
  if (reason.includes(STATUS_KEYWORDS.REVOKED)) {
    return `${config.icon} ${agent} token ${config.text} (${reason})`;
  }

  if (config.text === TOKEN_STATUS.APPROVED.KEYWORD) {
    return `${config.icon} ${agent} ${config.text}`;
  }

  return `${config.icon} ${agent} ${config.text} (${reason})`;
}

// ============================================================================
// Event Log Management
// ============================================================================

/**
 * Appends a new timestamped entry to the event log container. Automatically
 * removes the placeholder text on first use, enforces the maximum entry limit,
 * and scrolls to the latest entry if auto-scroll is enabled.
 *
 * @param message    - The text content to display in the log entry.
 * @param colorClass - The CSS class used to color the entry. Defaults to the standard log color.
 * @returns void
 */
function addEventLog(
  message: string,
  colorClass: string = CSS_CLASSES.LOG_ENTRY.DEFAULT_COLOR,
): void {
  const logContainer = document.getElementById(ELEMENT_IDS.EVENT_LOG);

  if (!logContainer) {
    console.error(`Element '${ELEMENT_IDS.EVENT_LOG}' not found`);
    return;
  }

  removePlaceholder(logContainer);

  const entry = createLogEntry(message, colorClass);
  logContainer.appendChild(entry);

  limitLogEntries(logContainer);

  if (EVENT_LOG_CONFIG.AUTO_SCROLL) {
    scrollToBottom(logContainer);
  }
}

/**
 * Clears the inner HTML of a container if it currently displays the default
 * "Waiting for events" placeholder text.
 *
 * @param container - The HTML element to inspect and potentially clear.
 * @returns void
 */
function removePlaceholder(container: HTMLElement): void {
  if (container.textContent?.includes('Waiting for events')) {
    container.innerHTML = '';
  }
}

/**
 * Creates a styled div element representing a single log entry, prefixed
 * with the current local time.
 *
 * @param message    - The text content of the log entry.
 * @param colorClass - The CSS class applied to the entry for color styling.
 * @returns A fully configured {@link HTMLDivElement} ready to be inserted into the DOM.
 */
function createLogEntry(message: string, colorClass: string): HTMLDivElement {
  const entry = document.createElement('div');
  entry.className = `${colorClass} ${CSS_CLASSES.LOG_ENTRY.BASE}`;
  entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  return entry;
}

/**
 * Removes the oldest log entries from the container until the number of
 * children is within the configured {@link EVENT_LOG_CONFIG.MAX_ENTRIES} limit.
 *
 * @param container - The log container element whose children should be pruned.
 * @returns void
 */
function limitLogEntries(container: HTMLElement): void {
  while (container.children.length > EVENT_LOG_CONFIG.MAX_ENTRIES) {
    const firstChild = container.firstChild;
    if (firstChild) {
      container.removeChild(firstChild);
    }
  }
}

/**
 * Scrolls the given container to its bottom-most position, ensuring the
 * latest content is visible.
 *
 * @param container - The scrollable HTML element to scroll.
 * @returns void
 */
function scrollToBottom(container: HTMLElement): void {
  container.scrollTop = container.scrollHeight;
}

// ============================================================================
// Statistics Updates
// ============================================================================

/**
 * Updates all statistics-related UI components: the numeric counters, the
 * per-agent breakdown, and the approval/rejection timeline chart.
 *
 * @param stats - The full {@link Statistics} object received from the backend.
 * @returns void
 */
function updateStatistics(stats: Statistics): void {
  updateStatCounters(stats);
  updateAgentStats(stats.agents);
  updateTimelineChart(stats.approved, stats.rejected);
}

/**
 * Updates the four numeric counter elements on the dashboard (total requests,
 * approved, rejected, and approval rate) using the provided statistics data.
 *
 * @param stats - The {@link Statistics} object containing the counter values.
 * @returns void
 */
function updateStatCounters(stats: Statistics): void {
  const elements = {
    total: document.getElementById(ELEMENT_IDS.STAT_TOTAL),
    approved: document.getElementById(ELEMENT_IDS.STAT_APPROVED),
    rejected: document.getElementById(ELEMENT_IDS.STAT_REJECTED),
    rate: document.getElementById(ELEMENT_IDS.STAT_RATE),
  };

  if (elements.total)
    elements.total.textContent = stats.total_requests.toString();
  if (elements.approved)
    elements.approved.textContent = stats.approved.toString();
  if (elements.rejected)
    elements.rejected.textContent = stats.rejected.toString();
  if (elements.rate) elements.rate.textContent = `${stats.approval_rate}%`;
}

/**
 * Rebuilds the agent statistics section of the dashboard from the provided
 * agent map. If the map is empty, the section is left unchanged. Otherwise,
 * all existing content is replaced with fresh stat elements for each agent.
 *
 * @param agents - A record mapping agent IDs to their respective {@link AgentStats}.
 * @returns void
 */
function updateAgentStats(agents: Record<string, AgentStats>): void {
  const container = document.getElementById(ELEMENT_IDS.AGENT_STATS);

  if (!container) {
    console.error(`Element '${ELEMENT_IDS.AGENT_STATS}' not found`);
    return;
  }

  if (Object.keys(agents).length === 0) {
    return;
  }

  removePlaceholder(container);
  container.innerHTML = '';

  Object.entries(agents).forEach(([agentId, stats]) => {
    const agentElement = createAgentStatsElement(agentId, stats);
    container.appendChild(agentElement);
  });
}

/**
 * Creates a DOM element displaying an individual agent's statistics, including
 * a label, an approved/total counter, and a proportional progress bar.
 *
 * @param agentId - The unique identifier of the agent.
 * @param stats   - The {@link AgentStats} object containing request and approval counts.
 * @returns A fully populated {@link HTMLDivElement} representing the agent's stats card.
 */
function createAgentStatsElement(
  agentId: string,
  stats: AgentStats,
): HTMLDivElement {
  const total = stats.requests;
  const approved = stats.approved;
  const percentage = calculatePercentage(approved, total);

  const agentEl = document.createElement('div');
  agentEl.className = CSS_CLASSES.AGENT_STATS.CONTAINER;
  agentEl.innerHTML = `
    <div class="flex justify-between items-center mb-1">
      <span class="${CSS_CLASSES.AGENT_STATS.LABEL}">${agentId}</span>
      <span class="${CSS_CLASSES.AGENT_STATS.VALUE}">${approved}/${total} (${percentage}%)</span>
    </div>
    <div class="${CSS_CLASSES.AGENT_STATS.PROGRESS_BAR_BG}">
      <div class="${CSS_CLASSES.AGENT_STATS.PROGRESS_BAR_FILL}" style="width: ${percentage}%"></div>
    </div>
  `;

  return agentEl;
}

/**
 * Computes the integer percentage of a partial value relative to a total.
 * Returns 0 if the total is zero to avoid division errors.
 *
 * @param value - The partial count (e.g. approved requests).
 * @param total - The total count (e.g. all requests).
 * @returns An integer between 0 and 100 representing the percentage.
 */
function calculatePercentage(value: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((value / total) * 100);
}

// ============================================================================
// Makefile Command Execution
// ============================================================================

/**
 * Executes a Makefile target via the backend API and displays the output
 * in the command output panel. Shows a running indicator while the request
 * is in flight, then renders either the success output or an error message.
 *
 * @param command - The Makefile target name to execute (e.g. `"start"`, `"stop"`).
 * @returns A promise that resolves once the output has been rendered.
 */
async function executeMakeCommand(command: string): Promise<void> {
  const outputEl = document.getElementById(ELEMENT_IDS.COMMAND_OUTPUT);
  const textEl = document.getElementById(ELEMENT_IDS.COMMAND_TEXT);

  if (!outputEl || !textEl) {
    console.error('Command output elements not found');
    return;
  }

  showCommandOutput(outputEl, textEl, command);

  try {
    const result = await executeCommand(command);
    displayCommandResult(textEl, result);
  } catch (error) {
    displayCommandError(textEl, error);
  }
}

/**
 * Makes the command output panel visible and sets its initial text to indicate
 * that the given command is currently being executed.
 *
 * @param outputEl - The wrapper element containing the command output panel.
 * @param textEl   - The text element where output content is rendered.
 * @param command  - The command name displayed in the running indicator.
 * @returns void
 */
function showCommandOutput(
  outputEl: HTMLElement,
  textEl: HTMLElement,
  command: string,
): void {
  outputEl.classList.remove(CSS_CLASSES.HIDDEN);
  textEl.textContent = `${UI_MESSAGES.COMMAND_EXECUTING}${command}...\n`;
}

/**
 * Sends a POST request to the Makefile execution endpoint with the specified
 * command and returns the parsed JSON response.
 *
 * @param command - The Makefile target name to execute.
 * @returns A promise resolving to the {@link MakeCommandResult} from the server.
 */
async function executeCommand(command: string): Promise<MakeCommandResult> {
  const response = await fetch(API_ENDPOINTS.MAKEFILE_EXECUTE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  });

  return await response.json();
}

/**
 * Appends the result of a Makefile command execution to the output text element.
 * Displays the standard output on success or the error message on failure.
 *
 * @param textEl - The element whose text content will be updated.
 * @param result - The {@link MakeCommandResult} returned by the execution endpoint.
 * @returns void
 */
function displayCommandResult(
  textEl: HTMLElement,
  result: MakeCommandResult,
): void {
  if (result.success) {
    textEl.textContent += `${UI_MESSAGES.COMMAND_SUCCESS}${result.output || ''}`;
  } else {
    textEl.textContent += `${UI_MESSAGES.COMMAND_FAILED}${result.error || UI_MESSAGES.UNKNOWN_ERROR}`;
  }
}

/**
 * Appends an error message to the command output text element when the fetch
 * request itself fails (e.g. due to a network error).
 *
 * @param textEl - The element whose text content will be updated.
 * @param error  - The caught error, which may or may not be an {@link Error} instance.
 * @returns void
 */
function displayCommandError(textEl: HTMLElement, error: unknown): void {
  const errorMessage =
    error instanceof Error ? error.message : UI_MESSAGES.UNKNOWN_ERROR;
  textEl.textContent += `${UI_MESSAGES.COMMAND_ERROR}${errorMessage}`;
}

// ============================================================================
// Statistics Reset
// ============================================================================

/**
 * Prompts the user for confirmation, then sends a reset request to the backend
 * and reloads the page to reflect the cleared state. Displays an alert if the
 * request fails.
 *
 * @returns A promise that resolves once the reset flow has completed or been cancelled.
 */
async function resetStats(): Promise<void> {
  if (!confirm(UI_MESSAGES.RESET_CONFIRM)) return;

  try {
    await fetch(API_ENDPOINTS.SYSTEM_RESET, { method: 'POST' });
    location.reload();
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : UI_MESSAGES.UNKNOWN_ERROR;
    alert(`${UI_MESSAGES.RESET_FAILED}${errorMessage}`);
  }
}

// ============================================================================
// Initial Data Loading
// ============================================================================

/**
 * Fetches the current system statistics from the backend on page load and
 * passes them to {@link updateStatistics} to populate the dashboard.
 * Errors are logged to the console without interrupting the page lifecycle.
 *
 * @returns A promise that resolves once the statistics have been loaded and rendered.
 */
async function loadInitialData(): Promise<void> {
  try {
    const response = await fetch(API_ENDPOINTS.SYSTEM_STATS);
    const stats: Statistics = await response.json();
    updateStatistics(stats);
  } catch (error) {
    console.error('Failed to load initial data:', error);
  }
}

// ============================================================================
// Initialization
// ============================================================================

window.addEventListener('DOMContentLoaded', (): void => {
  loadInitialData();
});

// ============================================================================
// Global Functions (for onclick handlers in HTML)
// ============================================================================

(window as any).executeMakeCommand = executeMakeCommand;
(window as any).resetStats = resetStats;
(window as any).handleGeometryToken = handleGeometryToken;
(window as any).handleAuthToken = handleAuthToken;
(window as any).updateStatistics = updateStatistics;
