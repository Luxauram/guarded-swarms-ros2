#!/usr/bin/env python3
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""
publish_clock.py - a controllable simulation-clock source for the Safety Board
bench.

The Safety Board reads the simulated clock from /clock (use_sim_time) and
judges a sensor stale when now - its last arrival exceeds the staleness window.
On the isolated bench there is no simulator to publish /clock, so this node is
the clock source. It advances simulated time from zero at a fixed rate; with
--freeze-at it stops advancing at a chosen instant and keeps republishing that
value, so the clock the board sees is held still. That is the stimulus of the
clock experiment: it checks whether the board's time-based staleness watchdog
can be defeated by holding its clock, while its value thresholds, which read no
clock, still act.

The node runs on the wall clock: it is the source of simulated time, so it must
not consume it. Without --freeze-at it advances for the whole run (the control
arm).

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/pipeline/publish_clock.py                  # advances
    python3 scripts/pipeline/publish_clock.py --freeze-at 20   # held at t=20 s
"""

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock


class ClockSource(Node):
    """Publishes /clock from the wall clock, with an optional freeze."""

    def __init__(self, args):
        super().__init__("clock_source")
        # This node is the source of simulated time, so it must stay on the
        # wall clock: never follow /clock.
        self.set_parameters(
            [Parameter("use_sim_time", Parameter.Type.BOOL, False)])
        self.args = args
        self.pub = self.create_publisher(Clock, "/clock", 10)
        self.wall0 = time.monotonic()
        self.frozen = False
        self.timer = self.create_timer(1.0 / args.rate, self._tick)

    def _sim_seconds(self):
        t = (time.monotonic() - self.wall0) * self.args.speed
        if self.args.freeze_at is not None and t >= self.args.freeze_at:
            t = self.args.freeze_at
            if not self.frozen:
                self.frozen = True
                self.get_logger().info(
                    "clock held at {:.3f} s".format(t))
        return t

    def _tick(self):
        t = self._sim_seconds()
        msg = Clock()
        msg.clock.sec = int(t)
        msg.clock.nanosec = int(round((t - int(t)) * 1e9))
        self.pub.publish(msg)


def main():
    p = argparse.ArgumentParser(
        description="Publish a controllable /clock for the Safety Board bench.")
    p.add_argument("--rate", type=float, default=100.0,
                   help="publish rate, Hz")
    p.add_argument("--speed", type=float, default=1.0,
                   help="simulated seconds per wall second before any freeze")
    p.add_argument("--freeze-at", type=float, default=None,
                   help="hold simulated time at this instant (s); "
                        "omit to advance for the whole run")
    p.add_argument("--run-for", type=float, default=None,
                   help="exit after this many wall seconds; "
                        "omit to run until stopped")
    args = p.parse_args()

    rclpy.init()
    node = ClockSource(args)
    try:
        if args.run_for is None:
            rclpy.spin(node)
        else:
            end = time.monotonic() + args.run_for
            while rclpy.ok() and time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()
