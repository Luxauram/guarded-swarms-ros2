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
 * Drives the intruder model of the coastal surveillance scenario: the swarm
 * must detect, classify and intercept a potentially hostile aerial target
 * approaching through the maritime corridor.
 *
 * This node does NOT belong to the swarm. It is scenario machinery: it plays
 * the adversary so the sensing and coordination layers have something to react
 * to. It is kept deliberately dumb - a straight ingress at constant speed and
 * altitude - because its purpose is to be reproducible, not realistic.
 *
 * OPEN-LOOP BY DESIGN
 * ===================
 * The commanded velocity is a pure function of elapsed time and the ingress
 * parameters. It does NOT depend on any feedback from Gazebo.
 *
 * A heading computed from the model's own odometry would deadlock: Gazebo's
 * OdometryPublisher only emits while the model moves, so a node that moves
 * only while it receives odometry can stall. Commanding open-loop removes the
 * loop entirely, and makes the trajectory repeatable: the same parameters
 * always produce the same path.
 *
 * The dead-reckoned position, integrated from the commanded velocity, is the
 * ground truth published for the consultant agents, and decides when the run
 * is complete. The model moves kinematically, without gravity, so it follows
 * the same path; only a collision in Gazebo would make the two differ.
 *
 * SIMULATED TIME
 * ==============
 * The node runs on the simulation clock (use_sim_time): the start delay, the
 * dead reckoning and the publication timer all follow simulated time, like
 * Gazebo and PX4. On the wall clock the target would cover its route faster
 * in simulated time whenever the real-time factor is below 1, and every
 * latency measured in simulated time would depend on the load of the machine.
 *
 * All motion is in world ENU, matching Gazebo. The PX4 vehicles reason in NED;
 * frame conversion, if any, is the consultant agents' responsibility.
 *
 * Phases:
 *   IDLE      before start_delay_s, the target holds at its spawn point
 *   INGRESS   constant-velocity run toward the target point
 *   ARRIVED   velocity zeroed, the target holds station
 *
 * Topics:
 *   Published:
 *     /model/intruder/cmd_vel   (geometry_msgs/Twist)   via ros_gz_bridge
 *     intruder/ground_truth     (geometry_msgs/PoseStamped)
 *     intruder/active           (std_msgs/Bool)
 *     intruder/transmitting     (std_msgs/Bool)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/create_timer.hpp>
#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <std_msgs/msg/bool.hpp>

#include <cmath>
#include <string>

using namespace std::chrono_literals;

static constexpr double PUBLISH_RATE_HZ = 20.0;
static constexpr int QUEUE_SIZE = 10;

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
    // Whether the target emits a detectable radio control link. A silent
    // target is invisible to the RF modality: the radio-silence
    // counterfactual.
    transmitting_ = this->declare_parameter<bool>("transmitting", true);
    start_delay_s_ = this->declare_parameter<double>("start_delay_s", 20.0);
    arrival_radius_m_ =
        this->declare_parameter<double>("arrival_radius_m", 3.0);

    const auto cmd_topic = this->declare_parameter<std::string>(
        "cmd_vel_topic", "/model/intruder/cmd_vel");

    // Unit ingress direction and total distance, computed once.
    const double dx = target_x_ - ingress_x_;
    const double dy = target_y_ - ingress_y_;
    const double dz = target_z_ - ingress_z_;
    total_dist_ = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (total_dist_ > 1e-6) {
      ux_ = dx / total_dist_;
      uy_ = dy / total_dist_;
      uz_ = dz / total_dist_;
    }

    // Dead-reckoned position starts at the spawn point.
    dr_x_ = ingress_x_;
    dr_y_ = ingress_y_;
    dr_z_ = ingress_z_;

    cmd_pub_ = this->create_publisher<geometry_msgs::msg::Twist>(cmd_topic,
                                                                 QUEUE_SIZE);
    truth_pub_ = this->create_publisher<geometry_msgs::msg::PoseStamped>(
        "intruder/ground_truth", QUEUE_SIZE);
    active_pub_ = this->create_publisher<std_msgs::msg::Bool>("intruder/active",
                                                              QUEUE_SIZE);
    transmitting_pub_ = this->create_publisher<std_msgs::msg::Bool>(
        "intruder/transmitting", QUEUE_SIZE);

    // The timer runs on the node clock, which is simulated time: it ticks
    // PUBLISH_RATE_HZ times per simulated second, whatever the real-time
    // factor. The start time is taken at the first tick (see step()).
    timer_ = rclcpp::create_timer(
        this, this->get_clock(),
        rclcpp::Duration::from_seconds(1.0 / PUBLISH_RATE_HZ),
        [this]() { step(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "IntruderNode initialized (open-loop)");
    RCLCPP_INFO(this->get_logger(), "  ingress : (%.1f, %.1f, %.1f)",
                ingress_x_, ingress_y_, ingress_z_);
    RCLCPP_INFO(this->get_logger(), "  target  : (%.1f, %.1f, %.1f)", target_x_,
                target_y_, target_z_);
    RCLCPP_INFO(this->get_logger(), "  distance: %.1f m at %.1f m/s",
                total_dist_, speed_mps_);
    RCLCPP_INFO(this->get_logger(), "  start in: %.0f s", start_delay_s_);
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  enum class Phase { Idle, Ingress, Arrived };

  /** @brief Timer tick: advances the phase state machine and publishes truth.
   */
  void step() {
    const rclcpp::Time now = this->now();
    // Before the first /clock message the simulated time reads zero, so the
    // start time is taken at the first tick with a valid clock. Taken in the
    // constructor, it would make the whole start delay look already elapsed.
    if (!started_) {
      if (now.nanoseconds() == 0) return;
      start_time_ = now;
      last_step_ = now;
      started_ = true;
    }
    const double elapsed = (now - start_time_).seconds();
    const double dt = (now - last_step_).seconds();
    last_step_ = now;

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
        publish_velocity(ux_ * speed_mps_, uy_ * speed_mps_, uz_ * speed_mps_);

        // Dead reckoning: integrate the commanded velocity. Independent of any
        // Gazebo feedback, so the run always completes.
        dr_x_ += ux_ * speed_mps_ * dt;
        dr_y_ += uy_ * speed_mps_ * dt;
        dr_z_ += uz_ * speed_mps_ * dt;
        travelled_ += speed_mps_ * dt;

        if (travelled_ >= total_dist_ - arrival_radius_m_) {
          phase_ = Phase::Arrived;
          publish_velocity(0.0, 0.0, 0.0);
          RCLCPP_WARN(this->get_logger(),
                      "Target point reached near (%.1f, %.1f, %.1f)", dr_x_,
                      dr_y_, dr_z_);
        }
        break;
      }

      case Phase::Arrived:
        publish_velocity(0.0, 0.0, 0.0);
        break;
    }

    publish_ground_truth();
  }

  /**
   * @brief Publishes the commanded velocity plus the active/transmitting flags.
   * @param vx,vy,vz  Commanded linear velocity, world ENU (m/s).
   */
  void publish_velocity(double vx, double vy, double vz) {
    geometry_msgs::msg::Twist cmd;
    cmd.linear.x = vx;
    cmd.linear.y = vy;
    cmd.linear.z = vz;
    cmd_pub_->publish(cmd);

    std_msgs::msg::Bool active;
    active.data = (phase_ == Phase::Ingress);
    active_pub_->publish(active);

    std_msgs::msg::Bool tx;
    tx.data = transmitting_;
    transmitting_pub_->publish(tx);
  }

  /** @brief Publishes the dead-reckoned position as the ground truth. */
  void publish_ground_truth() {
    geometry_msgs::msg::PoseStamped truth;
    truth.header.stamp = this->now();
    truth.header.frame_id = "world";
    truth.pose.position.x = dr_x_;
    truth.pose.position.y = dr_y_;
    truth.pose.position.z = dr_z_;
    truth.pose.orientation.w = 1.0;
    truth_pub_->publish(truth);
  }

  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr cmd_pub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr truth_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr active_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr transmitting_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  rclcpp::Time start_time_, last_step_;
  bool started_ = false;  // start_time_ is taken at the first valid tick
  Phase phase_ = Phase::Idle;

  double ingress_x_, ingress_y_, ingress_z_;
  double target_x_, target_y_, target_z_;
  double speed_mps_, start_delay_s_, arrival_radius_m_;
  bool transmitting_ = true;

  double ux_ = 0.0, uy_ = 0.0, uz_ = 0.0, total_dist_ = 0.0;
  double dr_x_ = 0.0, dr_y_ = 0.0, dr_z_ = 0.0, travelled_ = 0.0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<IntruderNode>());
  rclcpp::shutdown();
  return 0;
}
