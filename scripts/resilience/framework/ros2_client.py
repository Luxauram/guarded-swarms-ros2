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
"""ROS 2 utility client for Guarded Swarms resilience tests.

Provides lightweight wrappers around rclpy for common test operations:
publishing messages to any topic, waiting for a specific message value,
checking topic activity, and injecting mock sensor data. Used by all test
classes in tests/*.py via base_test.py.
"""

import time
import threading
from typing import Optional, Callable

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float32
from sensor_msgs.msg import Range, BatteryState


# ==============================================================================
# QoS profiles
# ==============================================================================
# Telemetry and monitoring topics where occasional packet loss is acceptable
# and low latency is preferred over guaranteed delivery.
BEST_EFFORT_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.BEST_EFFORT,
)

# Control, coordination, and security-critical topics where every message must
# be delivered to subscribers whenever possible.
RELIABLE_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
)


# ==============================================================================
# ROS 2 Client
# ==============================================================================
class ROS2Client:
    """Lightweight ROS 2 utility client for test operations.

    Wraps common pub/sub patterns so test code stays focused on assertions
    rather than ROS 2 boilerplate.

    Usage:
        client = ROS2Client(node)
        client.publish_float("/actuator_cmd_raw", 0.6)
        value = client.wait_float("/actuator_cmd_safe", timeout_s=3.0)
    """

    def __init__(self, node: Node):
        """Initialise topic helper state for the given ROS 2 node.

        Creates internal registries used to manage publishers, subscriptions,
        and thread-safe access to the most recently received message on each
        topic.

        @param node  ROS 2 node that owns all publishers and subscriptions
                     created through this helper.
        """
        self._node = node
        self._publishers: dict = {}
        self._latest: dict = {}
        self._locks: dict = {}
        self._subscriptions: dict = {}

    # --------------------------------------------------------------------------
    # Publishing helpers
    # --------------------------------------------------------------------------
    def publish_float(self, topic: str, value: float):
        """Publish a Float32 message to a topic.

        @param topic  ROS 2 topic name.
        @param value  Value to publish.
        """
        if topic not in self._publishers:
            self._publishers[topic] = self._node.create_publisher(
                Float32, topic, RELIABLE_QOS
            )
        msg = Float32()
        msg.data = value
        self._publishers[topic].publish(msg)

    def publish_proximity(self, topic: str, distance_m: float,
                          min_range: float = 0.1, max_range: float = 10.0):
        """Publish a sensor_msgs/Range message representing a proximity reading.

        Creates and caches the publisher on first use, then reuses it. Messages
        use BEST_EFFORT QoS to match typical proximity/obstacle sensors. The
        measurement is published as an infrared range reading.

        @param topic       ROS 2 topic on which the Range message is published.
        @param distance_m  Measured distance to the detected object in metres.
        @param min_range   Minimum valid sensor range in metres. Defaults to 0.1.
        @param max_range   Maximum valid sensor range in metres. Defaults to 10.0.
        """
        key = f"range_{topic}"
        if key not in self._publishers:
            self._publishers[key] = self._node.create_publisher(
                Range, topic, BEST_EFFORT_QOS
            )
        msg = Range()
        msg.range = distance_m
        msg.min_range = min_range
        msg.max_range = max_range
        msg.radiation_type = Range.INFRARED
        self._publishers[key].publish(msg)

    def publish_battery(self, topic: str, percentage: float):
        """Publish a sensor_msgs/BatteryState message.

        Creates and caches the publisher on first use, then reuses it. Messages
        use BEST_EFFORT QoS, appropriate for telemetry where the latest state
        matters more than guaranteed delivery. The level is a normalised value
        in [0.0, 1.0], from empty to fully charged.

        @param topic       ROS 2 topic on which the BatteryState is published.
        @param percentage  Battery charge level as a value between 0.0 and 1.0.
        """
        key = f"bat_{topic}"
        if key not in self._publishers:
            self._publishers[key] = self._node.create_publisher(
                BatteryState, topic, BEST_EFFORT_QOS
            )
        msg = BatteryState()
        msg.percentage = percentage
        self._publishers[key].publish(msg)

    def publish_nominal_sensors(self, topics: dict,
                                proximity: float = 5.0,
                                altitude: float = 10.0,
                                battery: float = 0.8,
                                cmd_raw: float = 0.6):
        """Publish a full set of nominal sensor values in one call.

        @param topics     Topic configuration dict with keys proximity,
                          altitude, battery, actuator_cmd_raw.
        @param proximity  Distance in metres (default 5.0, above the 1.5 m veto).
        @param altitude   Altitude in metres (default 10.0, within bounds).
        @param battery    Charge level 0.0-1.0 (default 0.8 = 80%).
        @param cmd_raw    Raw actuator command (default 0.6).
        """
        self.publish_proximity(topics["proximity"], proximity)
        self.publish_float(topics["altitude"], altitude)
        self.publish_battery(topics["battery"], battery)
        self.publish_float(topics["actuator_cmd_raw"], cmd_raw)

    # --------------------------------------------------------------------------
    # Subscription helpers
    # --------------------------------------------------------------------------
    def subscribe_float(self, topic: str):
        """Subscribe to a Float32 topic and cache the most recent value.

        The subscription is created only once per topic. Incoming values are
        stored in a thread-safe cache and retrieved with get_latest_float()
        without waiting for further messages. BEST_EFFORT QoS is used, as the
        latest value matters more than guaranteed delivery.

        @param topic  ROS 2 topic name publishing std_msgs/Float32 messages.
        """
        if topic in self._subscriptions:
            return
        self._latest[topic] = None
        self._locks[topic] = threading.Lock()

        def cb(msg):
            with self._locks[topic]:
                self._latest[topic] = msg.data

        self._subscriptions[topic] = self._node.create_subscription(
            Float32, topic, cb, BEST_EFFORT_QOS
        )

    def get_latest_float(self, topic: str) -> Optional[float]:
        """Return the most recent Float32 value for a subscribed topic.

        Access to the internal cache is protected by a per-topic lock for safe
        concurrent access from ROS 2 callback threads.

        @param topic  ROS 2 topic name previously passed to subscribe_float().
        @return       Latest received value, or None if no message has arrived
                      yet or the topic is not being tracked.
        """
        with self._locks.get(topic, threading.Lock()):
            return self._latest.get(topic)

    # --------------------------------------------------------------------------
    # Wait helpers
    # --------------------------------------------------------------------------
    def wait_float(self, topic: str, condition: Callable[[float], bool] = None,
                   timeout_s: float = 5.0) -> Optional[float]:
        """Wait until a Float32 topic publishes a value matching a condition.

        @param topic      ROS 2 topic name.
        @param condition  Callable(value) -> bool, True when the value is
                          acceptable. If None, the first value is returned.
        @param timeout_s  Maximum wait time in seconds. Defaults to 5.0.
        @return           The matching value, or None on timeout.
        """
        self.subscribe_float(topic)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rclpy.spin_once(self._node, timeout_sec=0.05)
            val = self.get_latest_float(topic)
            if val is not None:
                if condition is None or condition(val):
                    return val
        return None

    def wait_for_safe(self, topics: dict, timeout_s: float = 5.0) -> bool:
        """Wait for the Safety Board to approve actuator execution.

        Monitors actuator_cmd_safe and returns when a value above 0.5 is seen,
        indicating that all safety checks passed and commands may proceed.

        @param topics     Topic configuration dict from the scenario config.
        @param timeout_s  Maximum time to wait in seconds. Defaults to 5.0.
        @return           True if a safe state is observed within the timeout.
        """
        val = self.wait_float(
            topics["actuator_cmd_safe"],
            condition=lambda v: v > 0.5,
            timeout_s=timeout_s,
        )
        return val is not None

    def wait_for_veto(self, topics: dict, timeout_s: float = 5.0) -> bool:
        """Wait for the Safety Board to veto actuator execution.

        Monitors actuator_cmd_safe and returns when a value of 0.0 is seen,
        indicating that commands were blocked by the safety layer.

        @param topics     Topic configuration dict from the scenario config.
        @param timeout_s  Maximum time to wait in seconds. Defaults to 5.0.
        @return           True if a veto is observed within the timeout.
        """
        val = self.wait_float(
            topics["actuator_cmd_safe"],
            condition=lambda v: v == 0.0,
            timeout_s=timeout_s,
        )
        return val is not None

    def wait_for_unsafe(self, topics: dict, timeout_s: float = 5.0) -> bool:
        """Wait for the system safety status to become UNSAFE.

        Monitors safety_status and returns when a value of 0.0 is seen,
        indicating that one or more safety constraints have been violated.

        @param topics     Topic configuration dict from the scenario config.
        @param timeout_s  Maximum time to wait in seconds. Defaults to 5.0.
        @return           True if the UNSAFE state is observed within timeout.
        """
        val = self.wait_float(
            topics["safety_status"],
            condition=lambda v: v == 0.0,
            timeout_s=timeout_s,
        )
        return val is not None

    # --------------------------------------------------------------------------
    # Topic activity check
    # --------------------------------------------------------------------------
    def is_topic_active(self, topic: str, msg_type, window_s: float = 2.0) -> bool:
        """Determine whether a topic is actively publishing messages.

        Creates a temporary subscription and monitors the topic for a limited
        window. Succeeds as soon as one message is received, regardless of its
        contents. Useful for checking a node is alive before more detailed
        behavioural assertions.

        @param topic     ROS 2 topic name to monitor.
        @param msg_type  Expected ROS 2 message type on the topic.
        @param window_s  Observation window in seconds. Defaults to 2.0.
        @return          True if at least one message is received within the
                         window, False otherwise.
        """
        received = threading.Event()
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)

        def cb(msg):
            received.set()

        sub = self._node.create_subscription(msg_type, topic, cb, qos)
        deadline = time.time() + window_s
        while time.time() < deadline and not received.is_set():
            rclpy.spin_once(self._node, timeout_sec=0.05)
        self._node.destroy_subscription(sub)
        return received.is_set()

    # --------------------------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------------------------
    def destroy(self):
        """Destroy all publishers and subscriptions managed by this helper.

        Releases every ROS 2 communication entity created through the helper
        and clears the internal registries. Call during test teardown so that
        resources are released before node shutdown.
        """
        for pub in self._publishers.values():
            self._node.destroy_publisher(pub)
        for sub in self._subscriptions.values():
            self._node.destroy_subscription(sub)
        self._publishers.clear()
        self._subscriptions.clear()