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
 * @file px4_safety_bridge_node.cpp
 * @brief Adapter node that converts PX4 SITL topics to standard safety board
 * topics.
 *
 * Subscribes to PX4 uORB topics exposed via ROS 2 and republishes them as
 * standard ROS 2 sensor messages compatible with @c SafetyBoardNode. This
 * keeps the safety board completely decoupled from PX4-specific message types.
 *
 * Topic mapping:
 * | PX4 / Gazebo source topic                 | Safety board topic  | Message
 * type                  |
 * |-------------------------------------------|---------------------|-------------------------------|
 * | /fmu/out/vehicle_attitude                 | /drone/imu          |
 * sensor_msgs/Imu               | | /fmu/out/battery_status_v1                |
 * /drone/battery      | sensor_msgs/BatteryState      | |
 * /fmu/out/vehicle_local_position_v1        | /drone/altitude     |
 * std_msgs/Float32              | | Gazebo lidar/scan (via ros_gz_bridge)     |
 * /drone/proximity    | sensor_msgs/Range             |
 *
 * @note The lidar topic name is configurable via the ROS parameter
 *       @c lidar_topic, defaulting to the x500_lidar_front_0 model path.
 *
 * @author Luca D'Aurizio
 */

#include <cmath>
#include <rclcpp/rclcpp.hpp>

#include <px4_msgs/msg/battery_status.hpp>
#include <px4_msgs/msg/vehicle_attitude.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>

#include <sensor_msgs/msg/battery_state.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <sensor_msgs/msg/range.hpp>
#include <std_msgs/msg/float32.hpp>

using namespace std::chrono_literals;

// ============================================================================
// Px4SafetyBridgeNode
// ============================================================================

/**
 * @brief ROS 2 adapter node bridging PX4 uORB topics and Gazebo lidar data
 *        to the SafetyBoard sensor interface.
 *
 * All PX4 subscriptions use @c BEST_EFFORT QoS to match the reliability
 * policy of the PX4 SITL publishers. The translated messages are republished
 * with the default @c RELIABLE QoS expected by @c SafetyBoardNode.
 *
 * The lidar LaserScan is received via ros_gz_bridge and converted to a
 * sensor_msgs/Range by taking the minimum finite range value.
 */
class Px4SafetyBridgeNode : public rclcpp::Node {
public:
  Px4SafetyBridgeNode() : Node("px4_safety_bridge_node") {
    this->declare_parameter("lidar_topic",
                            "/world/default/model/x500_lidar_front_0/link/"
                            "lidar_sensor_link/sensor/lidar/scan");
    std::string lidar_topic = this->get_parameter("lidar_topic").as_string();

    auto px4_qos = rclcpp::QoS(10)
                       .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                       .durability(rclcpp::DurabilityPolicy::Volatile)
                       .history(rclcpp::HistoryPolicy::KeepLast);

    attitude_sub_ = this->create_subscription<px4_msgs::msg::VehicleAttitude>(
        "fmu/out/vehicle_attitude", px4_qos,
        [this](const px4_msgs::msg::VehicleAttitude::SharedPtr msg) {
          on_attitude(msg);
        });

    battery_sub_ = this->create_subscription<px4_msgs::msg::BatteryStatus>(
        "fmu/out/battery_status_v1", px4_qos,
        [this](const px4_msgs::msg::BatteryStatus::SharedPtr msg) {
          on_battery(msg);
        });

    local_pos_sub_ =
        this->create_subscription<px4_msgs::msg::VehicleLocalPosition>(
            "fmu/out/vehicle_local_position_v1", px4_qos,
            [this](const px4_msgs::msg::VehicleLocalPosition::SharedPtr msg) {
              on_local_position(msg);
            });

    lidar_sub_ = this->create_subscription<sensor_msgs::msg::LaserScan>(
        lidar_topic, 10,
        [this](const sensor_msgs::msg::LaserScan::SharedPtr msg) {
          on_lidar(msg);
        });

    imu_pub_ = this->create_publisher<sensor_msgs::msg::Imu>("/drone/imu", 10);
    battery_pub_ = this->create_publisher<sensor_msgs::msg::BatteryState>(
        "/drone/battery", 10);
    altitude_pub_ =
        this->create_publisher<std_msgs::msg::Float32>("/drone/altitude", 10);
    proximity_pub_ =
        this->create_publisher<sensor_msgs::msg::Range>("/drone/proximity", 10);

    RCLCPP_INFO(this->get_logger(),
                "Px4SafetyBridge initialized (BEST_EFFORT QoS)");
    RCLCPP_INFO(this->get_logger(),
                "  /fmu/out/vehicle_attitude          -> /drone/imu");
    RCLCPP_INFO(this->get_logger(),
                "  /fmu/out/battery_status_v1         -> /drone/battery");
    RCLCPP_INFO(this->get_logger(),
                "  /fmu/out/vehicle_local_position_v1 -> /drone/altitude");
    RCLCPP_INFO(this->get_logger(), "  %s -> /drone/proximity",
                lidar_topic.c_str());
  }

private:
  /**
   * @brief Translates a PX4 @c VehicleAttitude message to a @c sensor_msgs/Imu
   *        message and publishes it on @c /drone/imu.
   *
   * The quaternion components are mapped directly from the PX4 array
   * representation @c q[w, x, y, z] to the ROS 2 orientation fields.
   *
   * @param msg Shared pointer to the received @c VehicleAttitude message.
   */
  void on_attitude(const px4_msgs::msg::VehicleAttitude::SharedPtr msg) {
    sensor_msgs::msg::Imu imu_msg;
    imu_msg.orientation.w = msg->q[0];
    imu_msg.orientation.x = msg->q[1];
    imu_msg.orientation.y = msg->q[2];
    imu_msg.orientation.z = msg->q[3];
    imu_pub_->publish(imu_msg);
  }

  /**
   * @brief Translates a PX4 @c BatteryStatus message to a
   *        @c sensor_msgs/BatteryState message and publishes it on
   *        @c /drone/battery.
   *
   * The @c remaining field of @c BatteryStatus is in the range [0.0, 1.0]
   * and maps directly to the @c percentage field of @c BatteryState.
   *
   * @param msg Shared pointer to the received @c BatteryStatus message.
   */
  void on_battery(const px4_msgs::msg::BatteryStatus::SharedPtr msg) {
    sensor_msgs::msg::BatteryState bat_msg;
    bat_msg.percentage = msg->remaining;
    battery_pub_->publish(bat_msg);
  }

  /**
   * @brief Translates a PX4 @c VehicleLocalPosition message to an altitude
   *        value and publishes it on @c /drone/altitude.
   *
   * The NED down axis is negated to obtain a positive altitude above ground.
   * Messages with an invalid @c z estimate are silently discarded.
   *
   * @param msg Shared pointer to the received @c VehicleLocalPosition message.
   */
  void
  on_local_position(const px4_msgs::msg::VehicleLocalPosition::SharedPtr msg) {
    if (!msg->z_valid)
      return;

    std_msgs::msg::Float32 alt_msg;
    alt_msg.data = -msg->z;
    altitude_pub_->publish(alt_msg);
    RCLCPP_DEBUG(this->get_logger(), "altitude=%.2fm", alt_msg.data);
  }

  /**
   * @brief Converts Gazebo LaserScan to sensor_msgs/Range for the safety board.
   *
   * Takes the minimum finite range value across all rays as the closest
   * obstacle distance. If all rays return inf (no obstacle), range_max
   * is used as a safe fallback.
   */
  void on_lidar(const sensor_msgs::msg::LaserScan::SharedPtr msg) {
    float min_range = msg->range_max;
    for (float r : msg->ranges) {
      if (std::isfinite(r) && r < min_range) {
        min_range = r;
      }
    }
    if (!std::isfinite(min_range)) {
      min_range = msg->range_max;
    }

    sensor_msgs::msg::Range prox_msg;
    prox_msg.range = min_range;
    prox_msg.min_range = msg->range_min;
    prox_msg.max_range = msg->range_max;
    proximity_pub_->publish(prox_msg);

    RCLCPP_DEBUG(this->get_logger(), "proximity=%.2fm", min_range);
  }

  rclcpp::Subscription<px4_msgs::msg::VehicleAttitude>::SharedPtr attitude_sub_;
  rclcpp::Subscription<px4_msgs::msg::BatteryStatus>::SharedPtr battery_sub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr
      local_pos_sub_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr lidar_sub_;

  rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_pub_;
  rclcpp::Publisher<sensor_msgs::msg::BatteryState>::SharedPtr battery_pub_;
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr altitude_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr proximity_pub_;
};

// ============================================================================
// Main
// ============================================================================

/**
 * @brief Entry point. Initialises the ROS 2 runtime and spins the
 *        Px4SafetyBridgeNode until shutdown.
 *
 * @param argc Argument count forwarded to @c rclcpp::init.
 * @param argv Argument vector forwarded to @c rclcpp::init.
 * @return 0 on clean exit.
 */
int main(int argc, char *argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Px4SafetyBridgeNode>());
  rclcpp::shutdown();
  return 0;
}
