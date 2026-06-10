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

@file test_forged_tokens.py

Resilience test: Forged token rejection.

Verifies that the coordinator correctly rejects tokens with invalid
cryptographic signatures. A tampered token (modified signature) must
never receive an AuthToken with approved=True.

Scalable: configure agents and topics via YAML.

@author Luca D'Aurizio
"""

import sys
import os
import rclpy
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.base_test import BaseResilienceTest, TestSuite, TestResult
from framework.reporter import save_report

from guarded_swarms_msgs.msg import GeometryToken as GeometryTokenMsg
from guarded_swarms_msgs.msg import AuthToken as AuthTokenMsg
from guarded_swarms_coordinator.token_system import create_geometry_token


class ForgedTokenTest(BaseResilienceTest):
    """
    Tests that forged (tampered signature) tokens are rejected.

    Scenario:
    1. Create a valid geometry token for agent_A
    2. Tamper with its signature (simulate an attacker)
    3. Publish the forged token to /geometry_tokens
    4. Assert the coordinator publishes a REJECTED AuthToken
    5. Assert no APPROVED AuthToken is ever published for this token
    """

    def __init__(self, config_path: str):
        """
        Initialise the Forged Tokens resilience test node.

        This test validates the system's ability to reject or correctly handle
        forged or manipulated geometry tokens, ensuring that authentication
        logic cannot be bypassed by invalid or malicious inputs.

        The node is configured to:
        - publish geometry tokens as a single test agent
        - capture authentication decisions from the safety layer

        @param config_path  Absolute path to the YAML configuration file
                            defining topics, agents, and test parameters.
        """
        super().__init__("test_forged_tokens", config_path)
        self.agent_id = self.config["agents"][0]["id"]
 
        self.geo_pub = self.create_publisher(
            GeometryTokenMsg, self.topics["geometry_tokens"], 10
        )
 
        self.subscribe_capture(self.topics["auth_tokens"], AuthTokenMsg)

    def run(self) -> TestSuite:
        """
        Execute the Forged Tokens resilience scenario.

        This test validates that the coordinator correctly:
        - accepts valid geometry tokens issued by a legitimate agent
        - rejects forged or tampered tokens with invalid signatures
        - never produces a false approval for a forged request

        The scenario is structured as follows:
        1. A valid token is published and must be approved
        2. A forged token is published with a tampered signature and must be rejected
        3. The system must never publish an approval for the forged token

        @return TestSuite containing all assertion results for the scenario
        """
        suite = TestSuite(f"forged_tokens_{self.config['scenario']}")
 
        self.get_logger().info("=" * 50)
        self.get_logger().info("Test: Forged Token Rejection")
        self.get_logger().info("=" * 50)
 
        # Wait for coordinator to be ready
        self.sleep(self.timeouts["startup_s"])
        self.clear_captured(self.topics["auth_tokens"])

        # --- Test 1: Valid token is accepted ---
        zone = self.config["agents"][0].get("zone_center", [0.0, 0.0, 5.0])
        valid_token = create_geometry_token(
            agent_id=self.agent_id,
            x=zone[0], y=zone[1], z=zone[2],
            width=5.0, height=5.0, depth=3.0,
            duration=10.0, priority=9,
        )
        self.geo_pub.publish(valid_token.to_msg())
        self.get_logger().info(f"Published VALID token {valid_token.token_id[:8]}...")
 
        token_id = valid_token.token_id
 
 
        result_valid = self.assert_message_received(
            topic=self.topics["auth_tokens"],
            timeout_s=self.timeouts["response_ms"] / 1000 * 5,
            condition=lambda m: (
                m.geometry_token_id == token_id and m.approved
            ),
            description="Valid token accepted by coordinator",
        )
        suite.add(result_valid)

        # --- Test 2: Forged token is rejected ---
        self.clear_captured(self.topics["auth_tokens"])
 
        forged_token = create_geometry_token(
            agent_id=self.agent_id,
            x=zone[0]+10, y=zone[1]+10, z=zone[2],
            width=5.0, height=5.0, depth=3.0,
            duration=10.0, priority=9,
        )
        # Tamper the signature
        forged_msg = forged_token.to_msg()
        forged_msg.base_token.signature = "deadbeefdeadbeefdeadbeefdeadbeef" * 2
        forged_id = forged_token.token_id
 
        self.geo_pub.publish(forged_msg)
        self.get_logger().warn(f"Published FORGED token {forged_id[:8]}...")
 
        result_rejected = self.assert_message_received(
            topic=self.topics["auth_tokens"],
            timeout_s=self.timeouts["response_ms"] / 1000 * 5,
            condition=lambda m: (
                m.geometry_token_id == forged_id and not m.approved
            ),
            description="Forged token rejected by coordinator",
        )
        suite.add(result_rejected)

        # --- Test 3: No approval ever published for forged token ---
        result_no_approval = self.assert_no_message(
            topic=self.topics["auth_tokens"],
            wait_s=1.0,
            condition=lambda m: (
                m.geometry_token_id == forged_id and m.approved
            ),
            description="Forged token never approved",
        )
        suite.add(result_no_approval)
 
        suite.print_report()
        return suite


def main():
    """
    Entry point for the Forged Tokens resilience test.

    This script initialises ROS2, loads the test configuration,
    executes the forged token scenario, stores the results, and
    shuts down all resources safely.

    Exit code semantics:
    - 0 -> all assertions passed (system correctly handled forged tokens)
    - 1 -> one or more assertions failed
    """
    rclpy.init()
    config = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "mock.yaml"
    )
    if len(sys.argv) > 1:
        config = sys.argv[1]
 
    test = ForgedTokenTest(config_path=config)
    suite = test.run()
    save_report(suite, output_dir=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
    ))
    test.safe_destroy()
    rclpy.shutdown()
    sys.exit(0 if suite.all_passed() else 1)
 
 
if __name__ == "__main__":
    main()
