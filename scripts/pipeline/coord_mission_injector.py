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

DEFAULT_N_MISSIONS = 10       # missions injected when no argument is given
SUBSCRIBER_TIMEOUT_S = 15.0   # max wait for the dispatch to subscribe
SETTLE_AFTER_CONNECT_S = 0.5  # extra settle once a subscriber is present
TARGET_RING_RADIUS_M = 60.0   # radius of the circle the targets are placed on
TARGET_ALTITUDE_M = 15.0      # z of every injected target
MISSION_TTL_S = 30.0          # time-to-live stamped on each mission
INTER_MISSION_GAP_S = 0.15    # spacing between publishes, so none are dropped
DISPATCH_DRAIN_S = 2.0        # wait for the dispatch to emit tasks before exit


class MissionInjector(Node):
    """ROS 2 node that publishes a burst of authorised missions for the bench."""

    def __init__(self, n_missions):
        """Initialise the node and its /mission_tokens publisher.

        @param n_missions  Number of missions to publish when run() is called.
        @return            None.
        """
        super().__init__("coord_mission_injector")
        self.pub = self.create_publisher(MissionToken, "/mission_tokens", 10)
        self.n = n_missions

    def run(self):
        """Publish the configured number of missions, then drain and return.

        Waits for the dispatch node to subscribe before publishing: with a
        large fleet the dispatch takes longer to initialise (it declares one
        subscription per vehicle), and any mission published before it is ready
        is lost. The wait is bounded by SUBSCRIBER_TIMEOUT_S so it never hangs.
        Targets are spread on a circle so the nearest-UAV choice sees varied
        distances.

        @return  None.
        """
        
        waited = 0.0
        while (self.pub.get_subscription_count() < 1
               and waited < SUBSCRIBER_TIMEOUT_S):
            rclpy.spin_once(self, timeout_sec=0.1)
            time.sleep(0.1)
            waited += 0.2
        if self.pub.get_subscription_count() < 1:
            self.get_logger().warn(
                "no subscriber on /mission_tokens after "
                f"{SUBSCRIBER_TIMEOUT_S:.0f} s; publishing anyway")
        else:
            time.sleep(SETTLE_AFTER_CONNECT_S)

        for i in range(self.n):
            m = MissionToken()
            m.mission_id = f"bench-mission-{i}"
            m.type = MissionToken.TYPE_INTERCEPT
            m.target_id = f"intruder-{i}"
            ang = 2.0 * math.pi * i / max(self.n, 1)
            m.target_position.x = TARGET_RING_RADIUS_M * math.cos(ang)
            m.target_position.y = TARGET_RING_RADIUS_M * math.sin(ang)
            m.target_position.z = TARGET_ALTITUDE_M
            m.justification = [f"bench:{i}"]
            m.authorised_by = "bench_supervisor"
            m.t = self.get_clock().now().to_msg()
            m.ttl_s = MISSION_TTL_S
            self.pub.publish(m)
            time.sleep(INTER_MISSION_GAP_S)

        time.sleep(DISPATCH_DRAIN_S)
        self.get_logger().info(f"injected {self.n} missions")


def main():
    """Entry point: parse the mission count, run the injector, and shut down.

    @return  None.
    """
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N_MISSIONS
    rclpy.init()
    node = MissionInjector(n)
    node.run()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()