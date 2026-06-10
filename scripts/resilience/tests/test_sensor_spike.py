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

@file test_sensor_spike.py

Resilience test: Sensor spike / transient fault.

Verifies that the analog safety board correctly reacts to a brief
sensor violation (proximity spike) and then recovers when the
anomaly clears.

Scalable: configure thresholds and topics via YAML.

@author Luca D'Aurizio
"""

import sys
import os
import rclpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.base_test import BaseResilienceTest, TestSuite
from framework.reporter import save_report

from std_msgs.msg import Float32
from sensor_msgs.msg import Range, BatteryState


class SensorSpikeTest(BaseResilienceTest):
    """
    Tests safety board reaction to transient sensor fault.

    Scenario:
    1. Publish nominal sensor data -> SAFE, cmd passes
    2. Inject proximity spike (obstacle at 0.5m < threshold 1.5m)
    3. Assert safety board transitions to UNSAFE -> VETO
    4. Clear spike (return to nominal proximity)
    5. Assert recovery to SAFE -> cmd passes again
    """

    def __init__(self, config_path: str):
        """
        Initialise the Sensor Spike resilience test node.

        This test validates the safety layer response to sudden sensor
        anomalies (spikes) across multiple input channels, including:
        - proximity sensing
        - altitude readings
        - battery state
        - raw actuator commands

        The node publishes simulated sensor data and monitors the safety
        system outputs to verify correct degradation and veto behaviour
        under abnormal conditions.

        @param config_path  Absolute path to the YAML configuration file
                            defining topics, thresholds, and test parameters.
        """
        super().__init__("test_sensor_spike", config_path)
        self.min_proximity = self.config["safety"]["min_proximity_m"]

        self.proximity_pub = self.create_publisher(Range, self.topics["proximity"], 10)
        self.altitude_pub = self.create_publisher(Float32, self.topics["altitude"], 10)
        self.battery_pub = self.create_publisher(BatteryState, self.topics["battery"], 10)
        self.cmd_raw_pub = self.create_publisher(Float32, self.topics["actuator_cmd_raw"], 10)

        self.subscribe_capture(self.topics["safety_status"], Float32, reliable=False)
        self.subscribe_capture(self.topics["actuator_cmd_safe"], Float32, reliable=False)

    def _publish_sensors(self, proximity: float, altitude: float = 10.0,
                         battery: float = 0.8):
        """
        Publish a coherent snapshot of simulated sensor inputs.

        This helper method injects a synchronized set of sensor readings into
        the system under test, representing a single timestep of robot state.

        It is used to simulate environmental conditions and trigger safety
        layer reactions under controlled and repeatable scenarios.

        @param proximity  Simulated proximity sensor reading in metres.
                        Lower values represent closer obstacles.
        @param altitude   Simulated altitude reading in metres.
                        Defaults to 10.0.
        @param battery    Simulated battery level in normalized range [0.0, 1.0].
                        Defaults to 0.8.
        """
        prox = Range()
        prox.range = proximity
        prox.min_range = 0.1
        prox.max_range = 10.0
        self.proximity_pub.publish(prox)

        alt = Float32()
        alt.data = altitude
        self.altitude_pub.publish(alt)

        bat = BatteryState()
        bat.percentage = battery
        self.battery_pub.publish(bat)

        cmd = Float32()
        cmd.data = 0.6
        self.cmd_raw_pub.publish(cmd)

    def run(self) -> TestSuite:
        """
        Execute the Sensor Spike resilience scenario.

        This test validates the system's ability to handle transient sensor
        faults and recover correctly once the anomaly is removed.

        The scenario is structured in three phases:
        1. Nominal operation -> system must remain in SAFE state
        2. Proximity spike -> system must transition to UNSAFE and veto actuation
        3. Recovery -> system must return to SAFE and re-enable actuation

        @return TestSuite containing all assertion results for the scenario
        """
        suite = TestSuite(f"sensor_spike_{self.config['scenario']}")

        self.get_logger().info("=" * 50)
        self.get_logger().info("Test: Sensor Spike / Transient Fault")
        self.get_logger().info("=" * 50)

        self.sleep(self.timeouts["startup_s"])

        # --- Phase 1: Nominal -> SAFE ---
        self.get_logger().info("Phase 1: Nominal sensor data...")
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])

        for _ in range(10):
            self._publish_sensors(proximity=5.0)  # well above threshold
            self.sleep(0.2)

        result_safe = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 1.0,
            description="SAFE during nominal operation",
        )
        suite.add(result_safe)

        # --- Phase 2: Proximity spike -> UNSAFE + VETO ---
        spike_value = self.min_proximity * 0.5  # well below threshold
        self.get_logger().warn(
            f"Phase 2: Injecting proximity spike ({spike_value}m < {self.min_proximity}m)..."
        )
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])

        for _ in range(10):
            self._publish_sensors(proximity=spike_value)
            self.sleep(0.2)

        result_unsafe = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 0.0,
            description=f"UNSAFE during proximity spike ({spike_value}m)",
        )
        suite.add(result_unsafe)

        result_veto = self.assert_message_received(
            topic=self.topics["actuator_cmd_safe"],
            timeout_s=3.0,
            condition=lambda m: m.data == 0.0,
            description="Actuator VETOED during proximity spike",
        )
        suite.add(result_veto)

        # --- Phase 3: Spike clears -> recovery ---
        self.get_logger().info("Phase 3: Clearing spike, returning to nominal...")
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])

        for _ in range(10):
            self._publish_sensors(proximity=5.0)
            self.sleep(0.2)

        result_recovery = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 1.0,
            description="Recovery to SAFE after spike clears",
        )
        suite.add(result_recovery)

        result_pass = self.assert_message_received(
            topic=self.topics["actuator_cmd_safe"],
            timeout_s=3.0,
            condition=lambda m: m.data > 0.5,
            description="Actuator command passes after recovery",
        )
        suite.add(result_pass)

        suite.print_report()
        return suite


def main():
    """
    Entry point for the Sensor Spike resilience test.

    This script initialises ROS2, loads the test configuration,
    executes a multi-sensor spike scenario, exports the results,
    and performs safe shutdown of all ROS2 resources.

    Exit code semantics:
    - 0 -> all assertions passed (system correctly handled sensor spikes)
    - 1 -> one or more assertions failed
    """
    rclpy.init()
    config = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "mock.yaml"
    )
    if len(sys.argv) > 1:
        config = sys.argv[1]

    test = SensorSpikeTest(config_path=config)
    suite = test.run()
    save_report(suite, output_dir=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"
    ))
    test.safe_destroy()
    rclpy.shutdown()
    sys.exit(0 if suite.all_passed() else 1)


if __name__ == "__main__":
    main()