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
"""Resilience test: sensor staleness detection.

Verifies that the analog safety board correctly detects when sensors go
offline (stop publishing) and transitions to UNSAFE, blocking actuator
commands via veto. The staleness timeout and topics are configured via YAML.
"""

import os
import sys

import rclpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.base_test import BaseResilienceTest, TestSuite
from framework.reporter import save_report
from std_msgs.msg import Float32
from sensor_msgs.msg import BatteryState, Imu, Range

# Nominal (safe) sensor values.
NOMINAL_PROXIMITY_M = 5.0
NOMINAL_ALTITUDE_M = 10.0
NOMINAL_BATTERY = 0.8
NOMINAL_CMD_RAW = 0.6

# Warm-up establishes connections before asserting; the phases then stream a
# sustained condition so the board sees it rather than a single reading.
WARMUP_SAMPLES = 20
WARMUP_INTERVAL_S = 0.1
SAMPLES_PER_PHASE = 10
SAMPLE_INTERVAL_S = 0.2


class SensorStalenessTest(BaseResilienceTest):
    """Test safety board reaction to sensor dropout.

    Scenario:
    1. Publish valid sensor data -> safety board should be SAFE.
    2. Stop publishing sensors.
    3. Wait > staleness_timeout_s.
    4. Assert safety_status goes to 0.0 (UNSAFE).
    5. Assert actuator_cmd_safe goes to 0.0 (VETO).
    6. Resume publishing -> assert recovery to SAFE.
    """

    def __init__(self, config_path: str):
        """Initialise the sensor-staleness test node.

        Validates the system's behaviour when sensor inputs become stale (no
        longer updated within the expected window). The safety layer must
        detect the missing updates, transition to a fail-secure state, and veto
        actuator commands when sensor freshness cannot be guaranteed.

        @param config_path  Absolute path to the YAML configuration file
                            defining topics, timeouts, and safety thresholds.
        """
        super().__init__("test_sensor_staleness", config_path)
        self.staleness_s = self.config["safety"]["staleness_timeout_s"]
        self.imu_pub = self.create_publisher(Imu, self.topics["imu"], 10)
        self.proximity_pub = self.create_publisher(Range, self.topics["proximity"], 10)
        self.altitude_pub = self.create_publisher(Float32, self.topics["altitude"], 10)
        self.battery_pub = self.create_publisher(BatteryState, self.topics["battery"], 10)
        self.cmd_raw_pub = self.create_publisher(Float32, self.topics["actuator_cmd_raw"], 10)
        self.subscribe_capture(self.topics["safety_status"], Float32, reliable=False)
        self.subscribe_capture(self.topics["actuator_cmd_safe"], Float32, reliable=False)

    def _publish_safe_sensors(self):
        """Publish a coherent set of nominal (safe) sensor values.

        Simulates a stable operating condition (level attitude, no obstacle,
        nominal altitude, sufficient battery, normal actuator command) used as
        the baseline for validating safety-layer behaviour.
        """
        imu = Imu()
        imu.orientation.w = 1.0
        self.imu_pub.publish(imu)

        prox = Range()
        prox.range = NOMINAL_PROXIMITY_M
        prox.min_range = 0.1
        prox.max_range = 10.0
        self.proximity_pub.publish(prox)

        alt = Float32()
        alt.data = NOMINAL_ALTITUDE_M
        self.altitude_pub.publish(alt)

        bat = BatteryState()
        bat.percentage = NOMINAL_BATTERY
        self.battery_pub.publish(bat)

        cmd = Float32()
        cmd.data = NOMINAL_CMD_RAW
        self.cmd_raw_pub.publish(cmd)

    def _stream_safe(self, samples: int, interval_s: float):
        """Stream nominal sensors for a fixed number of samples.

        @param samples     Number of nominal snapshots to publish.
        @param interval_s  Delay between snapshots, in seconds.
        """
        for _ in range(samples):
            self._publish_safe_sensors()
            self.sleep(interval_s)

    def run(self) -> TestSuite:
        """Execute the sensor-staleness resilience scenario.

        Three phases: nominal operation (must stay SAFE and pass commands),
        sensor dropout beyond the staleness timeout (must go UNSAFE and veto),
        and recovery once sensors resume (must return to SAFE).

        @return TestSuite containing all assertion results for the scenario.
        """
        suite = TestSuite(f"sensor_staleness_{self.config['scenario']}")
        self.get_logger().info("=" * 50)
        self.get_logger().info("Test: Sensor Staleness Detection")
        self.get_logger().info("=" * 50)
        self.sleep(self.timeouts["startup_s"])

        # Warm-up: publish briefly to establish connections before asserting.
        self.get_logger().info("Warm-up: establishing connections...")
        self._stream_safe(WARMUP_SAMPLES, WARMUP_INTERVAL_S)

        # Phase 1: Publish safe sensors -> expect SAFE.
        self.get_logger().info("Phase 1: Publishing safe sensor data...")
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])
        self._stream_safe(SAMPLES_PER_PHASE, SAMPLE_INTERVAL_S)
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

        # Phase 2: Stop publishing -> expect UNSAFE after the staleness window.
        self.get_logger().info(
            f"Phase 2: Stopping sensors, waiting {self.staleness_s + 1.5}s..."
        )
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])
        self.sleep(self.staleness_s + 1.5)
        cmd = Float32()
        cmd.data = NOMINAL_CMD_RAW
        self.cmd_raw_pub.publish(cmd)
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

        # Phase 3: Resume sensors -> expect recovery.
        self.get_logger().info("Phase 3: Resuming sensor data...")
        self.clear_captured(self.topics["safety_status"])
        self._stream_safe(SAMPLES_PER_PHASE, SAMPLE_INTERVAL_S)
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
    """Entry point for the sensor-staleness resilience test.

    Initialises ROS 2, loads the configuration, runs the staleness scenario,
    exports the results, and shuts down. Exit code is 0 if all assertions
    passed, 1 otherwise.
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
