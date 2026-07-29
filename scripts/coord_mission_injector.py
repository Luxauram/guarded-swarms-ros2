#!/usr/bin/env python3
# Copyright 2026 Luca D'Aurizio
# Licensed under the Apache License, Version 2.0 (the "License").
"""Inject a fixed number of MissionTokens for the coordination-overhead bench.

Publishes M authorised InterceptMission tokens on /mission_tokens, each with a
distinct id and a distinct target position so the dispatch's nearest-UAV choice
has something to discriminate. Used by bench_coordination.sh (Group 5): the
dispatch node, running with a fleet of size N, turns each mission into vehicle
tasks, and we measure how the task volume scales with N.

Usage:  python3 coord_mission_injector.py <n_missions>
"""
import sys
import time
import math

import rclpy
from rclpy.node import Node
from guarded_swarms_msgs.msg import MissionToken


class MissionInjector(Node):
    def __init__(self, n_missions):
        super().__init__("coord_mission_injector")
        self.pub = self.create_publisher(MissionToken, "/mission_tokens", 10)
        self.n = n_missions

    def run(self):
        # Wait until the dispatch node has actually subscribed to
        # /mission_tokens before publishing: with a large fleet the dispatch
        # takes longer to initialise (it declares one subscription per vehicle),
        # and any mission published before it is ready is lost. Poll the
        # publisher's subscription count, with a timeout so we never hang.
        waited = 0.0
        while self.pub.get_subscription_count() < 1 and waited < 15.0:
            rclpy.spin_once(self, timeout_sec=0.1)
            time.sleep(0.1)
            waited += 0.2
        if self.pub.get_subscription_count() < 1:
            self.get_logger().warn(
                "no subscriber on /mission_tokens after 15 s; publishing anyway")
        else:
            # a small extra settle once connected, so the first message is not
            # raced against the subscription becoming fully active
            time.sleep(0.5)
        for i in range(self.n):
            m = MissionToken()
            m.mission_id = f"bench-mission-{i}"
            m.type = MissionToken.TYPE_INTERCEPT
            m.target_id = f"intruder-{i}"
            # spread targets on a circle so nearest_uav gets varied distances
            ang = 2.0 * math.pi * i / max(self.n, 1)
            m.target_position.x = 60.0 * math.cos(ang)
            m.target_position.y = 60.0 * math.sin(ang)
            m.target_position.z = 15.0
            m.justification = [f"bench:{i}"]
            m.authorised_by = "bench_supervisor"  # non-empty: a valid mission
            m.t = self.get_clock().now().to_msg()
            m.ttl_s = 30.0
            self.pub.publish(m)
            # space them out so none are dropped by the queue
            time.sleep(0.15)
        # give the dispatch time to emit the tasks before we exit
        time.sleep(2.0)
        self.get_logger().info(f"injected {self.n} missions")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rclpy.init()
    node = MissionInjector(n)
    node.run()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()