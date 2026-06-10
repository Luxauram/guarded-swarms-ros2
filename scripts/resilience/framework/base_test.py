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

@file base_test.py

Base class for all Guarded Swarms resilience tests.

Provides ROS2 node lifecycle, config loading, topic pub/sub helpers,
and pass/fail assertion utilities. All test classes inherit from this.

@author Luca D'Aurizio
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
import yaml
import time
import threading
from typing import Optional, List, Any
from dataclasses import dataclass, field


# ==============================================================================
# Result types
# ==============================================================================

@dataclass
class TestResult:
    """
    Holds the result of a single test assertion.
 
    @param name        Human-readable test name shown in the report.
    @param passed      True if the assertion succeeded, False otherwise.
    @param message     Short description of the outcome (e.g. timing info).
    @param duration_s  Wall-clock time taken by the assertion in seconds.
    @param details     Optional dict for extra diagnostic data (unused by default).
    """
 
    name: str
    passed: bool
    message: str
    duration_s: float = 0.0
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        """
        Returns a one-line summary suitable for console output.
 
        @return Formatted string: "[PASS|FAIL] <name> (<duration>s) - <message>"
        """
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name} ({self.duration_s:.2f}s) - {self.message}"


class TestSuite:
    """
    Collects TestResult objects from a test run and generates a summary report.
 
    Typical usage:
        suite = TestSuite("my_scenario")
        suite.add(some_test_result)
        suite.print_report()
        return suite.all_passed()
    """
 
    def __init__(self, scenario: str):
        """
        Initialise a new test suite for the given scenario.
 
        @param scenario  Label used in the printed report header and JSON output.
        """
        self.scenario = scenario
        self.results: List[TestResult] = []
        self.start_time = time.time()

    def add(self, result: TestResult):
        """
        Append a TestResult to the suite.
 
        @param result  The TestResult to record.
        """
        self.results.append(result)

    def passed(self) -> int:
        """
        Count of passing assertions.
 
        @return Number of TestResult objects where passed == True.
        """
        return sum(1 for r in self.results if r.passed)

    def failed(self) -> int:
        """
        Count of failing assertions.
 
        @return Number of TestResult objects where passed == False.
        """
        return sum(1 for r in self.results if not r.passed)


    def print_report(self):
        """
        Print a formatted summary of all results to stdout.
 
        Includes per-result PASS/FAIL lines, totals, and elapsed duration.
        """
        total = len(self.results)
        elapsed = time.time() - self.start_time

        print()
        print("=" * 60)
        print(f"  Resilience Test Report — {self.scenario}")
        print("=" * 60)
        for r in self.results:
            print(f"  {r}")
        print("-" * 60)
        print(f"  Total: {total}  |  Passed: {self.passed()}  |  Failed: {self.failed()}")
        print(f"  Duration: {elapsed:.2f}s")
        print("=" * 60)
        print()

    def all_passed(self) -> bool:
        """
        Check whether every assertion in the suite passed.
 
        @return True if failed() == 0, False otherwise.
        """
        return self.failed() == 0



# ==============================================================================
# Base test node
# ==============================================================================

class BaseResilienceTest(Node):
    """
    Base class for all Guarded Swarms resilience tests.
 
    Extends rclpy.Node to provide:
    - YAML config loading (agents, topics, timeouts, safety thresholds)
    - Thread-safe message capture from any ROS2 topic
    - Timeout-based message waiting with optional condition matching
    - High-level pass/fail assertion utilities
    - Safe node teardown compatible with rclpy Humble cleanup quirks
 
    All concrete test classes (test_forged_tokens, test_dropped_tokens, etc.)
    inherit from this class.
    """
 
    def __init__(self, node_name: str, config_path: str):
        """
        Initialise the test node and load scenario configuration.
 
        @param node_name   ROS2 node name (must be unique within the ROS graph).
        @param config_path Absolute path to the YAML scenario config file.
        """
        super().__init__(node_name)
        self.config = self._load_config(config_path)
        self.topics = self.config["topics"]
        self.timeouts = self.config["timeouts"]
        self._captured: dict = {}
        self._locks: dict = {}
        self._subscriptions = []

    # --------------------------------------------------------------------------
    # Config
    # --------------------------------------------------------------------------

    def _load_config(self, path: str) -> dict:
        """
        Load and parse a YAML scenario configuration file.
 
        @param path  Absolute path to the YAML file.
        @return      Parsed configuration as a Python dict.
        """
        with open(path, "r") as f:
            return yaml.safe_load(f)

    # --------------------------------------------------------------------------
    # Topic helpers
    # --------------------------------------------------------------------------

    def subscribe_capture(self, topic: str, msg_type, max_messages: int = 1000,
                          reliable: bool = True):
        """
        Subscribe to a ROS2 topic and buffer all incoming messages.
 
        Messages are stored as (timestamp, msg) tuples and can be retrieved
        with get_captured() or consumed by wait_for_message().
 
        @param topic        ROS2 topic name to subscribe to.
        @param msg_type     ROS2 message class (e.g. Float32, AuthToken).
        @param max_messages Maximum number of messages to buffer before
                            dropping older ones. Defaults to 1000.
        @param reliable     If True, use RELIABLE QoS; if False, use
                            BEST_EFFORT. Use False for sensor topics
                            (safety_status, actuator_cmd_safe) which
                            the safety board publishes as BEST_EFFORT.
        """
        self._captured[topic] = []
        self._locks[topic] = threading.Lock()

        def callback(msg):
            with self._locks[topic]:
                if len(self._captured[topic]) < max_messages:
                    self._captured[topic].append((time.time(), msg))

        qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE if reliable else ReliabilityPolicy.BEST_EFFORT,
        )
        sub = self.create_subscription(msg_type, topic, callback, qos)
        self._subscriptions.append(sub)

    def get_captured(self, topic: str) -> list:
        """
        Return a snapshot of all buffered messages for a topic.
 
        Thread-safe: acquires the topic lock before copying the list.
 
        @param topic  ROS2 topic name previously passed to subscribe_capture().
        @return       List of (timestamp_float, msg) tuples, oldest first.
                      Returns an empty list if the topic has not been
                      subscribed or no messages have arrived yet.
        """
        with self._locks.get(topic, threading.Lock()):
            return list(self._captured.get(topic, []))

    def wait_for_message(self, topic: str, timeout_s: float = 5.0,
                         condition=None) -> Optional[Any]:
        """
        Block until a message matching an optional condition is received.
 
        Spins the ROS2 executor in 50 ms slices while polling the capture
        buffer. Returns immediately if a matching message is already buffered.
 
        @param topic      ROS2 topic name previously passed to subscribe_capture().
        @param timeout_s  Maximum time to wait in seconds. Defaults to 5.0.
        @param condition  Optional callable(msg) -> bool. If provided, only
                          messages for which condition returns True are
                          considered a match. If None, the first message
                          received on the topic is returned.
        @return           The first matching message object, or None if the
                          timeout expires before a match is found.
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msgs = self.get_captured(topic)
            for ts, msg in msgs:
                if condition is None or condition(msg):
                    return msg
            rclpy.spin_once(self, timeout_sec=0.05)
        return None

    def clear_captured(self, topic: str):
        """
        Discard all buffered messages for a topic.
 
        Call this before a test phase to ensure only messages published
        after the clear are considered by subsequent assertions.
 
        @param topic  ROS2 topic name previously passed to subscribe_capture().
        """
        with self._locks.get(topic, threading.Lock()):
            self._captured[topic] = []

    # --------------------------------------------------------------------------
    # Assertions
    # --------------------------------------------------------------------------

    def assert_message_received(self, topic: str, timeout_s: float = 5.0,
                                condition=None, description: str = "") -> TestResult:
        """
        Assert that at least one message (optionally matching a condition)
        arrives on a topic within the given timeout.
 
        @param topic       ROS2 topic name to check.
        @param timeout_s   Maximum seconds to wait. Defaults to 5.0.
        @param condition   Optional callable(msg) -> bool. If provided, the
                           assertion passes only when a message satisfying
                           condition is received.
        @param description Human-readable label shown in the test report.
                           Defaults to "message_received(<topic>)".
        @return            TestResult with passed=True if a matching message
                           was received, passed=False on timeout.
        """
        start = time.time()
        msg = self.wait_for_message(topic, timeout_s=timeout_s, condition=condition)
        duration = time.time() - start

        if msg is not None:
            return TestResult(
                name=description or f"message_received({topic})",
                passed=True,
                message=f"Message received in {duration:.2f}s",
                duration_s=duration,
            )
        else:
            return TestResult(
                name=description or f"message_received({topic})",
                passed=False,
                message=f"No message received within {timeout_s}s",
                duration_s=duration,
            )

    def assert_no_message(self, topic: str, wait_s: float = 2.0,
                          condition=None, description: str = "") -> TestResult:
        """
        Assert that NO message matching an optional condition arrives on a
        topic during the observation window.
 
        Clears the capture buffer before starting the observation so that
        previously buffered messages do not influence the result.
 
        @param topic       ROS2 topic name to monitor.
        @param wait_s      Duration to observe in seconds. Defaults to 2.0.
        @param condition   Optional callable(msg) -> bool. If provided, only
                           messages satisfying condition count as violations.
                           If None, any message is a violation.
        @param description Human-readable label shown in the test report.
        @return            TestResult with passed=True if no matching message
                           arrived, passed=False if one did.
        """
        start = time.time()
        self.clear_captured(topic)
        deadline = time.time() + wait_s

        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

        msgs = self.get_captured(topic)
        matched = [m for _, m in msgs if condition is None or condition(m)]
        duration = time.time() - start

        if not matched:
            return TestResult(
                name=description or f"no_message({topic})",
                passed=True,
                message=f"No matching message in {wait_s}s as expected",
                duration_s=duration,
            )
        else:
            return TestResult(
                name=description or f"no_message({topic})",
                passed=False,
                message=f"Unexpected message received: {matched[0]}",
                duration_s=duration,
            )

    def assert_value_within(self, topic: str, field: str, expected,
                            tolerance: float = 0.01, timeout_s: float = 5.0,
                            description: str = "") -> TestResult:
        """
        Assert that a numeric field of a received message is within tolerance
        of the expected value.
 
        @param topic       ROS2 topic name to monitor.
        @param field       Name of the message attribute to compare
                           (e.g. "data" for std_msgs/Float32).
        @param expected    Expected numeric value.
        @param tolerance   Acceptable deviation from expected. Defaults to 0.01.
        @param timeout_s   Maximum seconds to wait. Defaults to 5.0.
        @param description Human-readable label shown in the test report.
        @return            TestResult with passed=True if a message with
                           |field - expected| <= tolerance was received within
                           timeout_s, passed=False otherwise.
        """
        start = time.time()
        msg = self.wait_for_message(
            topic,
            timeout_s=timeout_s,
            condition=lambda m: abs(getattr(m, field, None) - expected) <= tolerance
            if getattr(m, field, None) is not None else False,
        )
        duration = time.time() - start

        if msg is not None:
            actual = getattr(msg, field)
            return TestResult(
                name=description or f"value_within({topic}.{field}={expected})",
                passed=True,
                message=f"Got {actual} (expected {expected}±{tolerance}) in {duration:.2f}s",
                duration_s=duration,
            )
        else:
            return TestResult(
                name=description or f"value_within({topic}.{field}={expected})",
                passed=False,
                message=f"Value {expected}±{tolerance} not observed within {timeout_s}s",
                duration_s=duration,
            )

    # --------------------------------------------------------------------------
    # Timing helpers
    # --------------------------------------------------------------------------

    def sleep(self, seconds: float):
        """
        Sleep for the given duration while keeping the ROS2 executor alive.
 
        Uses rclpy.spin_once in 50 ms slices so that subscriptions continue
        to receive messages during the wait.
 
        @param seconds  Duration to sleep in seconds.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def spin_for(self, seconds: float):
        """
        Alias for sleep(). Provided for readability in test code where the
        intent is to keep the executor running rather than to pause.
 
        @param seconds  Duration to spin in seconds.
        """
        self.sleep(seconds)

    
    def safe_destroy(self):
        """
        Destroy the ROS2 node, suppressing cleanup errors.
 
        rclpy Humble occasionally raises ValueError during destroy_node()
        when internal subscription waitables are already removed. This
        wrapper catches all exceptions so that test scripts can call it
        unconditionally without masking actual test failures.
        """
        try:
            self.destroy_node()
        except Exception:
            pass