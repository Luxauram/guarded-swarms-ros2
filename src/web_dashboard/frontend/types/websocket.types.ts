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
 * @file websocket.types.ts
 *
 * WebSocket Types and Interfaces.
 *
 * Type definitions for real-time communication.
 *
 * @author Luca D'Aurizio
 */

export interface BaseToken {
  token_id: string;
  timestamp: string;
  agent_id: string;
  token_type: string;
  signature: string;
}

export interface GeometryTokenData {
  base_token: BaseToken;
  position: number[];
  dimensions: number[];
  duration: number;
  priority: number;
}

export interface AuthTokenData {
  base_token: BaseToken;
  geometry_token_id: string;
  approved: boolean;
  coordinator_id: string;
  reason: string;
}

export interface AgentStats {
  requests: number;
  approved: number;
}

export interface Statistics {
  total_requests: number;
  approved: number;
  rejected: number;
  approval_rate: number;
  agents: Record<string, AgentStats>;
}

export type EventType = 'geometry' | 'auth' | 'stats_update' | 'connection';

export interface WebSocketMessage {
  event_type: EventType;
  data: GeometryTokenData | AuthTokenData | Statistics | unknown;
}

export type ConnectionStatus =
  | 'connected'
  | 'disconnected'
  | 'connecting'
  | 'error';
