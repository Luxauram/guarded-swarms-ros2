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
@file safety_board_node.py

Analog safety enforcement layer for the Guarded Swarms architecture.

This node implements the virtual safety board described in Section IV of the
Guarded Swarms paper. It operates independently of the digital token layer and
enforces hard physical safety constraints using OR-logic: any single violation
is sufficient to veto an actuator command.

Architecture position:
    [coordinator_node] --AuthToken--> [safety_board_node] --ActuatorCommand--> [Gazebo actuators]
                                              ^
                                    [sensor topics: IMU, proximity, battery, altitude]

The safety board workflow:
1. Subscribe to simulated sensor topics (Gazebo plugins or mock publishers)
2. Maintain a live snapshot of the latest sensor readings
3. Intercept ActuatorCommand messages before they reach the actuators
4. Evaluate all safety thresholds in parallel using OR-logic
5. Forward the command (safety_cleared=true) or publish a zero/hold command
6. Publish SafetyStatus at a fixed rate for dashboard monitoring

Sensor topics (Gazebo-compatible):
    /drone/imu              -> sensor_msgs/Imu         (attitude)
    /drone/proximity        -> sensor_msgs/Range        (obstacle distance)
    /drone/battery          -> sensor_msgs/BatteryState (battery percentage)
    /drone/altitude         -> std_msgs/Float32         (altitude in meters)

Command topics:
    Input:  /actuator_cmd_raw    -> ActuatorCommand  (from coordinator)
    Output: /actuator_cmd_safe   -> ActuatorCommand  (to Gazebo actuators)

Safety topics:
    /safety_status               -> SafetyStatus     (monitoring)

Typical usage:
    ros2 run guarded_swarms_safety safety_board_node

    With custom thresholds:
    ros2 run guarded_swarms_safety safety_board_node --ros-args \\
        -p min_proximity_m:=2.0 \\
        -p max_pitch_deg:=25.0 \\
        -p min_battery_percent:=20.0

@author Luca D'Aurizio
"""

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Imu, Range, BatteryState
from std_msgs.msg import Float32
from guarded_swarms_coordinator.msg import AuthToken as AuthTokenMsg

import math
import time

# ============================================================================
# Internal Data Structures
# ============================================================================


class SensorSnapshot:
    """
    Thread-safe snapshot of the latest sensor readings.

    Updated by each sensor subscriber callback and read by the safety
    evaluator. Fields default to safe values so the node does not veto
    commands before the first sensor message arrives.
    """

    def __init__(self):
        """
        Initializes all sensor fields to safe default values and sets
        all timestamp markers to zero.
        """
        self.proximity_m: float = 999.0
        self.pitch_deg: float = 0.0
        self.roll_deg: float = 0.0
        self.battery_percent: float = 100.0
        self.altitude_m: float = 0.0
        self.last_imu_ts: float = 0.0
        self.last_proximity_ts: float = 0.0
        self.last_battery_ts: float = 0.0
        self.last_altitude_ts: float = 0.0

    def __repr__(self):
        """
        Returns a human-readable summary of the current sensor state.

        @return Formatted string with proximity, attitude, battery, and altitude values.
        """
        return (
            f"SensorSnapshot("
            f"prox={self.proximity_m:.2f}m, "
            f"pitch={self.pitch_deg:.1f}°, "
            f"roll={self.roll_deg:.1f}°, "
            f"bat={self.battery_percent:.1f}%, "
            f"alt={self.altitude_m:.1f}m)"
        )


class SafetyVerdict:
    """
    Result of a single safety evaluation pass.

    Aggregates the per-check outcomes and the overall safety decision
    produced by SafetyBoardNode._evaluate_safety.
    """

    def __init__(self):
        """
        Initializes the verdict with all checks passing and no violation reason.
        """
        self.is_safe: bool = True
        self.proximity_ok: bool = True
        self.attitude_ok: bool = True
        self.battery_ok: bool = True
        self.altitude_ok: bool = True
        self.violation_reason: str = ""

    def __bool__(self):
        """
        Allows the verdict to be used directly in boolean expressions.

        @return True if the drone state is considered safe, False otherwise.
        """
        return self.is_safe


# ============================================================================
# SafetyBoard Node
# ============================================================================


class SafetyBoardNode(Node):
    """
    ROS 2 node implementing the analog safety enforcement layer.

    Monitors real-time sensor data and enforces physical safety constraints
    independently of the digital coordination layer. Uses OR-logic: a single
    threshold violation vetoes the current actuator command.
    """

    TOPIC_IMU = "/drone/imu"
    TOPIC_PROXIMITY = "/drone/proximity"
    TOPIC_BATTERY = "/drone/battery"
    TOPIC_ALTITUDE = "/drone/altitude"
    TOPIC_CMD_RAW = "/actuator_cmd_raw"
    TOPIC_CMD_SAFE = "/actuator_cmd_safe"
    TOPIC_SAFETY_STATUS = "/safety_status"
    TOPIC_AUTH_TOKENS = "/auth_tokens"

    QUEUE_SIZE = 10

    DEFAULT_MIN_PROXIMITY_M = 1.5
    DEFAULT_MAX_PITCH_DEG = 30.0
    DEFAULT_MAX_ROLL_DEG = 30.0
    DEFAULT_MIN_BATTERY_PCT = 15.0
    DEFAULT_MIN_ALTITUDE_M = 0.3
    DEFAULT_MAX_ALTITUDE_M = 50.0
    SAFETY_STATUS_RATE_HZ = 10.0
    SENSOR_STALENESS_S = 2.0

    def __init__(self):
        """
        Initializes the SafetyBoardNode.

        Declares and loads ROS 2 parameters, initializes sensor state and
        statistics counters, creates all subscriptions and publishers, and
        starts the periodic safety status broadcast timer.
        """
        super().__init__("safety_board_node")

        self.declare_parameter("min_proximity_m", self.DEFAULT_MIN_PROXIMITY_M)
        self.declare_parameter("max_pitch_deg", self.DEFAULT_MAX_PITCH_DEG)
        self.declare_parameter("max_roll_deg", self.DEFAULT_MAX_ROLL_DEG)
        self.declare_parameter("min_battery_percent", self.DEFAULT_MIN_BATTERY_PCT)
        self.declare_parameter("min_altitude_m", self.DEFAULT_MIN_ALTITUDE_M)
        self.declare_parameter("max_altitude_m", self.DEFAULT_MAX_ALTITUDE_M)
        self.declare_parameter("sensor_staleness_s", self.SENSOR_STALENESS_S)

        self.min_proximity_m = self.get_parameter("min_proximity_m").value
        self.max_pitch_deg = self.get_parameter("max_pitch_deg").value
        self.max_roll_deg = self.get_parameter("max_roll_deg").value
        self.min_battery_pct = self.get_parameter("min_battery_percent").value
        self.min_altitude_m = self.get_parameter("min_altitude_m").value
        self.max_altitude_m = self.get_parameter("max_altitude_m").value
        self.sensor_staleness_s = self.get_parameter("sensor_staleness_s").value

        self.sensors = SensorSnapshot()

        self.commands_received = 0
        self.commands_cleared = 0
        self.commands_vetoed = 0
        self.veto_counts = {
            "proximity": 0,
            "attitude": 0,
            "battery": 0,
            "altitude": 0,
            "stale_sensor": 0,
        }

        self.imu_sub = self.create_subscription(
            Imu, self.TOPIC_IMU, self._imu_callback, self.QUEUE_SIZE
        )
        self.proximity_sub = self.create_subscription(
            Range, self.TOPIC_PROXIMITY, self._proximity_callback, self.QUEUE_SIZE
        )
        self.battery_sub = self.create_subscription(
            BatteryState, self.TOPIC_BATTERY, self._battery_callback, self.QUEUE_SIZE
        )
        self.altitude_sub = self.create_subscription(
            Float32, self.TOPIC_ALTITUDE, self._altitude_callback, self.QUEUE_SIZE
        )
        self.auth_sub = self.create_subscription(
            AuthTokenMsg, self.TOPIC_AUTH_TOKENS, self._auth_token_callback, self.QUEUE_SIZE
        )
        self.cmd_raw_sub = self.create_subscription(
            Float32, self.TOPIC_CMD_RAW, self._cmd_raw_callback, self.QUEUE_SIZE
        )
        self.cmd_safe_pub = self.create_publisher(Float32, self.TOPIC_CMD_SAFE, self.QUEUE_SIZE)
        self.safety_status_pub = self.create_publisher(
            Float32, self.TOPIC_SAFETY_STATUS, self.QUEUE_SIZE
        )

        self.status_timer = self.create_timer(
            1.0 / self.SAFETY_STATUS_RATE_HZ, self._publish_safety_status
        )

        self._log_startup()

    def _log_startup(self):
        """
        Logs the active safety threshold configuration at node startup.
        """
        self.get_logger().info("=" * 60)
        self.get_logger().info("SafetyBoard node initialized")
        self.get_logger().info(f"  min_proximity : {self.min_proximity_m} m")
        self.get_logger().info(f"  max_pitch     : {self.max_pitch_deg} °")
        self.get_logger().info(f"  max_roll      : {self.max_roll_deg} °")
        self.get_logger().info(f"  min_battery   : {self.min_battery_pct} %")
        self.get_logger().info(
            f"  altitude range: [{self.min_altitude_m}, {self.max_altitude_m}] m"
        )
        self.get_logger().info(f"  staleness     : {self.sensor_staleness_s} s")
        self.get_logger().info("=" * 60)

    def _imu_callback(self, msg: Imu):
        """
        Updates pitch and roll estimates from an incoming IMU message.

        Converts the quaternion orientation from the Imu message to Euler
        angles. Compatible with standard sensor_msgs/Imu published by the
        ros_gz_bridge.

        @param msg  The incoming sensor_msgs/Imu message.
        """
        q = msg.orientation

        sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z)
        cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y)
        roll_rad = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (q.w * q.y - q.z * q.x)
        sinp = max(-1.0, min(1.0, sinp))
        pitch_rad = math.asin(sinp)

        self.sensors.pitch_deg = math.degrees(pitch_rad)
        self.sensors.roll_deg = math.degrees(roll_rad)
        self.sensors.last_imu_ts = time.time()

    def _proximity_callback(self, msg: Range):
        """
        Updates the closest obstacle distance from an incoming Range message.

        Compatible with Gazebo sonar and lidar plugins publishing
        sensor_msgs/Range.

        @param msg  The incoming sensor_msgs/Range message.
        """
        self.sensors.proximity_m = msg.range
        self.sensors.last_proximity_ts = time.time()

    def _battery_callback(self, msg: BatteryState):
        """
        Updates the battery level from an incoming BatteryState message.

        Converts the normalized percentage field (range [0.0, 1.0]) to the
        [0, 100] scale used internally.

        @param msg  The incoming sensor_msgs/BatteryState message.
        """
        self.sensors.battery_percent = msg.percentage * 100.0
        self.sensors.last_battery_ts = time.time()

    def _altitude_callback(self, msg: Float32):
        """
        Updates the altitude above ground from an incoming Float32 message.

        @param msg  The incoming std_msgs/Float32 message carrying altitude in meters.
        """
        self.sensors.altitude_m = msg.data
        self.sensors.last_altitude_ts = time.time()

    def _auth_token_callback(self, msg: AuthTokenMsg):
        """
        Monitors coordinator authorization decisions for logging purposes.

        The safety board does not depend on token approval and operates
        independently of the digital coordination layer. This subscription
        is used exclusively for logging and dashboard correlation.

        @param msg  The incoming AuthToken message from the coordinator.
        """
        status = "APPROVED" if msg.approved else "REJECTED"
        self.get_logger().debug(
            f"[SafetyBoard] Observed auth token: {status} for {msg.base_token.agent_id} "
            f"(reason: {msg.reason})"
        )

    def _cmd_raw_callback(self, msg: Float32):
        """
        Intercepts a raw actuator command and applies the safety gate.

        Evaluates the current sensor snapshot against all configured
        thresholds. If the verdict is safe, the command is forwarded
        unchanged. Otherwise a zero-thrust command is published and the
        veto is logged.

        @param msg  The incoming Float32 stand-in for the raw ActuatorCommand.
        """
        self.commands_received += 1
        verdict = self._evaluate_safety()

        if verdict.is_safe:
            self.cmd_safe_pub.publish(msg)
            self.commands_cleared += 1
            self.get_logger().debug(f"[SafetyBoard] ✓ Command cleared | {self.sensors}")
        else:
            zero_cmd = Float32()
            zero_cmd.data = 0.0
            self.cmd_safe_pub.publish(zero_cmd)
            self.commands_vetoed += 1
            self.get_logger().warn(
                f"[SafetyBoard] ✗ VETO | reason: {verdict.violation_reason} | {self.sensors}"
            )

    # ========================================================================
    # Safety Evaluation (OR Logic)
    # ========================================================================

    def _evaluate_safety(self) -> SafetyVerdict:
        """
        Evaluates all safety constraints and returns an aggregated verdict.

        Implements the OR-logic policy from the Guarded Swarms paper: any
        single constraint violation sets is_safe=False and returns
        immediately. Checks are ordered from most critical to least:
        sensor staleness, proximity, attitude, battery, altitude.

        @return SafetyVerdict instance with per-check results and the
                overall safety decision.
        """
        verdict = SafetyVerdict()
        now = time.time()

        # -- 1. Sensor staleness check --
        stale_sensors = []
        if (
            self.sensors.last_imu_ts > 0
            and (now - self.sensors.last_imu_ts) > self.sensor_staleness_s
        ):
            stale_sensors.append("IMU")
        if (
            self.sensors.last_proximity_ts > 0
            and (now - self.sensors.last_proximity_ts) > self.sensor_staleness_s
        ):
            stale_sensors.append("proximity")
        if (
            self.sensors.last_battery_ts > 0
            and (now - self.sensors.last_battery_ts) > self.sensor_staleness_s
        ):
            stale_sensors.append("battery")

        if stale_sensors:
            verdict.is_safe = False
            verdict.violation_reason = f"stale_sensor: {', '.join(stale_sensors)}"
            self.veto_counts["stale_sensor"] += 1
            return verdict

        # -- 2. Proximity check --
        if self.sensors.proximity_m < self.min_proximity_m:
            verdict.proximity_ok = False
            verdict.is_safe = False
            verdict.violation_reason = (
                f"proximity={self.sensors.proximity_m:.2f}m < min={self.min_proximity_m}m"
            )
            self.veto_counts["proximity"] += 1
            return verdict

        # -- 3. Attitude check (pitch AND roll) --
        pitch_violation = abs(self.sensors.pitch_deg) > self.max_pitch_deg
        roll_violation = abs(self.sensors.roll_deg) > self.max_roll_deg

        if pitch_violation or roll_violation:
            verdict.attitude_ok = False
            verdict.is_safe = False
            parts = []
            if pitch_violation:
                parts.append(f"pitch={self.sensors.pitch_deg:.1f}° > max={self.max_pitch_deg}°")
            if roll_violation:
                parts.append(f"roll={self.sensors.roll_deg:.1f}° > max={self.max_roll_deg}°")
            verdict.violation_reason = "attitude: " + ", ".join(parts)
            self.veto_counts["attitude"] += 1
            return verdict

        # -- 4. Battery check --
        if self.sensors.battery_percent < self.min_battery_pct:
            verdict.battery_ok = False
            verdict.is_safe = False
            verdict.violation_reason = (
                f"battery={self.sensors.battery_percent:.1f}% < min={self.min_battery_pct}%"
            )
            self.veto_counts["battery"] += 1
            return verdict

        # -- 5. Altitude check --
        alt_too_low = self.sensors.altitude_m < self.min_altitude_m
        alt_too_high = self.sensors.altitude_m > self.max_altitude_m

        if alt_too_low or alt_too_high:
            verdict.altitude_ok = False
            verdict.is_safe = False
            if alt_too_low:
                verdict.violation_reason = (
                    f"altitude={self.sensors.altitude_m:.1f}m < min={self.min_altitude_m}m"
                )
            else:
                verdict.violation_reason = (
                    f"altitude={self.sensors.altitude_m:.1f}m > max={self.max_altitude_m}m"
                )
            self.veto_counts["altitude"] += 1
            return verdict

        return verdict

    def _publish_safety_status(self):
        """
        Broadcasts the current safety state at the configured fixed rate.

        Publishes a Float32 with value 1.0 (safe) or 0.0 (unsafe) as a
        stand-in until SafetyStatus.msg is available. Logs a summary
        approximately every two seconds to avoid log spam.
        """
        verdict = self._evaluate_safety()

        status_msg = Float32()
        status_msg.data = 1.0 if verdict.is_safe else 0.0
        self.safety_status_pub.publish(status_msg)

        if int(time.time() * self.SAFETY_STATUS_RATE_HZ) % 20 == 0:
            self.get_logger().info(
                f"[SafetyBoard] {'✓ SAFE' if verdict.is_safe else '✗ UNSAFE'} | "
                f"{self.sensors} | "
                f"cleared={self.commands_cleared} "
                f"vetoed={self.commands_vetoed}"
            )
            if not verdict.is_safe:
                self.get_logger().warn(
                    f"[SafetyBoard] Active violation: {verdict.violation_reason}"
                )

    def get_stats(self) -> dict:
        """
        Returns runtime statistics for monitoring and testing.

        @return Dictionary containing total command counts, veto rate
                percentage, per-category veto counts, and the current
                sensor snapshot string representation.
        """
        total = self.commands_received if self.commands_received > 0 else 1
        return {
            "commands_received": self.commands_received,
            "commands_cleared": self.commands_cleared,
            "commands_vetoed": self.commands_vetoed,
            "veto_rate_pct": round(self.commands_vetoed / total * 100, 1),
            "veto_counts": dict(self.veto_counts),
            "current_sensors": str(self.sensors),
        }


# ============================================================================
# Main
# ============================================================================


def main(args=None):
    """
    Main entry point for the safety board node.

    Initializes the ROS 2 runtime, instantiates SafetyBoardNode, and
    spins until a KeyboardInterrupt is received. Logs final statistics
    before shutting down.

    Thresholds can be overridden at launch via ROS 2 parameters:

        ros2 run guarded_swarms_safety safety_board_node --ros-args \\
            -p min_proximity_m:=2.0 \\
            -p max_pitch_deg:=25.0 \\
            -p min_battery_percent:=20.0

    @param args  Optional argument list forwarded to rclpy.init (default: None).
    """
    rclpy.init(args=args)
    node = SafetyBoardNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("[SafetyBoard] Shutting down")
    finally:
        stats = node.get_stats()
        node.get_logger().info(
            f"[SafetyBoard] Final stats: "
            f"received={stats['commands_received']} "
            f"cleared={stats['commands_cleared']} "
            f"vetoed={stats['commands_vetoed']} "
            f"({stats['veto_rate_pct']}% veto rate)"
        )
        node.get_logger().info(f"[SafetyBoard] Veto breakdown: {stats['veto_counts']}")
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
