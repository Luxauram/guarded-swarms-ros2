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
 * @file charts.constants.ts
 *
 * Chart Constants.
 *
 * Configuration values for Chart.js visualizations.
 *
 * @author Luca D'Aurizio
 */

// ============================================================================
// Timeline Chart Configuration
// ============================================================================

export const TIMELINE_CONFIG = {
  MAX_DATA_POINTS: 20,
  ASPECT_RATIO: 2,
  Y_AXIS_STEP: 1,
  LABEL_ROTATION: {
    MIN: 45,
    MAX: 45,
  },
} as const;

// ============================================================================
// Priority Chart Configuration
// ============================================================================

export const PRIORITY_CONFIG = {
  LEVELS: [0, 1, 2, 3, 4] as const,
  LABELS: [
    'Minimal (0-2)',
    'Low (3-4)',
    'Normal (5-6)',
    'High (7-8)',
    'Emergency (9-10)',
  ] as const,
  ASPECT_RATIO: 2,
  Y_AXIS_STEP: 1,
} as const;

// ============================================================================
// Color Schemes
// ============================================================================

export const COLORS = {
  APPROVED: {
    BORDER: 'rgb(34, 197, 94)',
    BACKGROUND: 'rgba(34, 197, 94, 0.1)',
  },
  REJECTED: {
    BORDER: 'rgb(239, 68, 68)',
    BACKGROUND: 'rgba(239, 68, 68, 0.1)',
  },
  PRIORITY: {
    BACKGROUNDS: [
      'rgba(189, 195, 199, 0.8)', // Minimal - light gray
      'rgba(149, 165, 166, 0.8)', // Low - gray
      'rgba(52, 152, 219, 0.8)', // Normal - blue
      'rgba(243, 156, 18, 0.8)', // High - orange
      'rgba(231, 76, 60, 0.8)', // Emergency - red
    ],
    BORDERS: [
      'rgb(189, 195, 199)', // Minimal
      'rgb(149, 165, 166)', // Low
      'rgb(52, 152, 219)', // Normal
      'rgb(243, 156, 18)', // High
      'rgb(231, 76, 60)', // Emergency
    ],
  },
} as const;

// ============================================================================
// Chart Options
// ============================================================================

export const CHART_OPTIONS = {
  LINE_TENSION: 0.4,
  BAR_BORDER_WIDTH: 2,
  UPDATE_MODE: 'none' as const, // Disable for real-time updates
  LEGEND: {
    POSITION: 'top' as const,
    PADDING: 10,
  },
} as const;

// ============================================================================
// DOM Element IDs
// ============================================================================

export const ELEMENT_IDS = {
  TIMELINE_CHART: 'timeline-chart',
  PRIORITY_CHART: 'priority-chart',
} as const;
