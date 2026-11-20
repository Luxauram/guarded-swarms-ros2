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
"""Resilience test: sensor spike / transient fault.

Verifies that the analog safety board correctly reacts to a brief sensor
violation (proximity spike) and then recovers when the anomaly clears.
Thresholds and topics are configured via YAML.
"""

import os
import sys

import rclpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from framework.base_test import BaseResilienceTest, TestSuite
from framework.reporter import save_report
from std_msgs.msg import Float32
from sensor_msgs.msg import BatteryState, Imu, Range

# Nominal sensor values used to drive the board between violation phases.
NOMINAL_PROXIMITY_M = 5.0
NOMINAL_ALTITUDE_M = 10.0
NOMINAL_BATTERY = 0.8
NOMINAL_CMD_RAW = 0.6

# Each phase streams this many samples at this interval, so the board sees a
# sustained condition rather than a single reading.
SAMPLES_PER_PHASE = 10
SAMPLE_INTERVAL_S = 0.2


class SensorSpikeTest(BaseResilienceTest):
    """Test safety board reaction to a transient sensor fault.

    Scenario:
    1. Publish nominal sensor data -> SAFE, cmd passes.
    2. Inject proximity spike (obstacle below threshold).
    3. Assert safety board transitions to UNSAFE -> VETO.
    4. Clear spike (return to nominal proximity).
    5. Assert recovery to SAFE -> cmd passes again.
    """

    def __init__(self, config_path: str):
        """Initialise the sensor-spike test node.

        Validates the response of the safety layer to a transient proximity
        violation. The node publishes simulated sensor data and monitors the
        safety outputs to verify the veto and the recovery.

        @param config_path  Absolute path to the YAML configuration file
                            defining topics, thresholds, and test parameters.
        """
        super().__init__("test_sensor_spike", config_path)
        self.min_proximity = self.config["safety"]["min_proximity_m"]
        self.imu_pub = self.create_publisher(Imu, self.topics["imu"], 10)
        self.proximity_pub = self.create_publisher(Range, self.topics["proximity"], 10)
        self.altitude_pub = self.create_publisher(Float32, self.topics["altitude"], 10)
        self.battery_pub = self.create_publisher(BatteryState, self.topics["battery"], 10)
        self.cmd_raw_pub = self.create_publisher(Float32, self.topics["actuator_cmd_raw"], 10)
        self.subscribe_capture(self.topics["safety_status"], Float32, reliable=False)
        self.subscribe_capture(self.topics["actuator_cmd_safe"], Float32, reliable=False)

    def _publish_sensors(self, proximity: float,
                         altitude: float = NOMINAL_ALTITUDE_M,
                         battery: float = NOMINAL_BATTERY):
        """Publish a coherent snapshot of simulated sensor inputs.

        Injects a synchronised set of readings representing a single timestep
        of robot state, used to drive safety-layer reactions under controlled,
        repeatable conditions.

        @param proximity  Proximity reading in metres. Lower is closer.
        @param altitude   Altitude reading in metres. Defaults to nominal.
        @param battery    Battery level in [0.0, 1.0]. Defaults to nominal.
        """
        imu = Imu()
        imu.orientation.w = 1.0
        self.imu_pub.publish(imu)

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
        cmd.data = NOMINAL_CMD_RAW
        self.cmd_raw_pub.publish(cmd)

    def _stream_phase(self, proximity: float):
        """Stream a sustained sensor condition for one phase.

        @param proximity  Proximity value to hold across the phase, in metres.
        """
        for _ in range(SAMPLES_PER_PHASE):
            self._publish_sensors(proximity=proximity)
            self.sleep(SAMPLE_INTERVAL_S)

    def run(self) -> TestSuite:
        """Execute the sensor-spike resilience scenario.

        Three phases: nominal operation (must stay SAFE), a proximity spike
        (must go UNSAFE and veto actuation), and recovery (must return to SAFE
        and re-enable actuation).

        @return TestSuite containing all assertion results for the scenario.
        """
        suite = TestSuite(f"sensor_spike_{self.config['scenario']}")
        self.get_logger().info("=" * 50)
        self.get_logger().info("Test: Sensor Spike / Transient Fault")
        self.get_logger().info("=" * 50)
        self.sleep(self.timeouts["startup_s"])

        # Phase 1: Nominal -> SAFE.
        self.get_logger().info("Phase 1: Nominal sensor data...")
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])
        self._stream_phase(NOMINAL_PROXIMITY_M)
        result_safe = self.assert_message_received(
            topic=self.topics["safety_status"],
            timeout_s=3.0,
            condition=lambda m: m.data == 1.0,
            description="SAFE during nominal operation",
        )
        suite.add(result_safe)

        # Phase 2: Proximity spike -> UNSAFE + VETO. The spike value sits well
        # below the configured threshold so the board must react.
        spike_value = self.min_proximity * 0.5
        self.get_logger().warn(
            f"Phase 2: Injecting proximity spike ({spike_value}m < {self.min_proximity}m)..."
        )
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])
        self._stream_phase(spike_value)
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

        # Phase 3: Spike clears -> recovery.
        self.get_logger().info("Phase 3: Clearing spike, returning to nominal...")
        self.clear_captured(self.topics["safety_status"])
        self.clear_captured(self.topics["actuator_cmd_safe"])
        self._stream_phase(NOMINAL_PROXIMITY_M)
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
    """Entry point for the sensor-spike resilience test.

    Initialises ROS 2, loads the configuration, runs the multi-phase spike
    scenario, exports the results, and shuts down. Exit code is 0 if all
    assertions passed, 1 otherwise.
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
