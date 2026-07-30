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
 * @file uav_worker_node.cpp
 *
 * @brief UAV worker agent (Figure 4, T8): task -> interception trajectory.
 *
 * The UAV worker agent of the coastal case study in Borghoff, Bottoni and
 * Pareschi (2026), IET Radar, Sonar and Navigation, Section 5.2. It is the
 * translation bridge across the digital-physical boundary: it consumes a
 * VehicleTask and turns it into platform control, which the paper describes as
 * converting "the mission directive into trajectory waypoints or interception
 * manoeuvres".
 *
 * WHY THE WORKER IS ALSO THE CONTROLLER
 * =====================================
 * This node is the single point of command for its UAV. It absorbs the offboard
 * control that a separate node used to do (arm, offboard mode, hover) and adds
 * task handling on top. Having one node command the vehicle avoids two
 * publishers racing on the same TrajectorySetpoint, and gives the analogue veto
 * a single command source to gate. This matches the paper's separation: the
 * worker agent translates and commands, the executor platform (PX4) only
 * executes deterministically.
 *
 * BEHAVIOUR
 * =========
 *   - On startup: arm, enter offboard, hold hover at hover_altitude (exactly
 *     the previous offboard_control_node behaviour).
 *   - On a VehicleTask of kind uav addressed to this vehicle's system id: fly
 *     to the target's horizontal position, holding an interception altitude of
 *     its own (intercept_altitude), so it does not descend onto the target.
 *     This is a stand-off interception trajectory in the sense of the paper.
 *   - The task's target_position is in world ENU (Gazebo). PX4 wants NED local,
 *     relative to the vehicle's spawn pose, so it is converted here -- the
 *     inverse of the NED->ENU the sensing agents apply.
 *
 * FRAME CONVERSION
 * ================
 *   world ENU -> local ENU:  subtract the spawn pose (spawn_x, spawn_y)
 *   local ENU -> NED:        north = local_y, east = local_x, down = -up
 * so:
 *   ned_north = target_enu_y - spawn_y
 *   ned_east  = target_enu_x - spawn_x
 *
 * Topics:
 *   Subscribed:
 *     /vehicle_tasks               (guarded_swarms_msgs/VehicleTask)
 *     /interp_tokens               (guarded_swarms_msgs/InterpToken)
 *     fmu/out/vehicle_status_v1    (px4_msgs/VehicleStatus)
 *   Published:
 *     fmu/in/offboard_control_mode (px4_msgs/OffboardControlMode)
 *     fmu/in/trajectory_setpoint   (px4_msgs/TrajectorySetpoint)
 *     fmu/in/vehicle_command       (px4_msgs/VehicleCommand)
 *
 * @author Luca D'Aurizio
 */

#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float32.hpp>

#include <guarded_swarms_msgs/msg/interp_token.hpp>
#include <guarded_swarms_msgs/msg/vehicle_task.hpp>

#include <chrono>
#include <cmath>
#include <string>

using namespace std::chrono_literals;
using guarded_swarms_msgs::msg::InterpToken;
using guarded_swarms_msgs::msg::VehicleTask;

class UavWorkerNode : public rclcpp::Node {
 public:
  UavWorkerNode() : Node("uav_worker_node") {
    target_system_ = static_cast<uint8_t>(
        this->declare_parameter<int>("target_system", 1));
    hover_altitude_m_ = this->declare_parameter<double>("hover_altitude", 5.0);
    // Altitude held during interception, so the UAV closes on the target's
    // horizontal position without descending onto it.
    intercept_altitude_m_ =
        this->declare_parameter<double>("intercept_altitude", 15.0);

    // Vehicle spawn pose in world ENU, for the ENU->NED conversion of the
    // target position. Same values the dispatch and EO nodes use.
    spawn_x_ = this->declare_parameter<double>("spawn_x", -24.0);
    spawn_y_ = this->declare_parameter<double>("spawn_y", -24.0);

    offboard_mode_pub_ =
        this->create_publisher<px4_msgs::msg::OffboardControlMode>(
            "fmu/in/offboard_control_mode", QUEUE_SIZE);
    setpoint_pub_ =
        this->create_publisher<px4_msgs::msg::TrajectorySetpoint>(
            "fmu/in/trajectory_setpoint", QUEUE_SIZE);
    command_pub_ = this->create_publisher<px4_msgs::msg::VehicleCommand>(
        "fmu/in/vehicle_command", QUEUE_SIZE);

    auto status_qos = rclcpp::QoS(QUEUE_SIZE)
                          .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                          .durability(rclcpp::DurabilityPolicy::TransientLocal);
    status_sub_ = this->create_subscription<px4_msgs::msg::VehicleStatus>(
        "fmu/out/vehicle_status_v1", status_qos,
        [this](const px4_msgs::msg::VehicleStatus::SharedPtr msg) {
          armed_ = (msg->arming_state ==
                    px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED);
        });

    // Tasks are swarm-wide; this worker filters by kind and system id.
    task_sub_ = this->create_subscription<VehicleTask>(
        "/vehicle_tasks", 10,
        [this](const VehicleTask::SharedPtr m) { on_task(m); });

    // Track-lock: once a task has designated a target, follow the system's
    // latest threat estimate for it. The worker acts on what the sensors
    // report (a ConfirmedThreat's position), not on ground truth -- it does
    // not know where the intruder truly is, only what the TB-CSPN layer
    // believes. This mirrors a real interceptor following its own sensor lock.
    threat_sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", 50,
        [this](const InterpToken::SharedPtr m) { on_threat(m); });
    // The analogue safety board publishes its verdict here, per vehicle
    // (relative topic, namespaced per UAV). This worker is the single command
    // source for its vehicle (see file header), so it is where the board's
    // verdict is honoured -- exactly as rover_control_node does for the UGV.
    // A multirotor cannot be stopped by zeroing throttle (it would fall); the
    // aerial equivalent of the rover's zero-throttle stop is a position hold,
    // implemented in publish_setpoint() by freezing the last commanded setpoint.
    // The board's independence is unchanged: it decides, the worker obeys. The
    // physical PWM-level cut the paper describes lives inside PX4/hardware and
    // is not reachable from SITL -- the same limitation as the rover.
    veto_sub_ = this->create_subscription<std_msgs::msg::Float32>(
        "actuator_cmd_safe", 10,
        [this](const std_msgs::msg::Float32::SharedPtr msg) {
          if (msg->data < 0.01f) {
            vetoed_ = true;
            last_veto_ = this->now();
          } else if (vetoed_ &&
                     (this->now() - last_veto_).seconds() > VETO_MIN_HOLD_S) {
            vetoed_ = false;
          }
        });

    timer_ = this->create_wall_timer(
        TIMER_PERIOD, [this]() { control_loop(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "UavWorkerNode (TB-CSPN T8)");
    RCLCPP_INFO(this->get_logger(), "  system %u, spawn (%.0f, %.0f)",
                target_system_, spawn_x_, spawn_y_);
    RCLCPP_INFO(this->get_logger(),
                "  hover %.1f m; intercept altitude %.1f m", hover_altitude_m_,
                intercept_altitude_m_);
    RCLCPP_INFO(this->get_logger(), "  holding hover until a task arrives");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  static constexpr int QUEUE_SIZE = 10;
  static constexpr std::chrono::milliseconds TIMER_PERIOD{100};  // 10 Hz
  static constexpr double TIMER_FREQUENCY_HZ = 10.0;
  static constexpr double ARMING_DELAY_S = 5.0;
  static constexpr int ARMING_THRESHOLD =
      static_cast<int>(ARMING_DELAY_S * TIMER_FREQUENCY_HZ);
  static constexpr int ARMING_RETRY_CYCLES = 20;  // 2 s at 10 Hz

  static constexpr uint16_t CMD_SET_MODE = 176;
  static constexpr uint16_t CMD_ARM_DISARM = 400;
  static constexpr float MAIN_MODE = 1.0f;
  static constexpr float SUB_MODE_OFFBOARD = 6.0f;
  static constexpr float ARM = 1.0f;
  static constexpr float FORCE_ARM = 21196.0f;
  static constexpr uint8_t COMPONENT_ID = 1;
  // Minimum time a veto is honoured once it fires, matching the rover. Without
  // it the UAV holds, the hazard leaves the board's window, the veto clears,
  // the UAV moves back in, and it chatters. Same value as rover_control_node.
  static constexpr double VETO_MIN_HOLD_S = 2.0;
  void on_task(const VehicleTask::SharedPtr m) {
    if (m->vehicle_kind != VehicleTask::KIND_UAV) return;
    if (m->assigned_system != target_system_) return;

    // Lock onto the designated target. The task's target_position is the
    // estimate at dispatch time; adopt it as the first goal, then keep
    // following the target's threat estimate as it updates (see on_threat).
    locked_target_ = m->target_id;
    set_goal_from_enu(m->target_position.x, m->target_position.y);
    has_task_ = true;

    RCLCPP_WARN(this->get_logger(),
                "Task '%s' (%s): locked on '%s', flying to NED (%.1f, %.1f) "
                "at %.1f m",
                m->task_id.c_str(), m->task_type.c_str(),
                locked_target_.c_str(), task_north_, task_east_,
                intercept_altitude_m_);
  }

  void on_threat(const InterpToken::SharedPtr m) {
    // Only follow updates once locked, and only for the designated target.
    if (!has_task_ || m->target_id != locked_target_) return;
    if (m->label != InterpToken::LABEL_CONFIRMED_THREAT) return;

    // Update the interception goal to the latest sensor estimate of the
    // target's position. Stand-off altitude is held separately, so the UAV
    // tracks the target horizontally without descending onto it.
    set_goal_from_enu(m->position.x, m->position.y);
  }

  // Convert a world-ENU (x_east, y_north) point to this vehicle's NED local
  // frame and store it as the horizontal goal.
  void set_goal_from_enu(double enu_x, double enu_y) {
    task_north_ = enu_y - spawn_y_;
    task_east_ = enu_x - spawn_x_;
  }

  void control_loop() {
    publish_offboard_mode();
    publish_setpoint();

    const int counter = static_cast<int>(counter_);
    if (!armed_ && counter >= ARMING_THRESHOLD &&
        (counter - ARMING_THRESHOLD) % ARMING_RETRY_CYCLES == 0) {
      publish_command(CMD_SET_MODE, MAIN_MODE, SUB_MODE_OFFBOARD);
      publish_command(CMD_ARM_DISARM, ARM, FORCE_ARM);
    }
    if (armed_ && !arm_confirmed_) {
      arm_confirmed_ = true;
      RCLCPP_INFO(this->get_logger(), "PX4 reports ARMED. Holding hover.");
    }
    counter_++;
  }

  void publish_offboard_mode() {
    px4_msgs::msg::OffboardControlMode msg;
    msg.timestamp = now_us();
    msg.position = true;
    offboard_mode_pub_->publish(msg);
  }

  void publish_setpoint() {
    px4_msgs::msg::TrajectorySetpoint msg;
    msg.timestamp = now_us();
    if (vetoed_) {
      // Under veto: hold position. Re-publish the last commanded setpoint so
      // the UAV freezes where it was rather than advancing toward its goal --
      // the aerial equivalent of the rover's zero-throttle stop. The board has
      // inhibited motion; the worker does not compute a new goal until the veto
      // lifts.
      msg.position[0] = static_cast<float>(last_north_);
      msg.position[1] = static_cast<float>(last_east_);
      msg.position[2] = static_cast<float>(last_down_);
    } else {
      if (has_task_) {
        msg.position[0] = static_cast<float>(task_north_);
        msg.position[1] = static_cast<float>(task_east_);
        msg.position[2] = static_cast<float>(-intercept_altitude_m_);
      } else {
        // Default: hold hover over the spawn point.
        msg.position[0] = 0.0f;
        msg.position[1] = 0.0f;
        msg.position[2] = static_cast<float>(-hover_altitude_m_);
      }
      // Remember what we commanded, so a veto on the next tick can freeze it.
      last_north_ = msg.position[0];
      last_east_ = msg.position[1];
      last_down_ = msg.position[2];
    }
    msg.yaw = 0.0f;
    msg.velocity = {NAN, NAN, NAN};
    msg.acceleration = {NAN, NAN, NAN};
    msg.jerk = {NAN, NAN, NAN};
    msg.yawspeed = NAN;
    setpoint_pub_->publish(msg);
  }

  void publish_command(uint16_t command, float p1, float p2) {
    px4_msgs::msg::VehicleCommand msg;
    msg.timestamp = now_us();
    msg.command = command;
    msg.param1 = p1;
    msg.param2 = p2;
    msg.target_system = target_system_;
    msg.target_component = COMPONENT_ID;
    msg.source_system = target_system_;
    msg.source_component = COMPONENT_ID;
    msg.from_external = true;
    command_pub_->publish(msg);
  }

  uint64_t now_us() { return this->get_clock()->now().nanoseconds() / 1000; }

  rclcpp::Publisher<px4_msgs::msg::OffboardControlMode>::SharedPtr
      offboard_mode_pub_;
  rclcpp::Publisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr setpoint_pub_;
  rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr command_pub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr status_sub_;
  rclcpp::Subscription<VehicleTask>::SharedPtr task_sub_;
  rclcpp::TimerBase::SharedPtr timer_;

  uint8_t target_system_ = 1;
  double hover_altitude_m_ = 5.0;
  double intercept_altitude_m_ = 15.0;
  double spawn_x_ = -24.0, spawn_y_ = -24.0;

  uint64_t counter_ = 0;
  bool armed_ = false;
  bool arm_confirmed_ = false;

  rclcpp::Subscription<InterpToken>::SharedPtr threat_sub_;

  bool has_task_ = false;
  std::string locked_target_;
  double task_north_ = 0.0, task_east_ = 0.0;
  // Analogue safety board veto (honoured as in rover_control_node).
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr veto_sub_;
  bool vetoed_ = false;
  rclcpp::Time last_veto_;
  // Last commanded setpoint, frozen under veto to hold position.
  double last_north_ = 0.0, last_east_ = 0.0, last_down_ = -5.0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<UavWorkerNode>());
  rclcpp::shutdown();
  return 0;
}