#!/usr/bin/env python3
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
@file dashboard.py

Real-time visualization dashboard for guarded swarms coordination.

This dashboard provides live monitoring of the multi-agent coordination system,
displaying token flows, spatial conflicts, and authorization decisions through
a Tkinter-based graphical interface.

The dashboard architecture:
1. DashboardNode subscribes to ROS 2 token topics
2. ROS 2 callbacks forward messages to GUI thread-safely
3. GUI updates spatial map, event log, and statistics in real-time
4. Dual-threaded design: ROS 2 spin in background, Tkinter in main thread

Features:
- 2D spatial map with AABB visualization
- Live event stream with color-coded decisions
- Per-agent and global statistics tracking
- Priority-based visual indicators
- Approval rate metrics

Typical usage:
    ros2 run guarded_swarms_coordinator dashboard

@author Luca D'Aurizio
"""

import tkinter as tk
from tkinter import ttk
import rclpy
from rclpy.node import Node
from guarded_swarms_coordinator.msg import GeometryToken as GeometryTokenMsg
from guarded_swarms_coordinator.msg import AuthToken as AuthTokenMsg
from collections import deque
import threading


class DashboardNode(Node):
    """
    ROS 2 subscriber node for dashboard data ingestion.

    Subscribes to geometry and authorization token topics, forwarding
    received messages to the GUI layer for visualization.
    """

    # ========================================================================
    # Constants
    # ========================================================================

    TOPIC_GEOMETRY_TOKENS = "/geometry_tokens"
    TOPIC_AUTH_TOKENS = "/auth_tokens"
    QUEUE_SIZE = 10

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(self, dashboard):
        """
        Initialize dashboard ROS 2 node.

        @param dashboard GuardedSwarmsDashboard instance for data forwarding
        """
        super().__init__("dashboard_node")
        self.dashboard = dashboard

        self.geometry_sub = self.create_subscription(
            GeometryTokenMsg, self.TOPIC_GEOMETRY_TOKENS, self.geometry_callback, self.QUEUE_SIZE
        )

        self.auth_sub = self.create_subscription(
            AuthTokenMsg, self.TOPIC_AUTH_TOKENS, self.auth_callback, self.QUEUE_SIZE
        )

        self.get_logger().info("Dashboard node initialized")

    # ========================================================================
    # Callbacks
    # ========================================================================

    def geometry_callback(self, msg):
        """
        Forwards geometry token to dashboard GUI.

        @param msg Incoming GeometryTokenMsg
        """
        self.dashboard.add_geometry_token(msg)

    def auth_callback(self, msg):
        """
        Forwards authorization token to dashboard GUI.

        @param msg Incoming AuthTokenMsg
        """
        self.dashboard.add_auth_token(msg)


class GuardedSwarmsDashboard:
    """
    Real-time visualization dashboard for guarded swarms coordination.

    Provides live monitoring through a Tkinter-based GUI, displaying spatial
    requests, authorization decisions, and system-wide statistics.
    """

    # ========================================================================
    # Constants
    # ========================================================================

    WINDOW_WIDTH = 1400
    WINDOW_HEIGHT = 800

    MAP_SIZE = 600
    MAP_SCALE = 15
    MAP_GRID_INTERVAL = 5

    MAX_DISPLAYED_TOKENS = 10

    MAX_EVENTS = 20

    AGENT_COLORS = {
        "agent_A": "#3498db",
        "agent_B": "#e74c3c",
        "agent_C": "#2ecc71",
        "agent_D": "#f39c12",
    }

    PRIORITY_COLORS = {
        "emergency": "#e74c3c",
        "high": "#f39c12",
        "normal": "#3498db",
        "low": "#95a5a6",
        "minimal": "#bdc3c7",
    }

    PRIORITY_BORDER_THRESHOLD = 5
    PRIORITY_BORDER_LOW = 2
    PRIORITY_BORDER_HIGH = 4

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(self):
        """Initialize dashboard GUI and data structures."""
        self.root = tk.Tk()
        self.root.title("Guarded Swarms Coordination Dashboard")
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")

        self.geometry_tokens = deque(maxlen=100)
        self.auth_tokens = deque(maxlen=100)
        self.event_log = deque(maxlen=self.MAX_EVENTS)

        self.stats = {
            "total_requests": 0,
            "approved": 0,
            "rejected": 0,
            "revoked": 0,
        }

        self.agent_stats = {}
        self.arbitration_mode = "unknown"
        self.first_token_received = False

        self._build_ui()

    def _build_ui(self):
        """Constructs dashboard user interface layout."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.title_label = ttk.Label(
            main_frame,
            text="Guarded Swarms Coordination Dashboard",
            font=("Helvetica", 18, "bold"),
        )
        self.title_label.grid(row=0, column=0, columnspan=2, pady=(0, 5))

        self.mode_label = ttk.Label(
            main_frame,
            text="Arbitration Mode: Loading...",
            font=("Helvetica", 10, "italic"),
            foreground="gray",
        )
        self.mode_label.grid(row=1, column=0, columnspan=2, pady=(0, 10))

        self._build_spatial_map(main_frame)
        self._build_right_panel(main_frame)
        self._build_legend(main_frame)

    def _build_spatial_map(self, parent):
        """
        Constructs spatial map panel with coordinate grid.

        The map displays spatial area requests (not agent positions). Each
        rectangle represents a requested operational volume with:
        - Position: center of requested area
        - Size: bounding box dimensions
        - Label: agent identifier (A, B, C, D)
        - Color: agent-specific color code

        As agents publish new requests, rectangles appear to "move" - these
        are actually distinct requests at different locations over time.

        @param parent Parent Tkinter frame
        """
        map_frame = ttk.LabelFrame(parent, text="Spatial Map (Top View)", padding="10")
        map_frame.grid(row=2, column=0, padx=(0, 10), sticky=(tk.N, tk.S, tk.W, tk.E))

        self.canvas = tk.Canvas(map_frame, width=self.MAP_SIZE, height=self.MAP_SIZE, bg="white")
        self.canvas.pack()

        self._draw_grid()

    def _build_right_panel(self, parent):
        """
        Constructs event log and statistics panels.

        @param parent Parent Tkinter frame
        """
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=2, column=1, sticky=(tk.N, tk.S, tk.W, tk.E))

        log_frame = ttk.LabelFrame(right_frame, text="Event Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.event_listbox = tk.Listbox(log_frame, height=15, font=("Courier", 9))
        self.event_listbox.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.event_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.event_listbox.config(yscrollcommand=scrollbar.set)

        stats_frame = ttk.LabelFrame(right_frame, text="Statistics", padding="10")
        stats_frame.pack(fill=tk.BOTH, expand=True)

        self.stats_text = tk.Text(stats_frame, height=12, width=50, font=("Courier", 10))
        self.stats_text.pack(fill=tk.BOTH, expand=True)

    def _build_legend(self, parent):
        """
        Constructs legend panel with color codes.

        @param parent Parent Tkinter frame
        """
        legend_frame = ttk.LabelFrame(parent, text="Legend", padding="10")
        legend_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky=(tk.W, tk.E))

        legend_text = (
            "Agents: [A] Blue | [B] Red | [C] Green | [D] Orange\n"
            "Priority Border Colors: RED=Emergency(9-10) | ORANGE=High(7-8) | BLUE=Normal(5-6) | GRAY=Low(3-4) | LIGHT=Minimal(0-2)\n"
            "Status: [✓] Approved | [✗] Rejected | [⚠] Revoked"
        )
        ttk.Label(legend_frame, text=legend_text, font=("Helvetica", 10)).pack()

    def _draw_grid(self):
        """Renders coordinate grid and axes on spatial map canvas."""
        grid_step = self.MAP_SCALE * self.MAP_GRID_INTERVAL

        for i in range(0, self.MAP_SIZE + 1, grid_step):
            self.canvas.create_line(i, 0, i, self.MAP_SIZE, fill="lightgray", dash=(2, 2))
            self.canvas.create_line(0, i, self.MAP_SIZE, i, fill="lightgray", dash=(2, 2))

        center = self.MAP_SIZE // 2
        self.canvas.create_line(center, 0, center, self.MAP_SIZE, fill="gray", width=2)
        self.canvas.create_line(0, center, self.MAP_SIZE, center, fill="gray", width=2)

        self.canvas.create_text(center + 5, 15, text="N", font=("Helvetica", 10, "bold"))
        self.canvas.create_text(
            self.MAP_SIZE - 15, center - 5, text="E", font=("Helvetica", 10, "bold")
        )

    # ========================================================================
    # Data Ingestion
    # ========================================================================

    def _get_priority_color(self, priority: int) -> str:
        """
        Gets border color based on priority level.

        @param priority Priority level 0-10
        @return Hex color code
        """
        if priority >= 9:
            return self.PRIORITY_COLORS["emergency"]
        elif priority >= 7:
            return self.PRIORITY_COLORS["high"]
        elif priority >= 5:
            return self.PRIORITY_COLORS["normal"]
        elif priority >= 3:
            return self.PRIORITY_COLORS["low"]
        else:
            return self.PRIORITY_COLORS["minimal"]

    def add_geometry_token(self, msg):
        """
        Processes incoming geometry token from ROS 2 subscription.

        Updates internal buffers, statistics, and triggers visualization refresh.

        @param msg GeometryTokenMsg from agent
        """
        self.geometry_tokens.append(msg)
        self.stats["total_requests"] += 1

        if not self.first_token_received and self.arbitration_mode == "unknown":
            self.first_token_received = True
            self.mode_label.config(
                text="Arbitration Mode: Monitoring for conflicts...", foreground="gray"
            )

        agent_id = msg.base_token.agent_id
        if agent_id not in self.agent_stats:
            self.agent_stats[agent_id] = {"requests": 0, "approved": 0, "rejected": 0}
        self.agent_stats[agent_id]["requests"] += 1

        event = (
            f"[REQ] {agent_id} → "
            f"pos=({msg.position[0]:.1f}, {msg.position[1]:.1f}) "
            f"priority={msg.priority}"
        )
        self._add_event(event)

        self._update_map()
        self._update_stats()

    def add_auth_token(self, msg):
        """
        Processes incoming authorization token from ROS 2 subscription.

        Updates statistics and event log based on coordinator decision.
        Detects arbitration mode from reason patterns in auth messages.

        @param msg AuthTokenMsg from coordinator
        """
        self.auth_tokens.append(msg)

        agent_id = msg.base_token.agent_id
        approved = msg.approved
        reason = msg.reason

        if self.arbitration_mode == "unknown":
            if approved and reason == "approved":
                pass
            elif "priority" in reason.lower() and (
                "preempt" in reason.lower() or "override" in reason.lower()
            ):
                self.arbitration_mode = "hybrid" if "override" in reason.lower() else "priority"
                self.mode_label.config(
                    text=f"Arbitration Mode: {self.arbitration_mode.upper()}", foreground="blue"
                )
            elif not approved and "conflict" in reason.lower():
                if "priority" not in reason.lower():
                    self.arbitration_mode = "fcfs"
                    self.mode_label.config(text="Arbitration Mode: FCFS", foreground="blue")

        if "preempted_by" in reason:
            if self.arbitration_mode != "priority":
                self.arbitration_mode = "priority"
                self.mode_label.config(text="Arbitration Mode: PRIORITY", foreground="blue")
        elif "priority_override" in reason:
            if self.arbitration_mode != "hybrid":
                self.arbitration_mode = "hybrid"
                self.mode_label.config(text="Arbitration Mode: HYBRID", foreground="blue")

        if "revoked" in reason:
            self.stats["revoked"] += 1
            symbol = "⚠"
            color = "orange"
        elif approved:
            self.stats["approved"] += 1
            self.agent_stats[agent_id]["approved"] += 1
            symbol = "✓"
            color = "green"
        else:
            self.stats["rejected"] += 1
            self.agent_stats[agent_id]["rejected"] += 1
            symbol = "✗"
            color = "red"

        event = f"[{symbol}] {agent_id} → {reason}"
        self._add_event(event, color)

        self._update_stats()

    def _add_event(self, text, color="black"):
        """
        Appends event to scrolling log with color coding.

        @param text Event description string
        @param color Text color for visual categorization
        """
        self.event_log.append((text, color))
        self.event_listbox.insert(tk.END, text)
        self.event_listbox.itemconfig(tk.END, foreground=color)
        self.event_listbox.see(tk.END)

    # ========================================================================
    # Visualization Updates
    # ========================================================================

    def _update_map(self):
        """
        Redraws spatial map with most recent geometry tokens.

        Displays only the most recent request per agent to show current
        spatial allocation requests without historical clutter. This provides
        a cleaner view of active coordination state.
        """
        self.canvas.delete("token")

        agent_latest = {}
        for msg in self.geometry_tokens:
            agent_id = msg.base_token.agent_id
            agent_latest[agent_id] = msg

        for msg in agent_latest.values():
            self._draw_token(msg)

    def _draw_token(self, msg):
        """
        Renders single geometry token as AABB on spatial map.

        Displays agent ID, priority level, and uses color-coded borders
        based on priority for quick visual identification.

        @param msg GeometryTokenMsg to visualize
        """
        center = self.MAP_SIZE // 2
        x = center + int(msg.position[0] * self.MAP_SCALE)
        y = center - int(msg.position[1] * self.MAP_SCALE)

        width = int(msg.dimensions[0] * self.MAP_SCALE)
        height = int(msg.dimensions[1] * self.MAP_SCALE)

        x1 = x - width // 2
        y1 = y - height // 2
        x2 = x + width // 2
        y2 = y + height // 2

        agent_id = msg.base_token.agent_id
        agent_color = self.AGENT_COLORS.get(agent_id, "gray")

        priority = msg.priority
        priority_color = self._get_priority_color(priority)

        border_width = (
            self.PRIORITY_BORDER_HIGH
            if priority > self.PRIORITY_BORDER_THRESHOLD
            else self.PRIORITY_BORDER_LOW
        )

        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline=priority_color,
            width=border_width,
            fill="",
            tags="token",
        )

        label_text = f"{agent_id[-1]}\nP:{priority}"
        self.canvas.create_text(
            x, y, text=label_text, font=("Helvetica", 9, "bold"), fill=agent_color, tags="token"
        )

    def _update_stats(self):
        """Refreshes statistics panel with current metrics."""
        self.stats_text.delete("1.0", tk.END)

        total = self.stats["total_requests"]
        approved = self.stats["approved"]
        rejected = self.stats["rejected"]
        revoked = self.stats["revoked"]

        approve_rate = (approved / total * 100) if total > 0 else 0

        mode_display = (
            self.arbitration_mode.upper() if self.arbitration_mode != "unknown" else "DETECTING..."
        )

        stats_str = f"""OVERALL STATISTICS
{'=' * 40}
Arbitration Mode: {mode_display}
Total Requests:   {total}
Approved:         {approved} ({approve_rate:.1f}%)
Rejected:         {rejected}
Revoked:          {revoked}

AGENT BREAKDOWN
{'=' * 40}
"""

        for agent_id in sorted(self.agent_stats.keys()):
            stats = self.agent_stats[agent_id]
            req = stats["requests"]
            appr = stats["approved"]
            rej = stats["rejected"]
            rate = (appr / req * 100) if req > 0 else 0

            stats_str += f"{agent_id}: {appr}/{req} ({rate:.0f}% approved)\n"

        self.stats_text.insert("1.0", stats_str)

    # ========================================================================
    # Main Loop
    # ========================================================================

    def run(self):
        """Starts Tkinter main event loop."""
        self.root.mainloop()


# ============================================================================
# Main Function
# ============================================================================


def main(args=None):
    """
    Main entry point for dashboard application.

    Initializes ROS 2, spawns background thread for message processing,
    and launches Tkinter GUI in main thread for responsiveness.

    The dual-threaded architecture ensures:
    - ROS 2 callbacks execute without blocking GUI
    - Tkinter remains responsive to user interactions
    - Thread-safe message forwarding via callback pattern

    @param args Command line arguments (unused, handled by ROS 2)
    """
    rclpy.init(args=args)

    dashboard = GuardedSwarmsDashboard()
    node = DashboardNode(dashboard)

    def spin_thread():
        rclpy.spin(node)

    thread = threading.Thread(target=spin_thread, daemon=True)
    thread.start()

    try:
        dashboard.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
