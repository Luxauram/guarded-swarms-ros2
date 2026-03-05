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
 * @file mock_sensor_publisher.cpp
 * @brief Mock sensor publisher for SafetyBoard testing without Gazebo.
 *
 * Publishes simulated sensor data by cycling through six scripted scenarios,
 * each lasting @c SCENARIO_DURATION_S seconds, designed to trigger and verify
 * every veto type enforced by the safety board.
 *
 * Scenario table:
 * | Index | Name               | Condition                              |
 * |-------|--------------------|----------------------------------------|
 * |   0   | NOMINAL            | All sensors within safe range          |
 * |   1   | PROXIMITY          | Obstacle at 0.8 m  (threshold: 1.5 m) |
 * |   2   | ATTITUDE           | Pitch at 45 deg    (threshold: 30 deg) |
 * |   3   | BATTERY LOW        | Battery at 10 %    (threshold: 15 %)  |
 * |   4   | ALTITUDE TOO HIGH  | Altitude at 60 m   (threshold: 50 m)  |
 * |   5   | NOMINAL (RECOVERY) | All sensors back within safe range     |
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/range.hpp>
#include <sensor_msgs/msg/battery_state.hpp>
#include <std_msgs/msg/float32.hpp>

#include <chrono>
#include <cmath>
#include <string>
#include <vector>

using namespace std::chrono_literals;

// ============================================================================
// Scenario Definition
// ============================================================================

/**
 * @brief Descriptor for a single scripted sensor scenario.
 *
 * Each field defines the value that will be published on the corresponding
 * sensor topic for the duration of the scenario.
 */
struct Scenario
{
  std::string name;  ///< Human-readable scenario identifier.
  float proximity_m; ///< Simulated obstacle distance (m).
  float pitch_deg;   ///< Simulated pitch angle (degrees).
  float roll_deg;    ///< Simulated roll angle (degrees).
  float battery_pct; ///< Simulated battery state of charge (0–100).
  float altitude_m;  ///< Simulated altitude above ground (m).
};

static const std::vector<Scenario> SCENARIOS = {
    {"NOMINAL", 5.0f, 5.0f, 3.0f, 80.0f, 10.0f},
    {"PROXIMITY VIOLATION", 0.8f, 5.0f, 3.0f, 80.0f, 10.0f},
    {"ATTITUDE VIOLATION", 5.0f, 45.0f, 3.0f, 80.0f, 10.0f},
    {"BATTERY LOW", 5.0f, 5.0f, 3.0f, 10.0f, 10.0f},
    {"ALTITUDE TOO HIGH", 5.0f, 5.0f, 3.0f, 80.0f, 60.0f},
    {"NOMINAL (RECOVERY)", 5.0f, 5.0f, 3.0f, 80.0f, 10.0f},
};

static constexpr double SCENARIO_DURATION_S = 10.0;
static constexpr double PUBLISH_RATE_HZ = 10.0;

// ============================================================================
// MockSensorPublisher
// ============================================================================

/**
 * @brief ROS 2 node that publishes scripted sensor data and raw actuator
 *        commands for SafetyBoard integration testing.
 *
 * The node cycles through the entries of @c SCENARIOS in order. After the
 * last scenario completes the cycle restarts from the beginning.
 */
class MockSensorPublisher : public rclcpp::Node
{
public:
  /**
   * @brief Constructs the node, creates all publishers, and starts the
   *        periodic publish timer.
   */
  MockSensorPublisher()
      : Node("mock_sensor_publisher"),
        current_scenario_idx_(0)
  {
    imu_pub_ = this->create_publisher<sensor_msgs::msg::Imu>("/drone/imu", 10);
    proximity_pub_ = this->create_publisher<sensor_msgs::msg::Range>("/drone/proximity", 10);
    battery_pub_ = this->create_publisher<sensor_msgs::msg::BatteryState>("/drone/battery", 10);
    altitude_pub_ = this->create_publisher<std_msgs::msg::Float32>("/drone/altitude", 10);

    start_time_ = this->now().seconds();

    auto period = std::chrono::duration<double>(1.0 / PUBLISH_RATE_HZ);
    timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(period),
        std::bind(&MockSensorPublisher::publish_all, this));

    RCLCPP_INFO(this->get_logger(), "MockSensorPublisher started (C++)");
    RCLCPP_INFO(this->get_logger(), "Cycling through %zu scenarios, %.0fs each",
                SCENARIOS.size(), SCENARIO_DURATION_S);
  }

private:
  /**
   * @brief Determines the active scenario based on elapsed time.
   *
   * Emits a warning log message whenever a scenario transition occurs.
   *
   * @return Const reference to the currently active @c Scenario entry.
   */
  const Scenario &get_current_scenario()
  {
    double elapsed = this->now().seconds() - start_time_;
    size_t idx = static_cast<size_t>(elapsed / SCENARIO_DURATION_S) % SCENARIOS.size();

    if (idx != current_scenario_idx_)
    {
      current_scenario_idx_ = idx;
      RCLCPP_WARN(this->get_logger(),
                  "[MockSensors] >>> Scenario %zu: %s <<<",
                  idx, SCENARIOS[idx].name.c_str());
    }

    return SCENARIOS[idx];
  }

  /**
   * @brief Timer callback that publishes all sensor topics and a constant
   *        raw actuator command for the current scenario.
   */
  void publish_all()
  {
    const Scenario &s = get_current_scenario();

    publish_imu(s.pitch_deg, s.roll_deg);
    publish_proximity(s.proximity_m);
    publish_battery(s.battery_pct);
    publish_altitude(s.altitude_m);
  }

  /**
   * @brief Converts Euler angles to a unit quaternion and publishes an IMU
   *        message with the resulting orientation.
   *
   * The conversion follows the ZYX (yaw–pitch–roll) convention with yaw
   * fixed at zero.
   *
   * @param pitch_deg Desired pitch angle in degrees.
   * @param roll_deg  Desired roll angle in degrees.
   */
  void publish_imu(float pitch_deg, float roll_deg)
  {
    double pitch = static_cast<double>(pitch_deg) * M_PI / 180.0;
    double roll = static_cast<double>(roll_deg) * M_PI / 180.0;
    double yaw = 0.0;

    double cy = std::cos(yaw * 0.5);
    double sy = std::sin(yaw * 0.5);
    double cp = std::cos(pitch * 0.5);
    double sp = std::sin(pitch * 0.5);
    double cr = std::cos(roll * 0.5);
    double sr = std::sin(roll * 0.5);

    sensor_msgs::msg::Imu msg;
    msg.orientation.w = cr * cp * cy + sr * sp * sy;
    msg.orientation.x = sr * cp * cy - cr * sp * sy;
    msg.orientation.y = cr * sp * cy + sr * cp * sy;
    msg.orientation.z = cr * cp * sy - sr * sp * cy;

    imu_pub_->publish(msg);
  }

  /**
   * @brief Publishes a Range message with the specified obstacle distance.
   *
   * @param distance_m Simulated distance to the nearest obstacle in metres.
   */
  void publish_proximity(float distance_m)
  {
    sensor_msgs::msg::Range msg;
    msg.range = distance_m;
    msg.min_range = 0.1f;
    msg.max_range = 10.0f;
    proximity_pub_->publish(msg);
  }

  /**
   * @brief Publishes a BatteryState message with the specified charge level.
   *
   * @param percent Simulated battery charge in the range [0, 100].
   *                The value is converted to the [0.0, 1.0] scale required
   *                by the BatteryState message type.
   */
  void publish_battery(float percent)
  {
    sensor_msgs::msg::BatteryState msg;
    msg.percentage = percent / 100.0f;
    battery_pub_->publish(msg);
  }

  /**
   * @brief Publishes a Float32 message containing the simulated altitude.
   *
   * @param altitude_m Simulated altitude above ground in metres.
   */
  void publish_altitude(float altitude_m)
  {
    std_msgs::msg::Float32 msg;
    msg.data = altitude_m;
    altitude_pub_->publish(msg);
  }

  rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr proximity_pub_;
  rclcpp::Publisher<sensor_msgs::msg::BatteryState>::SharedPtr battery_pub_;
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr altitude_pub_;

  rclcpp::TimerBase::SharedPtr timer_;
  double start_time_;
  size_t current_scenario_idx_;
};

// ============================================================================
// Main
// ============================================================================

/**
 * @brief Entry point. Initialises the ROS 2 runtime and spins the
 *        MockSensorPublisher node until shutdown.
 *
 * @param argc Argument count forwarded to @c rclcpp::init.
 * @param argv Argument vector forwarded to @c rclcpp::init.
 * @return 0 on clean exit.
 */
int main(int argc, char *argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MockSensorPublisher>());
  rclcpp::shutdown();
  return 0;
}
