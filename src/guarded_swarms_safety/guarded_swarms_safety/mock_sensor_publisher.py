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
"""

"""
@file mock_sensor_publisher.py

Mock sensor publisher for testing the SafetyBoard node without Gazebo.

Publishes realistic simulated sensor data on the same topics that
Gazebo plugins would use. Includes scripted scenarios to trigger
safety violations and verify the safety board's OR-logic veto behavior.

Scenarios (cycle through every 10 seconds):
  0 - NOMINAL      : All sensors within safe range
  1 - PROXIMITY    : Obstacle at 0.8m (below 1.5m threshold)
  2 - ATTITUDE     : Pitch at 45° (above 30° threshold)
  3 - BATTERY LOW  : Battery at 10% (below 15% threshold)
  4 - ALTITUDE HIGH: Altitude at 60m (above 50m threshold)
  5 - NOMINAL      : Recovery to safe state

Typical usage:
    ros2 run guarded_swarms_safety mock_sensor_publisher

    Then in another terminal:
    ros2 run guarded_swarms_safety safety_board_node

@author Luca D'Aurizio
"""

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Imu, Range, BatteryState
from std_msgs.msg import Float32

import math
import time


SCENARIOS = [
    {
        "name": "NOMINAL",
        "proximity_m": 5.0,
        "pitch_deg": 5.0,
        "roll_deg": 3.0,
        "battery_pct": 80.0,
        "altitude_m": 10.0,
    },
    {
        "name": "PROXIMITY VIOLATION",
        "proximity_m": 0.8,
        "pitch_deg": 5.0,
        "roll_deg": 3.0,
        "battery_pct": 80.0,
        "altitude_m": 10.0,
    },
    {
        "name": "ATTITUDE VIOLATION",
        "proximity_m": 5.0,
        "pitch_deg": 45.0,
        "roll_deg": 3.0,
        "battery_pct": 80.0,
        "altitude_m": 10.0,
    },
    {
        "name": "BATTERY LOW",
        "proximity_m": 5.0,
        "pitch_deg": 5.0,
        "roll_deg": 3.0,
        "battery_pct": 10.0,
        "altitude_m": 10.0,
    },
    {
        "name": "ALTITUDE TOO HIGH",
        "proximity_m": 5.0,
        "pitch_deg": 5.0,
        "roll_deg": 3.0,
        "battery_pct": 80.0,
        "altitude_m": 60.0,
    },
    {
        "name": "NOMINAL (RECOVERY)",
        "proximity_m": 5.0,
        "pitch_deg": 5.0,
        "roll_deg": 3.0,
        "battery_pct": 80.0,
        "altitude_m": 10.0,
    },
]

SCENARIO_DURATION_S = 10.0


class MockSensorPublisher(Node):
    """
    ROS 2 node that publishes simulated sensor data for SafetyBoard testing.

    Cycles through a predefined sequence of scenarios, each lasting
    SCENARIO_DURATION_S seconds, and publishes the corresponding sensor
    values on the topics normally served by Gazebo plugins.
    """

    TOPIC_IMU = "/drone/imu"
    TOPIC_PROXIMITY = "/drone/proximity"
    TOPIC_BATTERY = "/drone/battery"
    TOPIC_ALTITUDE = "/drone/altitude"
    TOPIC_CMD_RAW = "/actuator_cmd_raw"

    PUBLISH_RATE_HZ = 10.0

    def __init__(self):
        """
        Initializes the MockSensorPublisher node.

        Creates publishers for all sensor topics and the raw command topic,
        records the start time for scenario timing, and starts the periodic
        publish timer.
        """
        super().__init__("mock_sensor_publisher")

        self.imu_pub = self.create_publisher(Imu, self.TOPIC_IMU, 10)
        self.proximity_pub = self.create_publisher(Range, self.TOPIC_PROXIMITY, 10)
        self.battery_pub = self.create_publisher(BatteryState, self.TOPIC_BATTERY, 10)
        self.altitude_pub = self.create_publisher(Float32, self.TOPIC_ALTITUDE, 10)
        self.cmd_raw_pub = self.create_publisher(Float32, self.TOPIC_CMD_RAW, 10)

        self.start_time = time.time()
        self.current_scenario_idx = 0

        self.timer = self.create_timer(1.0 / self.PUBLISH_RATE_HZ, self._publish_all)

        self.get_logger().info("MockSensorPublisher started")
        self.get_logger().info(
            f"Cycling through {len(SCENARIOS)} scenarios, {SCENARIO_DURATION_S}s each"
        )

    def _get_current_scenario(self) -> dict:
        """
        Determines and returns the active scenario based on elapsed time.

        Logs a warning whenever a scenario transition occurs.

        @return Dictionary describing the current scenario's sensor values.
        """
        elapsed = time.time() - self.start_time
        idx = int(elapsed / SCENARIO_DURATION_S) % len(SCENARIOS)

        if idx != self.current_scenario_idx:
            self.current_scenario_idx = idx
            self.get_logger().warn(
                f"[MockSensors] >>> Scenario {idx}: {SCENARIOS[idx]['name']} <<<"
            )

        return SCENARIOS[idx]

    def _publish_all(self):
        """
        Publishes one update cycle for all sensor topics and the raw command.

        Retrieves the current scenario and delegates to the individual
        publish helpers for each topic.
        """
        scenario = self._get_current_scenario()

        self._publish_imu(scenario["pitch_deg"], scenario["roll_deg"])
        self._publish_proximity(scenario["proximity_m"])
        self._publish_battery(scenario["battery_pct"])
        self._publish_altitude(scenario["altitude_m"])
        self._publish_cmd_raw(thrust=0.5)

    def _publish_imu(self, pitch_deg: float, roll_deg: float):
        """
        Converts Euler angles to a quaternion and publishes an Imu message.

        Uses the ZYX convention with yaw fixed at zero.

        @param pitch_deg  Desired pitch angle in degrees.
        @param roll_deg   Desired roll angle in degrees.
        """
        msg = Imu()

        pitch = math.radians(pitch_deg)
        roll = math.radians(roll_deg)
        yaw = 0.0

        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)

        msg.orientation.w = cr * cp * cy + sr * sp * sy
        msg.orientation.x = sr * cp * cy - cr * sp * sy
        msg.orientation.y = cr * sp * cy + sr * cp * sy
        msg.orientation.z = cr * cp * sy - sr * sp * cy

        self.imu_pub.publish(msg)

    def _publish_proximity(self, distance_m: float):
        """
        Publishes a Range message with the given obstacle distance.

        @param distance_m  Distance to the nearest obstacle in meters.
        """
        msg = Range()
        msg.range = distance_m
        msg.min_range = 0.1
        msg.max_range = 10.0
        self.proximity_pub.publish(msg)

    def _publish_battery(self, percent: float):
        """
        Publishes a BatteryState message with the given charge level.

        Converts the percentage value to the normalized [0.0, 1.0] range
        expected by sensor_msgs/BatteryState.

        @param percent  Battery charge level in the range [0, 100].
        """
        msg = BatteryState()
        msg.percentage = percent / 100.0
        self.battery_pub.publish(msg)

    def _publish_altitude(self, altitude_m: float):
        """
        Publishes a Float32 message with the given altitude above ground.

        @param altitude_m  Altitude in meters.
        """
        msg = Float32()
        msg.data = altitude_m
        self.altitude_pub.publish(msg)

    def _publish_cmd_raw(self, thrust: float):
        """
        Publishes a constant raw thrust command to simulate coordinator output.

        @param thrust  Normalized thrust value in the range [0.0, 1.0].
        """
        msg = Float32()
        msg.data = thrust
        self.cmd_raw_pub.publish(msg)


def main(args=None):
    """
    Main entry point for the mock sensor publisher node.

    Initializes the ROS 2 runtime, instantiates MockSensorPublisher, and
    spins until a KeyboardInterrupt is received.

    @param args  Optional argument list forwarded to rclpy.init (default: None).
    """
    rclpy.init(args=args)
    node = MockSensorPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
