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
 * @file charts.types.ts
 *
 * Chart Types and Interfaces.
 *
 * Type definitions for Chart.js visualizations.
 *
 * @author Luca D'Aurizio
 */

export declare const Chart: any;

export interface TimelineData {
  labels: string[];
  approved: number[];
  rejected: number[];
}

export type PriorityBinIndex = 0 | 1 | 2 | 3 | 4;

export type PriorityValue = number;
