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
 * @file offboard_control_node.cpp
 *
 * Offboard position control node for PX4 UAV via ROS 2.
 *
 * This node demonstrates autonomous flight control using the PX4 offboard mode.
 * It publishes trajectory setpoints at 10Hz to maintain a stable hover
 * position, enables offboard control mode, and commands the drone to arm and
 * takeoff.
 *
 * The control sequence:
 * 1. Publish position setpoints for 5 seconds (PX4 validation period)
 * 2. Request offboard mode activation
 * 3. Send arm command with force flag
 * 4. Continue publishing setpoints to maintain flight
 *
 * @author Luca D'Aurizio
 */

#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <rclcpp/rclcpp.hpp>

#include <chrono>
#include <cmath>

using namespace std::chrono_literals;

/**
 * ROS 2 node for PX4 offboard position control.
 *
 * Publishes trajectory setpoints and vehicle commands to control a PX4 drone
 * in offboard mode. Maintains hover at a fixed altitude above the start
 * position.
 */
class OffboardControlNode : public rclcpp::Node {
public:
  /**
   * Constructor - initializes publishers and timer.
   *
   * Sets up ROS 2 publishers for offboard control mode, trajectory setpoints,
   * and vehicle commands. Creates a 10Hz timer for continuous setpoint
   * publishing.
   */
  OffboardControlNode() : Node("offboard_control_node") {
    offboard_setpoint_counter_ = 0;

    target_system_ = static_cast<uint8_t>(
        this->declare_parameter<int>("target_system", 1));

    // Hover altitude in metres, positive up. Multi-UAV scenarios stack the
    // platforms at different altitudes so their patrol volumes do not overlap.
    hover_altitude_m_ = this->declare_parameter<double>("hover_altitude", 5.0);

    offboard_control_mode_publisher_ =
        this->create_publisher<px4_msgs::msg::OffboardControlMode>(
            TOPIC_OFFBOARD_CONTROL_MODE, QUEUE_SIZE);

    trajectory_setpoint_publisher_ =
        this->create_publisher<px4_msgs::msg::TrajectorySetpoint>(
            TOPIC_TRAJECTORY_SETPOINT, QUEUE_SIZE);

    vehicle_command_publisher_ =
        this->create_publisher<px4_msgs::msg::VehicleCommand>(
            TOPIC_VEHICLE_COMMAND, QUEUE_SIZE);

    auto status_qos = rclcpp::QoS(QUEUE_SIZE)
        .reliability(rclcpp::ReliabilityPolicy::BestEffort)
        .durability(rclcpp::DurabilityPolicy::TransientLocal);

    vehicle_status_subscriber_ =
        this->create_subscription<px4_msgs::msg::VehicleStatus>(
            TOPIC_VEHICLE_STATUS, status_qos,
            [this](const px4_msgs::msg::VehicleStatus::SharedPtr msg) {
              armed_ = (msg->arming_state ==
                        px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED);
            });

    timer_ = this->create_wall_timer(
        TIMER_PERIOD, std::bind(&OffboardControlNode::timer_callback, this));

    RCLCPP_INFO(this->get_logger(), "Offboard control node started");
    RCLCPP_INFO(this->get_logger(), "Target hover altitude: %.1f meters",
                hover_altitude_m_);
    RCLCPP_INFO(this->get_logger(), "Waiting %.1f seconds before arming...",
                ARMING_DELAY_SECONDS);
    RCLCPP_INFO(this->get_logger(), "Target system ID: %u", target_system_);
  }

private:
  // ========================================================================
  // Constants
  // ========================================================================

  // ROS 2 Topic Names
  static constexpr const char *TOPIC_OFFBOARD_CONTROL_MODE =
      "fmu/in/offboard_control_mode";
  static constexpr const char *TOPIC_TRAJECTORY_SETPOINT =
      "fmu/in/trajectory_setpoint";
  static constexpr const char *TOPIC_VEHICLE_COMMAND =
      "fmu/in/vehicle_command";
  static constexpr const char *TOPIC_VEHICLE_STATUS =
      "fmu/out/vehicle_status_v1";

  // Publisher Configuration
  static constexpr int QUEUE_SIZE = 10;

  // Timer Configuration
  static constexpr std::chrono::milliseconds TIMER_PERIOD{100}; // 10Hz
  static constexpr double TIMER_FREQUENCY_HZ = 10.0;

  // Arming Sequence Timing
  static constexpr double ARMING_DELAY_SECONDS = 5.0;
  static constexpr int ARMING_COUNTER_THRESHOLD =
      static_cast<int>(ARMING_DELAY_SECONDS * TIMER_FREQUENCY_HZ);

  // Flight Parameters (NED Frame)
  static constexpr double HOVER_ALTITUDE_METERS = 5.0;
  static constexpr double TARGET_POSITION_NORTH = 0.0; // meters
  static constexpr double TARGET_POSITION_EAST = 0.0;  // meters
  static constexpr double TARGET_YAW_RADIANS = 0.0;    // facing north

  // PX4 Command IDs
  static constexpr uint16_t CMD_SET_MODE = 176;
  static constexpr uint16_t CMD_ARM_DISARM = 400;

  // PX4 Command Parameters
  static constexpr float PARAM_CUSTOM_MAIN_MODE = 1.0f;
  static constexpr float PARAM_CUSTOM_SUB_MODE_OFFBOARD = 6.0f;
  static constexpr float PARAM_ARM = 1.0f;
  static constexpr float PARAM_FORCE_ARM =
      21196.0f; // bypasses preflight checks - @TODO

  // PX4 component ID. 
  // The system ID is deliberately NOT a constant: it is a
  // ROS parameter, see target_system_.
  static constexpr uint8_t PX4_COMPONENT_ID = 1;

  // Re-issue mode + arm every N cycles until PX4 reports armed. Sending them
  // once is not enough: if PX4 is not ready at that exact instant, or the DDS
  // session is still settling, the commands are lost and the vehicle never
  // takes off.
  static constexpr int ARMING_RETRY_PERIOD_CYCLES = 20;  // 2 s at 10 Hz

  // ========================================================================
  // Methods
  // ========================================================================

  /**
   * Main control loop callback, executed at 10Hz.
   *
   * Continuously publishes offboard control mode and trajectory setpoints.
   * After the arming delay period, sends commands to enable offboard mode
   * and arm the drone.
   */
  void timer_callback() {
    publish_offboard_control_mode();
    publish_trajectory_setpoint();

    const auto counter = static_cast<int>(offboard_setpoint_counter_);

    if (!armed_ && counter >= ARMING_COUNTER_THRESHOLD &&
        (counter - ARMING_COUNTER_THRESHOLD) % ARMING_RETRY_PERIOD_CYCLES == 0) {

      RCLCPP_INFO(this->get_logger(), "Enabling offboard mode...");
      publish_vehicle_command(CMD_SET_MODE, PARAM_CUSTOM_MAIN_MODE,
                              PARAM_CUSTOM_SUB_MODE_OFFBOARD);

      RCLCPP_INFO(this->get_logger(), "Arming drone (force flag enabled)...");
      publish_vehicle_command(CMD_ARM_DISARM, PARAM_ARM, PARAM_FORCE_ARM);
    }

    if (armed_ && !arm_confirmed_) {
      arm_confirmed_ = true;
      RCLCPP_INFO(this->get_logger(), "PX4 reports ARMED. Holding hover.");
    }

    offboard_setpoint_counter_++;
  }

  /**
   * Publishes offboard control mode configuration.
   *
   * Informs PX4 which control dimensions are active. This implementation
   * enables position control only, disabling velocity and acceleration control.
   */
  void publish_offboard_control_mode() {
    px4_msgs::msg::OffboardControlMode msg;

    msg.timestamp = get_timestamp_microseconds();
    msg.position = true;
    msg.velocity = false;
    msg.acceleration = false;
    msg.attitude = false;
    msg.body_rate = false;

    offboard_control_mode_publisher_->publish(msg);
  }

  /**
   * Publishes trajectory setpoint for position control.
   *
   * Sends target position in NED (North-East-Down) coordinate frame.
   *
   * Velocity and acceleration fields are set to NaN to indicate they
   * are not used for control.
   */
  void publish_trajectory_setpoint() {
    px4_msgs::msg::TrajectorySetpoint msg;

    msg.timestamp = get_timestamp_microseconds();

    msg.position[0] = TARGET_POSITION_NORTH;
    msg.position[1] = TARGET_POSITION_EAST;
    msg.position[2] = -hover_altitude_m_;

    msg.yaw = TARGET_YAW_RADIANS;

    msg.velocity[0] = NAN;
    msg.velocity[1] = NAN;
    msg.velocity[2] = NAN;
    msg.acceleration[0] = NAN;
    msg.acceleration[1] = NAN;
    msg.acceleration[2] = NAN;
    msg.jerk[0] = NAN;
    msg.jerk[1] = NAN;
    msg.jerk[2] = NAN;
    msg.yawspeed = NAN;

    trajectory_setpoint_publisher_->publish(msg);
  }

  /**
   * Sends a vehicle command to PX4.
   *
   * @param command The MAVLink command ID (e.g., CMD_SET_MODE, CMD_ARM_DISARM)
   * @param param1 First command parameter (command-specific meaning)
   * @param param2 Second command parameter (command-specific meaning)
   */
  void publish_vehicle_command(uint16_t command, float param1 = 0.0f,
                               float param2 = 0.0f) {
    px4_msgs::msg::VehicleCommand msg;

    msg.timestamp = get_timestamp_microseconds();
    msg.command = command;
    msg.param1 = param1;
    msg.param2 = param2;
    msg.target_system = target_system_;
    msg.target_component = PX4_COMPONENT_ID;
    msg.source_system = target_system_;
    msg.source_component = PX4_COMPONENT_ID;
    msg.from_external = true;

    vehicle_command_publisher_->publish(msg);

    RCLCPP_INFO(this->get_logger(),
                "Sent vehicle command %d (param1: %.1f, param2: %.1f)", command,
                param1, param2);
  }

  /**
   * Gets current ROS time in microseconds.
   *
   * PX4 expects timestamps in microseconds since epoch for proper
   * time synchronization across the system.
   *
   * @return Current time in microseconds
   */
  uint64_t get_timestamp_microseconds() {
    return this->get_clock()->now().nanoseconds() / 1000;
  }

  // ========================================================================
  // Variables
  // ========================================================================

  rclcpp::TimerBase::SharedPtr timer_;

  rclcpp::Publisher<px4_msgs::msg::OffboardControlMode>::SharedPtr
      offboard_control_mode_publisher_;

  rclcpp::Publisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr
      trajectory_setpoint_publisher_;

  rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr
      vehicle_command_publisher_;

  rclcpp::Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr
      vehicle_status_subscriber_;

  uint64_t offboard_setpoint_counter_;
  uint8_t target_system_ = 1;
  double hover_altitude_m_ = 5.0;
  bool armed_ = false;
  bool arm_confirmed_ = false;
};

// ============================================================================
// Main Function
// ============================================================================

/**
 * Main entry point for the offboard control node.
 *
 * Initializes ROS 2, creates the offboard control node instance,
 * and spins until shutdown.
 *
 * @param argc Command line argument count
 * @param argv Command line argument values
 * @return Exit code (0 on success)
 */
int main(int argc, char *argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<OffboardControlNode>());
  rclcpp::shutdown();

  return 0;
}
