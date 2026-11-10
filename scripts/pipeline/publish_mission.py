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

"""Publish one MissionToken to /mission_tokens and confirm its dispatch.

A small command-line publisher used by the pipeline tests to place a single
mission on the dispatch topic directly, so the dispatch transition (T7) and the
UAV safety layer can be exercised without driving the sensing and
mission-release chain. The fields are given on the command line.

The node is short-lived, so it keeps republishing the mission (the dispatch is
idempotent per target_id) and watches /vehicle_tasks until the dispatch
transition turns the mission into a task, then exits 0. If no task appears
within the timeout it exits 1, so the caller can repeat the run: on a loaded
machine the dispatch node can take longer to discover a short-lived publisher
than a single one-shot publish stays alive, and the message is then lost.
"""
import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

from guarded_swarms_msgs.msg import MissionToken, VehicleTask
from geometry_msgs.msg import Point


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mission-id", default="test-mission")
    ap.add_argument("--type", default="intercept")
    ap.add_argument("--target-id", default="intruder")
    ap.add_argument("--x", type=float, required=True)
    ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--z", type=float, default=12.0)
    ap.add_argument("--ttl", type=float, default=30.0)
    ap.add_argument("--confirm-timeout", type=float, default=15.0)
    args = ap.parse_args()

    rclpy.init()
    node = Node(
        "mission_test_publisher",
        parameter_overrides=[Parameter("use_sim_time", value=True)],
    )
    pub = node.create_publisher(MissionToken, "/mission_tokens", 10)

    dispatched = {"seen": False}

    def on_task(task):
        if task.target_id == args.target_id:
            dispatched["seen"] = True

    node.create_subscription(VehicleTask, "/vehicle_tasks", on_task, 10)

    # Wait for a subscriber on /mission_tokens and for the simulated clock, so
    # the message is stamped in simulated time. Give up after ~10 s.
    for _ in range(200):
        rclpy.spin_once(node, timeout_sec=0.05)
        if pub.get_subscription_count() > 0 and node.get_clock().now().nanoseconds > 0:
            break

    msg = MissionToken()
    msg.mission_id = args.mission_id
    msg.type = args.type
    msg.target_id = args.target_id
    msg.target_position = Point(x=args.x, y=args.y, z=args.z)
    msg.justification = []
    msg.t = node.get_clock().now().to_msg()
    msg.ttl_s = args.ttl

    node.get_logger().info(
        f"publishing mission '{args.mission_id}' at ({args.x}, {args.y}, {args.z})"
    )

    # Republish until the dispatch transition turns the mission into a task, or
    # until the timeout. The repeats are idempotent (T7 dispatches once per
    # target_id); the loop also rides out the discovery of this short-lived
    # publisher by the already-running dispatch node.
    start = time.monotonic()
    last_pub = -1.0
    while rclpy.ok() and not dispatched["seen"]:
        if time.monotonic() - start >= args.confirm_timeout:
            break
        now = time.monotonic()
        if now - last_pub >= 0.3:
            pub.publish(msg)
            last_pub = now
        rclpy.spin_once(node, timeout_sec=0.1)

    rc = 0 if dispatched["seen"] else 1
    if rc == 0:
        node.get_logger().info(f"mission '{args.mission_id}' dispatched")
    else:
        node.get_logger().error(
            f"mission '{args.mission_id}' not dispatched within "
            f"{args.confirm_timeout:.0f} s"
        )

    node.destroy_node()
    rclpy.shutdown()
    sys.exit(rc)


if __name__ == "__main__":
    main()