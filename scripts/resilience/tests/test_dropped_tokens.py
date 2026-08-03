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
"""Resilience test: dropped token / agent failure.

Verifies that when an agent stops publishing tokens, the coordinator correctly
expires previously approved tokens and allows other agents to reclaim the
space. Agents and topics are configured via YAML.
"""

import os
import sys

import rclpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.base_test import BaseResilienceTest, TestSuite, TestResult
from framework.reporter import save_report
from guarded_swarms_msgs.msg import GeometryToken as GeometryTokenMsg
from guarded_swarms_msgs.msg import AuthToken as AuthTokenMsg
from guarded_swarms_coordinator.token_system import create_geometry_token


class DroppedTokenTest(BaseResilienceTest):
    """Test coordinator behaviour when an agent stops publishing tokens.

    Scenario:
    1. Agent A publishes a valid token and gets approved.
    2. Agent A goes silent (simulates crash/disconnect).
    3. After the token expires (> duration), Agent B requests the same space.
    4. Assert Agent B gets approved (space reclaimed after timeout).
    """

    def __init__(self, config_path: str):
        """Initialise the dropped-tokens test node.

        Loads the scenario configuration and prepares the ROS 2 interfaces
        required to simulate and observe token-based communication failures:
        publishes geometry tokens as normal input, captures auth tokens to
        detect loss or corruption, and operates on the configured agents.

        @param config_path  Absolute path to the YAML configuration file
                            defining topics, agents, and test parameters.
        """
        super().__init__("test_dropped_tokens", config_path)
        self.agents = self.config["agents"]

        self.geo_pub = self.create_publisher(
            GeometryTokenMsg, self.topics["geometry_tokens"], 10
        )
        self.subscribe_capture(self.topics["auth_tokens"], AuthTokenMsg)

    def run(self) -> TestSuite:
        """Execute the dropped-tokens resilience scenario.

        Agent A is approved for a shared zone, then goes silent; after the
        token expires, Agent B requests the same zone and must be approved.

        @return TestSuite containing all assertion results for the scenario.
        """
        suite = TestSuite(f"dropped_tokens_{self.config['scenario']}")

        self.get_logger().info("=" * 50)
        self.get_logger().info("Test: Dropped Token / Agent Failure")
        self.get_logger().info("=" * 50)

        self.sleep(self.timeouts["startup_s"])
        self.clear_captured(self.topics["auth_tokens"])

        agent_a = self.agents[0]["id"]
        agent_b = self.agents[1]["id"] if len(self.agents) > 1 else "test_agent_B"

        shared_pos = [500.0, 500.0, 50.0]

        # Test 1: Agent A gets approved. Short duration so the token expires
        # quickly and the reclaim can be observed within the test.
        token_a = create_geometry_token(
            agent_id=agent_a,
            x=shared_pos[0], y=shared_pos[1], z=shared_pos[2],
            width=5.0, height=5.0, depth=3.0,
            duration=2.0,
            priority=5,
        )
        self.geo_pub.publish(token_a.to_msg())
        self.get_logger().info("Agent A published token, duration=2s")

        result_a_approved = self.assert_message_received(
            topic=self.topics["auth_tokens"],
            timeout_s=2.0,
            condition=lambda m: m.geometry_token_id == token_a.token_id and m.approved,
            description="Agent A token approved",
        )
        suite.add(result_a_approved)

        # Test 2: Agent A goes silent; wait longer than the 2 s token duration
        # so the coordinator expires it.
        self.get_logger().info("Agent A goes silent (simulating crash)...")
        self.sleep(3.0)
        self.clear_captured(self.topics["auth_tokens"])

        # Test 3: Agent B requests the same space and must be approved.
        token_b = create_geometry_token(
            agent_id=agent_b,
            x=shared_pos[0], y=shared_pos[1], z=shared_pos[2],
            width=5.0, height=5.0, depth=3.0,
            duration=10.0,
            priority=5,
        )
        self.geo_pub.publish(token_b.to_msg())
        self.get_logger().info("Agent B requests same space after A went silent")

        result_b_approved = self.assert_message_received(
            topic=self.topics["auth_tokens"],
            timeout_s=5.0,
            condition=lambda m: m.geometry_token_id == token_b.token_id and m.approved,
            description="Agent B approved after Agent A timeout",
        )
        suite.add(result_b_approved)

        suite.print_report()
        return suite


def main():
    """Entry point for the dropped-tokens resilience test.

    Initialises ROS 2, loads the scenario configuration, runs the test, exports
    the results, and shuts down. Exit code is 0 if all assertions passed, 1
    otherwise.
    """
    rclpy.init()
    config = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "mock.yaml"
    )
    if len(sys.argv) > 1:
        config = sys.argv[1]

    test = DroppedTokenTest(config_path=config)
    suite = test.run()
    save_report(suite, output_dir=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
    ))
    test.safe_destroy()
    rclpy.shutdown()
    sys.exit(0 if suite.all_passed() else 1)


if __name__ == "__main__":
    main()