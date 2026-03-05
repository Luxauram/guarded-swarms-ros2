/**
 * Copyright 2026 Luca D'Aurizio
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @file safety_board_node.hpp
 *
 * @brief Analog safety enforcement layer — class declaration.
 *
 * Implements the virtual safety board described in the Guarded Swarms paper.
 * Monitors real-time sensor data and enforces hard physical safety constraints
 * using OR-logic: any single violation vetoes the current actuator command.
 *
 * @author Luca D'Aurizio
 */

#pragma once

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/range.hpp>
#include <sensor_msgs/msg/battery_state.hpp>
#include <std_msgs/msg/float32.hpp>

#include <chrono>
#include <string>

// ============================================================================
// SensorSnapshot
// ============================================================================

/**
 * @brief Aggregated snapshot of the latest reading from each sensor.
 *
 * Updated by each subscriber callback and consumed by the safety evaluator.
 * All fields are initialised to safe default values so that the node does not
 * veto commands before the first sensor message is received.
 */
struct SensorSnapshot
{
  float proximity_m = 999.0f;     ///< Closest obstacle distance (m).
  float pitch_deg = 0.0f;         ///< Current pitch angle (degrees).
  float roll_deg = 0.0f;          ///< Current roll angle (degrees).
  float battery_percent = 100.0f; ///< Battery state of charge in the range [0, 100].
  float altitude_m = 0.0f;        ///< Altitude above ground (m).

  double last_imu_ts = 0.0;       ///< Timestamp of the last IMU message (seconds).
  double last_proximity_ts = 0.0; ///< Timestamp of the last proximity message (seconds).
  double last_battery_ts = 0.0;   ///< Timestamp of the last battery message (seconds).
  double last_altitude_ts = 0.0;  ///< Timestamp of the last altitude message (seconds).
};

// ============================================================================
// SafetyVerdict
// ============================================================================

/**
 * @brief Result of a single safety evaluation pass.
 *
 * Carries both the overall decision and per-check results, together with a
 * human-readable description of the first constraint violation detected.
 */
struct SafetyVerdict
{
  bool is_safe = true;          ///< Overall safety decision (false if any check fails).
  bool proximity_ok = true;     ///< Result of the proximity constraint check.
  bool attitude_ok = true;      ///< Result of the attitude constraint check.
  bool battery_ok = true;       ///< Result of the battery constraint check.
  bool altitude_ok = true;      ///< Result of the altitude constraint check.
  std::string violation_reason; ///< Human-readable description of the first violation.
};

// ============================================================================
// SafetyBoardNode
// ============================================================================

/**
 * @brief ROS 2 node implementing the analog safety enforcement layer.
 *
 * Subscribes to sensor topics, intercepts actuator commands, and applies
 * OR-logic safety constraints before forwarding commands to the actuators.
 * Any single violated constraint causes the current command to be replaced
 * with a zero-thrust output.
 */
class SafetyBoardNode : public rclcpp::Node
{
public:
  /**
   * @brief Constructs the node, declares ROS parameters, and initialises all
   *        subscriptions, publishers, and timers.
   */
  explicit SafetyBoardNode();

private:
  static constexpr const char *TOPIC_IMU = "/drone/imu";
  static constexpr const char *TOPIC_PROXIMITY = "/drone/proximity";
  static constexpr const char *TOPIC_BATTERY = "/drone/battery";
  static constexpr const char *TOPIC_ALTITUDE = "/drone/altitude";
  static constexpr const char *TOPIC_CMD_RAW = "/actuator_cmd_raw";
  static constexpr const char *TOPIC_CMD_SAFE = "/actuator_cmd_safe";
  static constexpr const char *TOPIC_SAFETY_STATUS = "/safety_status";

  static constexpr int QUEUE_SIZE = 10;

  static constexpr float DEFAULT_MIN_PROXIMITY_M = 1.5f;
  static constexpr float DEFAULT_MAX_PITCH_DEG = 30.0f;
  static constexpr float DEFAULT_MAX_ROLL_DEG = 30.0f;
  static constexpr float DEFAULT_MIN_BATTERY_PCT = 15.0f;
  static constexpr float DEFAULT_MIN_ALTITUDE_M = 0.3f;
  static constexpr float DEFAULT_MAX_ALTITUDE_M = 50.0f;
  static constexpr float DEFAULT_SENSOR_STALENESS_S = 2.0f;

  static constexpr double SAFETY_STATUS_RATE_HZ = 10.0;

  /**
   * @brief Handles incoming IMU messages and updates pitch and roll in the
   *        sensor snapshot.
   *
   * @param msg Shared pointer to the received IMU message.
   */
  void imu_callback(const sensor_msgs::msg::Imu::SharedPtr msg);

  /**
   * @brief Handles incoming proximity messages and updates the obstacle
   *        distance in the sensor snapshot.
   *
   * @param msg Shared pointer to the received Range message.
   */
  void proximity_callback(const sensor_msgs::msg::Range::SharedPtr msg);

  /**
   * @brief Handles incoming battery messages and updates the state of charge
   *        in the sensor snapshot.
   *
   * @param msg Shared pointer to the received BatteryState message.
   */
  void battery_callback(const sensor_msgs::msg::BatteryState::SharedPtr msg);

  /**
   * @brief Handles incoming altitude messages and updates the altitude in the
   *        sensor snapshot.
   *
   * @param msg Shared pointer to the received Float32 message.
   */
  void altitude_callback(const std_msgs::msg::Float32::SharedPtr msg);

  /**
   * @brief Intercepts raw actuator commands, evaluates safety, and either
   *        forwards the command unchanged or publishes a zero-thrust veto.
   *
   * @param msg Shared pointer to the raw command message.
   */
  void cmd_raw_callback(const std_msgs::msg::Float32::SharedPtr msg);

  /**
   * @brief Evaluates all safety constraints against the current sensor snapshot.
   *
   * Applies OR-logic: the first failed constraint short-circuits the evaluation
   * and populates the violation reason in the returned verdict.
   *
   * @return A @c SafetyVerdict describing the overall result and per-check outcomes.
   */
  SafetyVerdict evaluate_safety() const;

  /**
   * @brief Publishes the current safety status on the status topic and emits a
   *        periodic diagnostic log entry.
   */
  void publish_safety_status();

  /**
   * @brief Logs the active safety thresholds at node startup.
   */
  void log_startup() const;

  /**
   * @brief Returns the current ROS time in seconds.
   *
   * @return Current time as a double-precision value in seconds.
   */
  double now_seconds() const;

  float min_proximity_m_;
  float max_pitch_deg_;
  float max_roll_deg_;
  float min_battery_pct_;
  float min_altitude_m_;
  float max_altitude_m_;
  float sensor_staleness_s_;

  SensorSnapshot sensors_;

  uint64_t commands_received_ = 0;
  uint64_t commands_cleared_ = 0;
  uint64_t commands_vetoed_ = 0;
  uint64_t veto_proximity_ = 0;
  uint64_t veto_attitude_ = 0;
  uint64_t veto_battery_ = 0;
  uint64_t veto_altitude_ = 0;
  uint64_t veto_stale_ = 0;

  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Range>::SharedPtr proximity_sub_;
  rclcpp::Subscription<sensor_msgs::msg::BatteryState>::SharedPtr battery_sub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr altitude_sub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr cmd_raw_sub_;

  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr cmd_safe_pub_;
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr safety_status_pub_;

  rclcpp::TimerBase::SharedPtr status_timer_;
};
