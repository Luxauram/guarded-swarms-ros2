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
 * @file charts.ts
 *
 * Charts Manager.
 *
 * Manages Chart.js visualizations for the main dashboard. Provides
 * initialization and real-time update logic for the approval timeline
 * line chart and the token priority distribution bar chart.
 *
 * Chart.js is expected to be available globally via CDN.
 *
 * @author Luca D'Aurizio
 */

import type { TimelineData } from '../types/charts.types';
import {
  TIMELINE_CONFIG,
  PRIORITY_CONFIG,
  COLORS,
  CHART_OPTIONS,
  ELEMENT_IDS,
} from '../constants/charts.constants';

declare const Chart: any;

// ============================================================================
// State Management
// ============================================================================

let timelineChart: any = null;
let priorityChart: any = null;

const timelineData: TimelineData = {
  labels: [],
  approved: [],
  rejected: [],
};

// ============================================================================
// Chart Initialization
// ============================================================================

/**
 * Entry point for chart setup. Initializes both the approval timeline chart
 * and the priority distribution chart. Should be called once the DOM is ready.
 *
 * @returns void
 */
function initializeCharts(): void {
  initializeTimelineChart();
  initializePriorityChart();
}

/**
 * Initializes the approval timeline line chart on the designated canvas element.
 * The chart displays cumulative approved and rejected token counts over time,
 * with filled areas and shared tooltip interaction mode.
 * Logs an error and returns early if the canvas or its 2D context cannot be obtained.
 *
 * @returns void
 */
function initializeTimelineChart(): void {
  const canvas = document.getElementById(
    ELEMENT_IDS.TIMELINE_CHART,
  ) as HTMLCanvasElement;
  if (!canvas) {
    console.error(`Canvas element '${ELEMENT_IDS.TIMELINE_CHART}' not found`);
    return;
  }

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    console.error('Failed to get 2D context for timeline chart');
    return;
  }

  timelineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timelineData.labels,
      datasets: [
        {
          label: 'Approved',
          data: timelineData.approved,
          borderColor: COLORS.APPROVED.BORDER,
          backgroundColor: COLORS.APPROVED.BACKGROUND,
          tension: CHART_OPTIONS.LINE_TENSION,
          fill: true,
        },
        {
          label: 'Rejected',
          data: timelineData.rejected,
          borderColor: COLORS.REJECTED.BORDER,
          backgroundColor: COLORS.REJECTED.BACKGROUND,
          tension: CHART_OPTIONS.LINE_TENSION,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: TIMELINE_CONFIG.ASPECT_RATIO,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            stepSize: TIMELINE_CONFIG.Y_AXIS_STEP,
            precision: 0,
          },
        },
        x: {
          ticks: {
            maxRotation: TIMELINE_CONFIG.LABEL_ROTATION.MAX,
            minRotation: TIMELINE_CONFIG.LABEL_ROTATION.MIN,
          },
        },
      },
      plugins: {
        legend: {
          position: CHART_OPTIONS.LEGEND.POSITION,
          labels: {
            usePointStyle: true,
            padding: CHART_OPTIONS.LEGEND.PADDING,
          },
        },
      },
      interaction: {
        mode: 'index',
        intersect: false,
      },
    },
  });
}

/**
 * Initializes the token priority distribution bar chart on the designated canvas element.
 * The chart groups incoming tokens into five priority bins (Minimal, Low, Normal, High,
 * Emergency) and displays their counts as colored bars. The legend is hidden since
 * bin labels are shown directly on the x-axis.
 * Logs an error and returns early if the canvas or its 2D context cannot be obtained.
 *
 * @returns void
 */
function initializePriorityChart(): void {
  const canvas = document.getElementById(
    ELEMENT_IDS.PRIORITY_CHART,
  ) as HTMLCanvasElement;
  if (!canvas) {
    console.error(`Canvas element '${ELEMENT_IDS.PRIORITY_CHART}' not found`);
    return;
  }

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    console.error('Failed to get 2D context for priority chart');
    return;
  }

  priorityChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: [...PRIORITY_CONFIG.LABELS],
      datasets: [
        {
          label: 'Token Count',
          data: [0, 0, 0, 0, 0],
          backgroundColor: [...COLORS.PRIORITY.BACKGROUNDS],
          borderColor: [...COLORS.PRIORITY.BORDERS],
          borderWidth: CHART_OPTIONS.BAR_BORDER_WIDTH,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: PRIORITY_CONFIG.ASPECT_RATIO,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            stepSize: PRIORITY_CONFIG.Y_AXIS_STEP,
            precision: 0,
          },
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}

// ============================================================================
// Chart Update Functions
// ============================================================================

/**
 * Appends a new data point to the approval timeline chart using the current
 * timestamp as the x-axis label. If the number of stored data points exceeds
 * {@link TIMELINE_CONFIG.MAX_DATA_POINTS}, the oldest point is removed to maintain
 * a rolling window. The chart is then refreshed without animation to avoid
 * layout shifts during frequent updates.
 * Emits a warning and returns early if the chart has not been initialized yet.
 *
 * @param approved - The cumulative count of approved tokens at this moment.
 * @param rejected - The cumulative count of rejected tokens at this moment.
 * @returns void
 */
function updateTimelineChart(approved: number, rejected: number): void {
  if (!timelineChart) {
    console.warn('Timeline chart not initialized');
    return;
  }

  const now = new Date().toLocaleTimeString();

  timelineData.labels.push(now);
  timelineData.approved.push(approved);
  timelineData.rejected.push(rejected);

  if (timelineData.labels.length > TIMELINE_CONFIG.MAX_DATA_POINTS) {
    timelineData.labels.shift();
    timelineData.approved.shift();
    timelineData.rejected.shift();
  }

  timelineChart.update(CHART_OPTIONS.UPDATE_MODE);
}

/**
 * Increments the count for the priority bin that corresponds to the given
 * priority value, then refreshes the bar chart. Priority values are mapped
 * to bins as follows:
 *
 * - 0–2  → Bin 0 (Minimal)
 * - 3–4  → Bin 1 (Low)
 * - 5–6  → Bin 2 (Normal)
 * - 7–8  → Bin 3 (High)
 * - 9–10 → Bin 4 (Emergency)
 *
 * Logs an error and returns early if the chart has not been initialized yet.
 *
 * @param priority - The numeric priority value of the incoming token (0–10).
 * @returns void
 */
function updatePriorityChart(priority: number): void {
  console.log('updatePriorityChart called with priority:', priority);

  if (!priorityChart) {
    console.error('Priority chart not initialized!');
    return;
  }

  let binIndex: number;
  if (priority <= 2) {
    binIndex = 0;
  } else if (priority <= 4) {
    binIndex = 1;
  } else if (priority <= 6) {
    binIndex = 2;
  } else if (priority <= 8) {
    binIndex = 3;
  } else {
    binIndex = 4;
  }

  console.log(`Priority ${priority} → Bin ${binIndex}`);
  console.log('Current data before:', priorityChart.data.datasets[0].data);

  priorityChart.data.datasets[0].data[binIndex]++;

  console.log('Current data after:', priorityChart.data.datasets[0].data);

  priorityChart.update(CHART_OPTIONS.UPDATE_MODE);

  console.log('Chart updated');
}

// ============================================================================
// Initialization
// ============================================================================

window.addEventListener('DOMContentLoaded', (): void => {
  initializeCharts();
});

// ============================================================================
// Global API Exports (for cross-module communication)
// ============================================================================

(window as any).updatePriorityChart = updatePriorityChart;
(window as any).updateTimelineChart = updateTimelineChart;
