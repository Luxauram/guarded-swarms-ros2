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
 * @file ugv_worker_node.cpp
 *
 * @brief UGV worker agent (Figure 4, T9): task -> observation move.
 *
 * The UGV worker agent of the coastal case study in Borghoff, Bottoni and
 * Pareschi (2026), IET Radar, Sonar and Navigation, Section 5.2. The paper
 * pairs the aerial interception with a ground vehicle for "observation and
 * target recovery", and describes a UGV worker as generating "navigation or
 * observation commands". This node is the UGV counterpart of the UAV worker:
 * the single controller of the rover, absorbing the patrol behaviour and
 * adding task handling.
 *
 * BEHAVIOUR
 * =========
 *   - Default: patrol the shore road between its waypoints, exactly the
 *     previous rover_control_node behaviour, veto included.
 *   - On a VehicleTask of kind ugv for this vehicle's system id: move to an
 *     OBSERVATION POINT and hold there, watching the target.
 *
 * WHERE THE ROVER GOES (an implementation choice, declared)
 * =========================================================
 * The target is over the water; the rover cannot leave the shore road. So the
 * observation point is the point ON the patrol line nearest the target: the
 * rover keeps its patrol north coordinate (the road) and takes the target's
 * east, i.e. it slides along the shore to sit abreast of the target and
 * observe it from land. This is a stand-off observation, not a pursuit.
 *
 *   observe_north = patrol_north            (stay on the road)
 *   observe_east  = target_enu_x - spawn_x  (abreast of the target)
 *
 * The east is clamped to the patrol span so a task never drives the rover off
 * the mapped road.
 *
 * THE VETO STILL GATES MOTION
 * ===========================
 * As in patrol, an active veto stops the rover with a zero throttle setpoint,
 * whatever the task. The worker translates and commands; the analogue board
 * still has the final say at the actuator, unchanged.
 *
 * Topics:
 *   Subscribed:
 *     /vehicle_tasks                     (guarded_swarms_msgs/VehicleTask)
 *     fmu/out/vehicle_local_position_v1  (px4_msgs/VehicleLocalPosition)
 *     actuator_cmd_safe                  (std_msgs/Float32)  the veto verdict
 *   Published:
 *     fmu/in/rover_position_setpoint     (px4_msgs/RoverPositionSetpoint)
 *     fmu/in/rover_throttle_setpoint     (px4_msgs/RoverThrottleSetpoint)
 *     fmu/in/vehicle_command             (px4_msgs/VehicleCommand)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/rover_position_setpoint.hpp>
#include <px4_msgs/msg/rover_throttle_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <std_msgs/msg/float32.hpp>

#include <guarded_swarms_msgs/msg/vehicle_task.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <vector>

using namespace std::chrono_literals;
using guarded_swarms_msgs::msg::VehicleTask;

class UgvWorkerNode : public rclcpp::Node {
 public:
  UgvWorkerNode() : Node("ugv_worker_node") {
    target_system_ = static_cast<uint8_t>(
        this->declare_parameter<int>("target_system", 3));

    spawn_x_ = this->declare_parameter<double>("spawn_x", 0.0);
    spawn_y_ = this->declare_parameter<double>("spawn_y", 0.0);

    const auto flat = this->declare_parameter<std::vector<double>>(
        "waypoints", std::vector<double>{0.0, 0.0, 0.0, 46.0});
    if (flat.size() >= 4 && flat.size() % 2 == 0) {
      for (size_t i = 0; i + 1 < flat.size(); i += 2)
        waypoints_.push_back({static_cast<float>(flat[i]),
                              static_cast<float>(flat[i + 1])});
    } else {
      waypoints_ = {{0.0f, 0.0f}, {0.0f, 46.0f}};
    }

    auto qos = rclcpp::QoS(10)
                   .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                   .durability(rclcpp::DurabilityPolicy::TransientLocal);

    pos_pub_ = this->create_publisher<px4_msgs::msg::RoverPositionSetpoint>(
        "fmu/in/rover_position_setpoint", 10);
    throttle_pub_ = this->create_publisher<px4_msgs::msg::RoverThrottleSetpoint>(
        "fmu/in/rover_throttle_setpoint", 10);
    cmd_pub_ = this->create_publisher<px4_msgs::msg::VehicleCommand>(
        "fmu/in/vehicle_command", 10);
    // Proposed-actuation channel into this vehicle's analog Safety Board
    // (relative topic: stays within the vehicle namespace). The board answers
    // on actuator_cmd_safe.
    cmd_raw_pub_ = this->create_publisher<std_msgs::msg::Float32>(
        "actuator_cmd_raw", 10);

    pos_sub_ = this->create_subscription<px4_msgs::msg::VehicleLocalPosition>(
        "fmu/out/vehicle_local_position_v1", qos,
        [this](const px4_msgs::msg::VehicleLocalPosition::SharedPtr m) {
          north_ = m->x;
          east_ = m->y;
          pos_valid_ = true;
        });

    veto_sub_ = this->create_subscription<std_msgs::msg::Float32>(
        "actuator_cmd_safe", 10,
        [this](const std_msgs::msg::Float32::SharedPtr m) {
          if (m->data < 0.01f) {
            vetoed_ = true;
            last_veto_ = this->now();
          } else if (vetoed_ &&
                     (this->now() - last_veto_).seconds() > VETO_MIN_HOLD_S) {
            vetoed_ = false;
          }
        });

    task_sub_ = this->create_subscription<VehicleTask>(
        "/vehicle_tasks", 10,
        [this](const VehicleTask::SharedPtr m) { on_task(m); });

    timer_ = this->create_wall_timer(std::chrono::duration<double>(0.1),
                                     [this]() { control_loop(); });
    start_time_ = this->now();

    // Patrol span along east, for clamping an observation point to the road.
    east_min_ = std::numeric_limits<float>::max();
    east_max_ = std::numeric_limits<float>::lowest();
    for (const auto& wp : waypoints_) {
      east_min_ = std::min(east_min_, wp[1]);
      east_max_ = std::max(east_max_, wp[1]);
    }
    patrol_north_ = waypoints_.empty() ? 0.0f : waypoints_.front()[0];

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "UgvWorkerNode (TB-CSPN T9)");
    RCLCPP_INFO(this->get_logger(), "  system %u, spawn (%.0f, %.0f)",
                target_system_, spawn_x_, spawn_y_);
    RCLCPP_INFO(this->get_logger(),
                "  patrol north %.1f, east span [%.1f, %.1f]", patrol_north_,
                east_min_, east_max_);
    RCLCPP_INFO(this->get_logger(),
                "  patrolling until an observe task arrives");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  static constexpr float WAYPOINT_RADIUS_M = 0.8f;
  static constexpr float CRUISING_SPEED_MS = 1.0f;
  static constexpr float ARRIVAL_SPEED_MS = 0.3f;
  static constexpr double ARM_DELAY_S = 5.0;
  static constexpr double VETO_GIVEUP_S = 6.0;
  static constexpr double VETO_MIN_HOLD_S = 2.0;

  void on_task(const VehicleTask::SharedPtr m) {
    if (m->vehicle_kind != VehicleTask::KIND_UGV) return;
    if (m->assigned_system != target_system_) return;

    // Observation point: stay on the road (patrol north), slide east to sit
    // abreast of the target, clamped to the patrol span so we never leave the
    // mapped road.
    float obs_east = static_cast<float>(m->target_position.x - spawn_x_);
    obs_east = std::clamp(obs_east, east_min_, east_max_);

    observe_point_ = {patrol_north_, obs_east};
    has_task_ = true;

    RCLCPP_WARN(this->get_logger(),
                "Task '%s' (%s): observing from NED (%.1f, %.1f)",
                m->task_id.c_str(), m->task_type.c_str(), observe_point_[0],
                observe_point_[1]);
  }

  void control_loop() {
    // Propose actuation to the analog Safety Board every cycle. The board
    // gates this against its own sensor envelope and answers on
    // actuator_cmd_safe (honoured in the veto subscription). Publishing
    // unconditionally keeps the board's verdict live even while vetoed, so the
    // board -- not a local timer -- decides when motion may resume.
    std_msgs::msg::Float32 raw;
    raw.data = 1.0f;
    cmd_raw_pub_->publish(raw);

    const double elapsed = (this->now() - start_time_).seconds();

    if (!armed_) {
      if (elapsed > ARM_DELAY_S) {
        arm_rover();
        armed_ = true;
        patrol_active_ = true;
        RCLCPP_INFO(this->get_logger(), "Rover armed.");
      }
      return;
    }
    if (!patrol_active_ || !pos_valid_) return;

    // The veto gates motion in every mode.
    if (vetoed_) {
      publish_stop();
      if (!veto_timing_) {
        veto_timing_ = true;
        veto_start_ = this->now();
      } else if (!has_task_ &&
                 (this->now() - veto_start_).seconds() > VETO_GIVEUP_S) {
        // Only the patrol gives up on a blocked waypoint and reverses. Under a
        // task the rover holds against the veto: the observation point is the
        // goal, not a leg of a loop to be abandoned.
        advance_waypoint();
        veto_timing_ = false;
      }
      return;
    }
    veto_timing_ = false;

    if (has_task_) {
      // Drive to the observation point and hold.
      publish_position(observe_point_);
      if (reached(observe_point_) && !observing_) {
        observing_ = true;
        RCLCPP_INFO(this->get_logger(),
                    "At observation point (%.1f, %.1f), holding.",
                    observe_point_[0], observe_point_[1]);
      }
      return;
    }

    // Default: patrol.
    publish_position(waypoints_[wp_index_]);
    if (reached(waypoints_[wp_index_])) advance_waypoint();
  }

  void advance_waypoint() {
    if (wp_forward_) {
      if (wp_index_ + 1 < waypoints_.size()) {
        wp_index_++;
      } else {
        wp_forward_ = false;
        if (wp_index_ > 0) wp_index_--;
      }
    } else {
      if (wp_index_ > 0) {
        wp_index_--;
      } else {
        wp_forward_ = true;
        if (waypoints_.size() > 1) wp_index_++;
      }
    }
  }

  bool reached(const std::array<float, 2>& wp) const {
    const float dn = north_ - wp[0];
    const float de = east_ - wp[1];
    return std::sqrt(dn * dn + de * de) < WAYPOINT_RADIUS_M;
  }

  void publish_position(const std::array<float, 2>& wp) {
    px4_msgs::msg::RoverPositionSetpoint msg;
    msg.timestamp = this->now().nanoseconds() / 1000;
    msg.position_ned[0] = wp[0];
    msg.position_ned[1] = wp[1];
    msg.cruising_speed = CRUISING_SPEED_MS;
    msg.arrival_speed = ARRIVAL_SPEED_MS;
    msg.yaw = std::numeric_limits<float>::quiet_NaN();
    msg.start_ned[0] = std::numeric_limits<float>::quiet_NaN();
    msg.start_ned[1] = std::numeric_limits<float>::quiet_NaN();
    pos_pub_->publish(msg);
  }

  void publish_stop() {
    px4_msgs::msg::RoverThrottleSetpoint msg;
    msg.timestamp = this->now().nanoseconds() / 1000;
    msg.throttle_body_x = 0.0f;
    msg.throttle_body_y = 0.0f;
    throttle_pub_->publish(msg);
  }

  void arm_rover() {
    px4_msgs::msg::VehicleCommand cmd;
    cmd.timestamp = this->now().nanoseconds() / 1000;
    cmd.command =
        px4_msgs::msg::VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM;
    cmd.param1 = 1.0f;
    cmd.param2 = 21196.0f;
    cmd.target_system = target_system_;
    cmd.target_component = 1;
    cmd.source_system = target_system_;
    cmd.source_component = 1;
    cmd.from_external = true;
    cmd_pub_->publish(cmd);
  }

  rclcpp::Publisher<px4_msgs::msg::RoverPositionSetpoint>::SharedPtr pos_pub_;
  rclcpp::Publisher<px4_msgs::msg::RoverThrottleSetpoint>::SharedPtr throttle_pub_;
  rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr cmd_pub_;
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr cmd_raw_pub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr pos_sub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr veto_sub_;
  rclcpp::Subscription<VehicleTask>::SharedPtr task_sub_;
  rclcpp::TimerBase::SharedPtr timer_;

  uint8_t target_system_ = 3;
  double spawn_x_ = 0.0, spawn_y_ = 0.0;
  std::vector<std::array<float, 2>> waypoints_;
  float east_min_ = 0.0f, east_max_ = 0.0f, patrol_north_ = 0.0f;

  rclcpp::Time start_time_, veto_start_, last_veto_;
  bool armed_ = false, patrol_active_ = false;
  bool vetoed_ = false, veto_timing_ = false;
  size_t wp_index_ = 0;
  bool wp_forward_ = true;

  float north_ = 0.0f, east_ = 0.0f;
  bool pos_valid_ = false;

  bool has_task_ = false, observing_ = false;
  std::array<float, 2> observe_point_ = {0.0f, 0.0f};
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<UgvWorkerNode>());
  rclcpp::shutdown();
  return 0;
}
