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
 * @file intruder_node.cpp
 *
 * @brief Scripted trajectory driver for the hostile aerial target.
 *
 * Drives the intruder model of the coastal surveillance scenario described in
 * Borghoff, Bottoni and Pareschi (2026), IET Radar, Sonar and Navigation,
 * Section 5: the swarm must detect, classify and intercept a potentially
 * hostile aerial target approaching through the maritime corridor.
 *
 * This node does NOT belong to the swarm. It is scenario machinery: it plays
 * the adversary so that the sensing and coordination layers have something to
 * react to. It is kept deliberately dumb — a straight ingress at constant
 * speed and altitude — because its purpose is to be reproducible, not
 * realistic. Detection latencies measured across runs are only comparable if
 * the stimulus is identical every time.
 *
 * All motion is commanded in world ENU coordinates, matching Gazebo. The PX4
 * vehicles reason in NED; the consultant agents are responsible for whatever
 * frame conversion their own observation model requires.
 *
 * Phases:
 *   IDLE      before start_delay_s, the target holds at its spawn point
 *   INGRESS   constant-velocity run toward the target point
 *   ARRIVED   velocity zeroed, the target holds station
 *
 * Topics:
 *   Published:
 *     /model/intruder/cmd_vel   (geometry_msgs/Twist)  via ros_gz_bridge
 *     intruder/ground_truth     (geometry_msgs/PoseStamped)
 *     intruder/active           (std_msgs/Bool)
 *   Subscribed:
 *     /model/intruder/odometry  (nav_msgs/Odometry)    via ros_gz_bridge
 *
 * Parameters (all in world ENU metres, seconds, metres per second):
 *   ingress_x, ingress_y, ingress_z   spawn / start point
 *   target_x, target_y, target_z      point the target runs toward
 *   speed_mps                         cruise speed along the ingress leg
 *   start_delay_s                     quiet period before ingress begins
 *   arrival_radius_m                  distance at which the run is complete
 *   cmd_vel_topic, odometry_topic     bridge topic names
 *
 * The counterfactual trajectories of the paper (Section 5.3) are meant to be
 * expressed as parameter sets over this node, not as separate code paths.
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <std_msgs/msg/bool.hpp>

#include <cmath>
#include <string>

using namespace std::chrono_literals;

static constexpr double PUBLISH_RATE_HZ = 20.0;

class IntruderNode : public rclcpp::Node {
 public:
  IntruderNode() : Node("intruder_node") {
    ingress_x_ = this->declare_parameter<double>("ingress_x", 0.0);
    ingress_y_ = this->declare_parameter<double>("ingress_y", 180.0);
    ingress_z_ = this->declare_parameter<double>("ingress_z", 15.0);

    target_x_ = this->declare_parameter<double>("target_x", 0.0);
    target_y_ = this->declare_parameter<double>("target_y", 10.0);
    target_z_ = this->declare_parameter<double>("target_z", 15.0);

    speed_mps_ = this->declare_parameter<double>("speed_mps", 8.0);
    start_delay_s_ = this->declare_parameter<double>("start_delay_s", 20.0);
    arrival_radius_m_ = this->declare_parameter<double>("arrival_radius_m", 3.0);

    const auto cmd_topic = this->declare_parameter<std::string>(
        "cmd_vel_topic", "/model/intruder/cmd_vel");
    const auto odom_topic = this->declare_parameter<std::string>(
        "odometry_topic", "/model/intruder/odometry");

    cmd_pub_ = this->create_publisher<geometry_msgs::msg::Twist>(cmd_topic, 10);
    truth_pub_ = this->create_publisher<geometry_msgs::msg::PoseStamped>(
        "intruder/ground_truth", 10);
    active_pub_ =
        this->create_publisher<std_msgs::msg::Bool>("intruder/active", 10);

    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
        odom_topic, 10,
        [this](const nav_msgs::msg::Odometry::SharedPtr msg) {
          x_ = msg->pose.pose.position.x;
          y_ = msg->pose.pose.position.y;
          z_ = msg->pose.pose.position.z;
          pose_valid_ = true;
        });

    timer_ = this->create_wall_timer(
        std::chrono::duration<double>(1.0 / PUBLISH_RATE_HZ),
        [this]() { step(); });

    start_time_ = this->now();

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "IntruderNode initialized");
    RCLCPP_INFO(this->get_logger(), "  ingress : (%.1f, %.1f, %.1f)",
                ingress_x_, ingress_y_, ingress_z_);
    RCLCPP_INFO(this->get_logger(), "  target  : (%.1f, %.1f, %.1f)",
                target_x_, target_y_, target_z_);
    RCLCPP_INFO(this->get_logger(), "  speed   : %.1f m/s", speed_mps_);
    RCLCPP_INFO(this->get_logger(), "  start in: %.0f s", start_delay_s_);
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  enum class Phase { Idle, Ingress, Arrived };

  void step() {
    const double elapsed = (this->now() - start_time_).seconds();

    if (pose_valid_) {
      publish_ground_truth();
    }

    switch (phase_) {
      case Phase::Idle:
        publish_velocity(0.0, 0.0, 0.0);
        if (elapsed >= start_delay_s_) {
          phase_ = Phase::Ingress;
          RCLCPP_WARN(this->get_logger(),
                      "Ingress started: heading for (%.1f, %.1f, %.1f)",
                      target_x_, target_y_, target_z_);
        }
        break;

      case Phase::Ingress: {
        if (!pose_valid_) {
          // Without odometry the heading cannot be computed. Holding still is
          // the correct fallback: a blind constant velocity would produce a
          // different trajectory on every run and destroy comparability.
          publish_velocity(0.0, 0.0, 0.0);
          RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                               "No odometry from the intruder model; holding. "
                               "Is the ros_gz bridge running?");
          return;
        }

        const double dx = target_x_ - x_;
        const double dy = target_y_ - y_;
        const double dz = target_z_ - z_;
        const double dist = std::sqrt(dx * dx + dy * dy + dz * dz);

        if (dist < arrival_radius_m_) {
          phase_ = Phase::Arrived;
          publish_velocity(0.0, 0.0, 0.0);
          RCLCPP_WARN(this->get_logger(),
                      "Target point reached at (%.1f, %.1f, %.1f)", x_, y_, z_);
          break;
        }

        const double scale = speed_mps_ / dist;
        publish_velocity(dx * scale, dy * scale, dz * scale);
        break;
      }

      case Phase::Arrived:
        publish_velocity(0.0, 0.0, 0.0);
        break;
    }
  }

  void publish_velocity(double vx, double vy, double vz) {
    geometry_msgs::msg::Twist cmd;
    cmd.linear.x = vx;
    cmd.linear.y = vy;
    cmd.linear.z = vz;
    cmd_pub_->publish(cmd);

    std_msgs::msg::Bool active;
    active.data = (phase_ == Phase::Ingress);
    active_pub_->publish(active);
  }

  void publish_ground_truth() {
    geometry_msgs::msg::PoseStamped truth;
    truth.header.stamp = this->now();
    truth.header.frame_id = "world";
    truth.pose.position.x = x_;
    truth.pose.position.y = y_;
    truth.pose.position.z = z_;
    truth.pose.orientation.w = 1.0;
    truth_pub_->publish(truth);
  }

  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr cmd_pub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr truth_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr active_pub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::TimerBase::SharedPtr timer_;

  rclcpp::Time start_time_;
  Phase phase_ = Phase::Idle;

  double ingress_x_, ingress_y_, ingress_z_;
  double target_x_, target_y_, target_z_;
  double speed_mps_, start_delay_s_, arrival_radius_m_;

  double x_ = 0.0, y_ = 0.0, z_ = 0.0;
  bool pose_valid_ = false;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<IntruderNode>());
  rclcpp::shutdown();
  return 0;
}
