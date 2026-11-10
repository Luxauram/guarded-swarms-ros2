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
publish_sensors.py - the sensor and command feed of the Safety Board bench.

It feeds the board the four readings it needs (IMU, proximity, battery,
altitude) and a constant "go" command on /actuator_cmd_raw, at a fixed rate on
the wall clock. The readings are well within any threshold, so with the bench's
permissive limits the only veto the board can raise is sensor staleness - the
one check that reads the clock.

Two events drive the experiment, each at a wall-clock instant from the start:
  --stop-at S    the four sensor streams stop at S (the command keeps flowing);
                 the board should then raise a staleness veto after its window.
  --danger-at S  the proximity reading drops to --danger-range at S and keeps
                 flowing; the board should veto at once, on the value, whatever
                 its clock is doing.
A run sets one of the two. The clock is driven separately by publish_clock.py.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/pipeline/publish_sensors.py --stop-at 20
"""

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import BatteryState, Imu, Range
from std_msgs.msg import Float32


class SensorFeed(Node):
    """Publishes the board's sensors and raw command on the wall clock."""

    def __init__(self, args):
        super().__init__("sensor_feed")
        # The feed is timed on the wall clock, independently of the simulated
        # clock the board reads, so a held clock does not stop the feed.
        self.set_parameters(
            [Parameter("use_sim_time", Parameter.Type.BOOL, False)])
        self.args = args
        self.imu_pub = self.create_publisher(Imu, "/drone/imu", 10)
        self.prox_pub = self.create_publisher(Range, "/drone/proximity", 10)
        self.batt_pub = self.create_publisher(BatteryState, "/drone/battery",
                                              10)
        self.alt_pub = self.create_publisher(Float32, "/drone/altitude", 10)
        self.raw_pub = self.create_publisher(Float32, "/actuator_cmd_raw", 10)
        self.start = time.monotonic()
        self.stopped = False
        self.dangerous = False
        self.timer = self.create_timer(1.0 / args.rate, self._tick)

    def _tick(self):
        a = self.args
        el = time.monotonic() - self.start

        raw = Float32()
        raw.data = float(a.raw)
        self.raw_pub.publish(raw)

        if a.stop_at is not None and el >= a.stop_at:
            if not self.stopped:
                self.stopped = True
                self.get_logger().info(
                    "sensor streams stopped at {:.2f} s".format(el))
            return

        prox = Range()
        if a.danger_at is not None and el >= a.danger_at:
            prox.range = float(a.danger_range)
            if not self.dangerous:
                self.dangerous = True
                self.get_logger().info(
                    "proximity dropped to {:.2f} m at {:.2f} s".format(
                        a.danger_range, el))
        else:
            prox.range = float(a.proximity)
        self.prox_pub.publish(prox)

        imu = Imu()
        imu.orientation.w = 1.0   # level: zero roll and pitch
        self.imu_pub.publish(imu)

        batt = BatteryState()
        batt.percentage = float(a.battery)   # 0..1; the board reads it as %
        self.batt_pub.publish(batt)

        alt = Float32()
        alt.data = float(a.altitude)
        self.alt_pub.publish(alt)


def main():
    p = argparse.ArgumentParser(
        description="Feed the Safety Board bench its sensors and command.")
    p.add_argument("--rate", type=float, default=10.0,
                   help="publish rate per stream, Hz")
    p.add_argument("--raw", type=float, default=0.7,
                   help="constant actuator_cmd_raw value (the 'go' command)")
    p.add_argument("--proximity", type=float, default=50.0,
                   help="safe proximity range, m")
    p.add_argument("--battery", type=float, default=1.0,
                   help="battery fraction, 0..1")
    p.add_argument("--altitude", type=float, default=10.0,
                   help="altitude reading, m")
    p.add_argument("--stop-at", type=float, default=None,
                   help="stop the four sensor streams at this instant (s)")
    p.add_argument("--danger-at", type=float, default=None,
                   help="drop proximity to --danger-range at this instant (s)")
    p.add_argument("--danger-range", type=float, default=5.0,
                   help="proximity range after --danger-at, m")
    args = p.parse_args()

    rclpy.init()
    node = SensorFeed(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()