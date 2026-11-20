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
sim_sleep.py - wait a number of seconds of simulated time.

Reads the simulation clock on /clock and returns once it has advanced by the
given number of seconds since the first message received. The simulation can
run slower than real time, and does with more vehicles, so a wait on the real
clock such as `sleep` would cover less simulated time than asked.

If /clock does not advance for STALL seconds of real time (--stall, 30 by
default), including when no message arrives at all, it gives up: the
simulation has stopped.

Usage:
    python3 scripts/pipeline/sim_sleep.py SECONDS [--stall STALL]

Exit codes: 0 the simulated time has passed; 1 /clock stopped advancing or
never arrived; 2 wrong arguments; 130 stopped with Ctrl-C.
"""
import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock


def main():
    parser = argparse.ArgumentParser(
        description="Wait a number of seconds of simulated time (/clock).")
    parser.add_argument("seconds", type=float,
                        help="simulated seconds to wait")
    parser.add_argument("--stall", type=float, default=30.0,
                        help="real seconds without /clock advancing before "
                             "giving up (default 30)")
    args = parser.parse_args()
    if args.seconds < 0 or args.stall <= 0:
        parser.error("SECONDS must be at least 0 and --stall more than 0")

    rclpy.init()
    node = Node("sim_sleep")
    # First and latest simulated time received, and the real time at which
    # the clock last advanced (or the start, before the first message).
    clock = {"first": None, "latest": None, "advanced": time.monotonic()}

    def on_clock(msg):
        t = msg.clock.sec + msg.clock.nanosec * 1e-9
        if clock["first"] is None:
            clock["first"] = t
        if clock["latest"] is None or t > clock["latest"]:
            clock["latest"] = t
            clock["advanced"] = time.monotonic()

    # Best effort matches the clock bridge whatever reliability it offers.
    node.create_subscription(Clock, "/clock", on_clock,
                             qos_profile_sensor_data)
    code = 0
    try:
        while True:
            rclpy.spin_once(node, timeout_sec=0.2)
            if (clock["first"] is not None
                    and clock["latest"] - clock["first"] >= args.seconds):
                break
            if time.monotonic() - clock["advanced"] > args.stall:
                print("sim_sleep: /clock did not advance for "
                      f"{args.stall:g} s of real time", file=sys.stderr)
                code = 1
                break
    except KeyboardInterrupt:
        code = 130
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
