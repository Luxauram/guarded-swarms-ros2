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
 * @file safety_board_node.cpp
 * @brief Analog safety enforcement layer - implementation.
 *
 * See safety_board_node.hpp for the full architecture description.
 *
 * @author Luca D'Aurizio
 */

#include "guarded_swarms_safety/safety_board_node.hpp"

#include <cmath>
#include <string>

using namespace std::chrono_literals;

// ============================================================================
// Constructor
// ============================================================================

SafetyBoardNode::SafetyBoardNode() : Node("safety_board_node") {
  this->declare_parameter("min_proximity_m", DEFAULT_MIN_PROXIMITY_M);
  this->declare_parameter("max_pitch_deg", DEFAULT_MAX_PITCH_DEG);
  this->declare_parameter("max_roll_deg", DEFAULT_MAX_ROLL_DEG);
  this->declare_parameter("min_battery_percent", DEFAULT_MIN_BATTERY_PCT);
  this->declare_parameter("min_altitude_m", DEFAULT_MIN_ALTITUDE_M);
  this->declare_parameter("max_altitude_m", DEFAULT_MAX_ALTITUDE_M);
  this->declare_parameter("sensor_staleness_s", DEFAULT_SENSOR_STALENESS_S);

  min_proximity_m_ = this->get_parameter("min_proximity_m").as_double();
  max_pitch_deg_ = this->get_parameter("max_pitch_deg").as_double();
  max_roll_deg_ = this->get_parameter("max_roll_deg").as_double();
  min_battery_pct_ = this->get_parameter("min_battery_percent").as_double();
  min_altitude_m_ = this->get_parameter("min_altitude_m").as_double();
  max_altitude_m_ = this->get_parameter("max_altitude_m").as_double();
  sensor_staleness_s_ = this->get_parameter("sensor_staleness_s").as_double();

  imu_sub_ = this->create_subscription<sensor_msgs::msg::Imu>(
      TOPIC_IMU, QUEUE_SIZE,
      std::bind(&SafetyBoardNode::imu_callback, this, std::placeholders::_1));

  proximity_sub_ = this->create_subscription<sensor_msgs::msg::Range>(
      TOPIC_PROXIMITY, QUEUE_SIZE,
      std::bind(&SafetyBoardNode::proximity_callback, this,
                std::placeholders::_1));

  battery_sub_ = this->create_subscription<sensor_msgs::msg::BatteryState>(
      TOPIC_BATTERY, QUEUE_SIZE,
      std::bind(&SafetyBoardNode::battery_callback, this,
                std::placeholders::_1));

  altitude_sub_ = this->create_subscription<std_msgs::msg::Float32>(
      TOPIC_ALTITUDE, QUEUE_SIZE,
      std::bind(&SafetyBoardNode::altitude_callback, this,
                std::placeholders::_1));

  cmd_raw_sub_ = this->create_subscription<std_msgs::msg::Float32>(
      TOPIC_CMD_RAW, QUEUE_SIZE,
      std::bind(&SafetyBoardNode::cmd_raw_callback, this,
                std::placeholders::_1));

  cmd_safe_pub_ = this->create_publisher<std_msgs::msg::Float32>(TOPIC_CMD_SAFE,
                                                                 QUEUE_SIZE);

  safety_status_pub_ = this->create_publisher<std_msgs::msg::Float32>(
      TOPIC_SAFETY_STATUS, QUEUE_SIZE);

  auto period = std::chrono::duration<double>(1.0 / SAFETY_STATUS_RATE_HZ);
  status_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&SafetyBoardNode::publish_safety_status, this));

  log_startup();
}

// ============================================================================
// Sensor Callbacks
// ============================================================================

void SafetyBoardNode::imu_callback(const sensor_msgs::msg::Imu::SharedPtr msg) {
  const auto& q = msg->orientation;

  double sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z);
  double cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y);
  sensors_.roll_deg =
      static_cast<float>(std::atan2(sinr_cosp, cosr_cosp) * 180.0 / M_PI);

  double sinp = 2.0 * (q.w * q.y - q.z * q.x);
  sinp = std::max(-1.0, std::min(1.0, sinp));
  sensors_.pitch_deg = static_cast<float>(std::asin(sinp) * 180.0 / M_PI);

  sensors_.last_imu_ts = now_seconds();
}

void SafetyBoardNode::proximity_callback(
    const sensor_msgs::msg::Range::SharedPtr msg) {
  sensors_.proximity_m = msg->range;
  sensors_.last_proximity_ts = now_seconds();
}

void SafetyBoardNode::battery_callback(
    const sensor_msgs::msg::BatteryState::SharedPtr msg) {
  sensors_.battery_percent = msg->percentage * 100.0f;
  sensors_.last_battery_ts = now_seconds();
}

void SafetyBoardNode::altitude_callback(
    const std_msgs::msg::Float32::SharedPtr msg) {
  sensors_.altitude_m = msg->data;
  sensors_.last_altitude_ts = now_seconds();
}

// ============================================================================
// Command Pipeline
// ============================================================================

void SafetyBoardNode::cmd_raw_callback(
    const std_msgs::msg::Float32::SharedPtr msg) {
  commands_received_++;
  SafetyVerdict verdict = evaluate_safety();

  if (verdict.is_safe) {
    cmd_safe_pub_->publish(*msg);
    commands_cleared_++;
    RCLCPP_DEBUG(this->get_logger(),
                 "[SafetyBoard] Command cleared | thrust=%.2f", msg->data);
  } else {
    std_msgs::msg::Float32 zero;
    zero.data = 0.0f;
    cmd_safe_pub_->publish(zero);
    commands_vetoed_++;
    RCLCPP_WARN(this->get_logger(), "[SafetyBoard] VETO | reason: %s",
                verdict.violation_reason.c_str());
  }
}

// ============================================================================
// Safety Evaluation - OR Logic
// ============================================================================

SafetyVerdict SafetyBoardNode::evaluate_safety() const {
  SafetyVerdict verdict;
  double now = now_seconds();

  // -- 1. Sensor staleness --
  std::string stale;
  if (sensors_.last_imu_ts > 0.0 &&
      (now - sensors_.last_imu_ts) > sensor_staleness_s_) {
    stale += "IMU ";
  }
  if (sensors_.last_proximity_ts > 0.0 &&
      (now - sensors_.last_proximity_ts) > sensor_staleness_s_) {
    stale += "proximity ";
  }
  if (sensors_.last_battery_ts > 0.0 &&
      (now - sensors_.last_battery_ts) > sensor_staleness_s_) {
    stale += "battery ";
  }
  if (!stale.empty()) {
    verdict.is_safe = false;
    verdict.violation_reason = "stale_sensor: " + stale;
    return verdict;
  }

  // -- 2. Proximity --
  if (sensors_.proximity_m < min_proximity_m_) {
    verdict.proximity_ok = false;
    verdict.is_safe = false;
    verdict.violation_reason =
        "proximity=" + std::to_string(sensors_.proximity_m) +
        "m < min=" + std::to_string(min_proximity_m_) + "m";
    return verdict;
  }

  // -- 3. Attitude --
  bool pitch_violation = std::abs(sensors_.pitch_deg) > max_pitch_deg_;
  bool roll_violation = std::abs(sensors_.roll_deg) > max_roll_deg_;

  if (pitch_violation || roll_violation) {
    verdict.attitude_ok = false;
    verdict.is_safe = false;
    std::string reason;
    if (pitch_violation) {
      reason += "pitch=" + std::to_string(sensors_.pitch_deg) +
                "deg > max=" + std::to_string(max_pitch_deg_) + "deg ";
    }
    if (roll_violation) {
      reason += "roll=" + std::to_string(sensors_.roll_deg) +
                "deg > max=" + std::to_string(max_roll_deg_) + "deg";
    }
    verdict.violation_reason = "attitude: " + reason;
    return verdict;
  }

  // -- 4. Battery --
  if (sensors_.battery_percent < min_battery_pct_) {
    verdict.battery_ok = false;
    verdict.is_safe = false;
    verdict.violation_reason =
        "battery=" + std::to_string(sensors_.battery_percent) +
        "% < min=" + std::to_string(min_battery_pct_) + "%";
    return verdict;
  }

  // -- 5. Altitude --
  if (sensors_.altitude_m < min_altitude_m_) {
    verdict.altitude_ok = false;
    verdict.is_safe = false;
    verdict.violation_reason =
        "altitude=" + std::to_string(sensors_.altitude_m) +
        "m < min=" + std::to_string(min_altitude_m_) + "m";
    return verdict;
  }
  if (sensors_.altitude_m > max_altitude_m_) {
    verdict.altitude_ok = false;
    verdict.is_safe = false;
    verdict.violation_reason =
        "altitude=" + std::to_string(sensors_.altitude_m) +
        "m > max=" + std::to_string(max_altitude_m_) + "m";
    return verdict;
  }

  return verdict;  // All checks passed
}

// ============================================================================
// Safety Status Publisher
// ============================================================================

void SafetyBoardNode::publish_safety_status() {
  SafetyVerdict verdict = evaluate_safety();

  std_msgs::msg::Float32 status;
  status.data = verdict.is_safe ? 1.0f : 0.0f;
  safety_status_pub_->publish(status);

  static uint64_t log_counter = 0;
  if (++log_counter % 20 == 0) {
    if (verdict.is_safe) {
      RCLCPP_INFO(this->get_logger(),
                  "[SafetyBoard] SAFE | prox=%.2fm pitch=%.1fdeg roll=%.1fdeg "
                  "bat=%.1f%% alt=%.1fm | cleared=%lu vetoed=%lu",
                  sensors_.proximity_m, sensors_.pitch_deg, sensors_.roll_deg,
                  sensors_.battery_percent, sensors_.altitude_m,
                  commands_cleared_, commands_vetoed_);
    } else {
      RCLCPP_WARN(this->get_logger(),
                  "[SafetyBoard] UNSAFE | %s | cleared=%lu vetoed=%lu",
                  verdict.violation_reason.c_str(), commands_cleared_,
                  commands_vetoed_);
    }
  }
}

// ============================================================================
// Helpers
// ============================================================================

void SafetyBoardNode::log_startup() const {
  RCLCPP_INFO(this->get_logger(),
              "============================================================");
  RCLCPP_INFO(this->get_logger(), "SafetyBoard node initialized (C++)");
  RCLCPP_INFO(this->get_logger(), "  min_proximity : %.2f m", min_proximity_m_);
  RCLCPP_INFO(this->get_logger(), "  max_pitch     : %.1f deg", max_pitch_deg_);
  RCLCPP_INFO(this->get_logger(), "  max_roll      : %.1f deg", max_roll_deg_);
  RCLCPP_INFO(this->get_logger(), "  min_battery   : %.1f %%",
              min_battery_pct_);
  RCLCPP_INFO(this->get_logger(), "  altitude range: [%.1f, %.1f] m",
              min_altitude_m_, max_altitude_m_);
  RCLCPP_INFO(this->get_logger(), "  staleness     : %.1f s",
              sensor_staleness_s_);
  RCLCPP_INFO(this->get_logger(),
              "============================================================");
}

double SafetyBoardNode::now_seconds() const { return this->now().seconds(); }

// ============================================================================
// Main
// ============================================================================

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<SafetyBoardNode>());
  rclcpp::shutdown();
  return 0;
}
