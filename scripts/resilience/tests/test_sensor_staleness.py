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

@file test_sensor_staleness.py

Resilience test: Sensor staleness detection.

Verifies that the analog safety board correctly detects when sensors
go offline (stop publishing) and transitions to UNSAFE state, blocking
actuator commands via veto.

Scalable: configure staleness timeout and topics via YAML.

@author Luca D'Aurizio
"""

import sys
import os
import rclpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.base_test import BaseResilienceTest, TestSuite
from framework.reporter import save_report

from std_msgs.msg import Float32
from sensor_msgs.msg import Range, Imu, BatteryState


class SensorStalenessTest(BaseResilienceTest):
    """
    Tests safety board reaction to sensor dropout.

    Scenario:
    1. Publish valid sensor data -> safety board should be SAFE
    2. Stop publishing sensors
    3. Wait > staleness_timeout_s
    4. Assert safety_status goes to 0.0 (UNSAFE)
    5. Assert actuator_cmd_safe goes to 0.0 (VETO)
    6. Resume publishing -> assert recovery to SAFE
    """

    def __init__(self, config_path: str):
        """
        Initialise the Sensor Staleness resilience test node.

        This test validates the system's behaviour when sensor inputs become
        stale (i.e. no longer updated within an expected time window).

        The safety layer is expected to:
        - detect stale or missing sensor updates
        - transition the system into a SAFE or FAIL-SECURE state
        - veto actuator commands when sensor freshness cannot be guaranteed

        The node simulates continuous sensor streams and observes safety
        reactions to degraded temporal validity of incoming data.

        @param config_path  Absolute path to the YAML configuration file
                            defining topics, timeouts, and safety thresholds.
        """
        super().__init__("test_sensor_staleness", config_path)
        self.staleness_s = self.config["safety"]["staleness_timeout_s"]

        self.proximity_pub = self.create_publisher(Range, self.topics["proximity"], 10)
        self.altitude_pub = self.create_publisher(Float32, self.topics["altitude"], 10)
        self.battery_pub = self.create_publisher(BatteryState, self.topics["battery"], 10)
        self.cmd_raw_pub = self.create_publisher(Float32, self.topics["actuator_cmd_raw"], 10)

        self.subscribe_capture(self.topics["safety_status"], Float32, reliable=False)
        self.subscribe_capture(self.topics["actuator_cmd_safe"], Float32, reliable=False)

    def _publish_safe_sensors(self):
        """
        Publish a coherent set of nominal (safe) sensor values.

        This helper method simulates a stable operating condition where all
        sensor inputs remain within expected bounds. It is used as the
        baseline state for validating correct safety-layer behaviour.

        The published values represent:
        - no obstacle proximity
        - nominal altitude
        - sufficient battery level
        - normal actuator command input
        """
        prox = Range()
        prox.range = 5.0
        prox.min_range = 0.1
        prox.max_range = 10.0
        self.proximity_pub.publish(prox)

        alt = Float32()
        alt.data = 10.0
        self.altitude_pub.publish(alt)

        bat = BatteryState()
        bat.percentage = 0.8
        self.battery_pub.publish(bat)

        cmd = Float32()
        cmd.data = 0.6
        self.cmd_raw_pub.publish(cmd)

    def run(self) -> TestSuite:
        """
        Execute the Sensor Staleness Detection resilience scenario.

        This test validates the system's ability to detect and react to
        stale sensor inputs (i.e. missing updates beyond a configured
        timeout window).

        The scenario is structured in three phases:
        1. Warm-up + nominal operation → system must remain SAFE
        2. Sensor dropout → system must transition to UNSAFE and veto commands
        3. Sensor recovery → system must return to SAFE state

        The safety layer is expected to:
        - detect loss of sensor freshness after staleness timeout
        - disable actuator commands during unsafe conditions
        - recover automatically once sensor updates resume

        @return TestSuite containing all assertion results for the scenario
        """
        suite = TestSuite(f"sensor_staleness_{self.config['scenario']}")

        self.get_logger().info("=" * 50)
        self.get_logger().info("Test: Sensor Staleness Detection")
        self.get_logger().info("=" * 50)

        self.sleep(self.timeouts["startup_s"])

        # Warm-up: publish for 2s to establish connections before asserting
        self.get_logger().info("Warm-up: establishing connections...")
        for _ in range(20):
            self._publish_safe_sensors()
            self.sleep(0.1)

        # --- Phase 1: Publish safe sensors -> expect SAFE ---
        self.get_logger().info("Phase 1: Publishing safe sensor data...")
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])

        for _ in range(10):
            self._publish_safe_sensors()
            self.sleep(0.2)

        result_safe = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 1.0,
            description="Safety board SAFE with valid sensors",
        )
        suite.add(result_safe)

        result_pass = self.assert_message_received(
            topic=self.topics["actuator_cmd_safe"],
            timeout_s=5.0,
            condition=lambda m: m.data > 0.5,
            description="Actuator command passes when SAFE",
        )
        suite.add(result_pass)

        # --- Phase 2: Stop publishing -> expect UNSAFE after staleness ---
        self.get_logger().info(
            f"Phase 2: Stopping sensors, waiting {self.staleness_s + 1}s..."
        )
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])

        cmd = Float32()
        cmd.data = 0.6
        self.cmd_raw_pub.publish(cmd)

        self.sleep(self.staleness_s + 1.5)

        result_unsafe = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 0.0,
            description=f"Safety board UNSAFE after {self.staleness_s}s sensor dropout",
        )
        suite.add(result_unsafe)

        result_veto = self.assert_message_received(
            topic=self.topics["actuator_cmd_safe"],
            timeout_s=3.0,
            condition=lambda m: m.data == 0.0,
            description="Actuator command VETOED when sensors stale",
        )
        suite.add(result_veto)

        # --- Phase 3: Resume sensors -> expect recovery ---
        self.get_logger().info("Phase 3: Resuming sensor data...")
        self.clear_captured(self.topics["safety_status"])

        for _ in range(10):
            self._publish_safe_sensors()
            self.sleep(0.2)

        result_recovery = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 1.0,
            description="Safety board recovers to SAFE after sensors resume",
        )
        suite.add(result_recovery)

        suite.print_report()
        return suite


def main():
    """
    Entry point for the Sensor Staleness resilience test.

    This script initialises ROS2, loads the test configuration,
    executes a scenario where sensor updates may become stale,
    exports the results, and safely shuts down all resources.

    Exit code semantics:
    - 0 → all assertions passed (system correctly handled staleness)
    - 1 → one or more assertions failed
    """
    rclpy.init()
    config = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "mock.yaml"
    )
    if len(sys.argv) > 1:
        config = sys.argv[1]

    test = SensorStalenessTest(config_path=config)
    suite = test.run()
    save_report(suite, output_dir=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
    ))
    test.safe_destroy()
    rclpy.shutdown()
    sys.exit(0 if suite.all_passed() else 1)


if __name__ == "__main__":
    main()