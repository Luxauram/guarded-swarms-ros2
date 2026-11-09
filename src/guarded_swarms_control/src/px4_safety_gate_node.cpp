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
 * @file px4_safety_gate_node.cpp
 *
 * @brief Independent command gate on a UAV's trajectory-setpoint path.
 *
 * Sits between the UAV worker and PX4: the worker publishes its setpoint to
 * trajectory_setpoint_proposed, this node forwards it to
 * fmu/in/trajectory_setpoint, and PX4 sees only what passes the gate. With
 * veto_by=gate it holds the UAV's position whenever the vehicle's Safety Board
 * reports unsafe, so a worker that ignores the board cannot drive the UAV past
 * the analogue safety layer. The gate reads the board's own safety_status flag
 * (published on a timer, independent of the worker's command), not the
 * worker's actuator_cmd_safe.
 *
 * It does not touch offboard_control_mode or vehicle_command, which the worker
 * still publishes directly: the gate acts only on the position setpoint, the
 * same level the Safety Board acts on.
 *
 * veto_by:
 *   worker  (default)  Forward every setpoint unchanged; the worker honours
 *                      the veto itself. The gate is transparent, so a nominal
 *                      run is unchanged.
 *   gate               Hold position while the board is unsafe, forward
 *                      otherwise. The hold begins only once airborne, that
 *                      is TAKEOFF_ALTITUDE_M up: on the ground the board is
 *                      unsafe (stale sensors, altitude floor), and holding
 *                      there would prevent take-off, so a ground veto is never
 *                      carried into flight. It resumes when the board is safe
 *                      again, after a minimum hold, so it does not chatter.
 *                      If safety_status stops arriving, the gate holds.
 *
 * Topics (relative, so each UAV namespace gets its own gate):
 *   Subscribed:
 *     trajectory_setpoint_proposed       (px4_msgs/TrajectorySetpoint)
 *     safety_status                       (std_msgs/Float32)
 *     fmu/out/vehicle_local_position_v1   (px4_msgs/VehicleLocalPosition)
 *   Published:
 *     fmu/in/trajectory_setpoint          (px4_msgs/TrajectorySetpoint)
 *
 * @author Luca D'Aurizio
 */

#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float32.hpp>

#include <cmath>
#include <string>

using px4_msgs::msg::TrajectorySetpoint;
using px4_msgs::msg::VehicleLocalPosition;

class Px4SafetyGateNode : public rclcpp::Node {
 public:
  Px4SafetyGateNode() : Node("px4_safety_gate_node") {
    // "worker" forwards (the worker vetoes); "gate" enforces the veto here.
    veto_by_ = this->declare_parameter<std::string>("veto_by", "worker");
    if (veto_by_ != "worker" && veto_by_ != "gate") {
      RCLCPP_WARN(this->get_logger(),
                  "veto_by='%s' is neither 'worker' nor 'gate'; forwarding.",
                  veto_by_.c_str());
      veto_by_ = "worker";
    }

    setpoint_pub_ = this->create_publisher<TrajectorySetpoint>(
        "fmu/in/trajectory_setpoint", QUEUE_SIZE);

    proposed_sub_ = this->create_subscription<TrajectorySetpoint>(
        "trajectory_setpoint_proposed", QUEUE_SIZE,
        [this](const TrajectorySetpoint::SharedPtr m) { on_proposed(m); });

    status_sub_ = this->create_subscription<std_msgs::msg::Float32>(
        "safety_status", QUEUE_SIZE,
        [this](const std_msgs::msg::Float32::SharedPtr m) {
          last_status_ = m->data;
          last_status_t_ = this->now();
        });

    // The PX4 out topics are BEST_EFFORT; match them, as the other nodes do.
    auto pos_qos = rclcpp::QoS(QUEUE_SIZE)
                       .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                       .durability(rclcpp::DurabilityPolicy::TransientLocal);
    local_pos_sub_ = this->create_subscription<VehicleLocalPosition>(
        "fmu/out/vehicle_local_position_v1", pos_qos,
        [this](const VehicleLocalPosition::SharedPtr m) {
          if (m->xy_valid) {
            cur_north_ = m->x;
            cur_east_ = m->y;
          }
          if (m->z_valid) cur_down_ = m->z;
          cur_valid_ = m->xy_valid && m->z_valid;
          if (-cur_down_ >= TAKEOFF_ALTITUDE_M) airborne_ = true;
        });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "Px4SafetyGateNode (veto_by=%s)",
                veto_by_.c_str());
    RCLCPP_INFO(this->get_logger(),
                "  worker setpoint -> gate -> fmu/in/trajectory_setpoint");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  static constexpr int QUEUE_SIZE = 10;
  // safety_status is 1.0 when safe, 0.0 when unsafe.
  static constexpr float SAFE_THRESHOLD = 0.5f;
  // Hold if no safety_status has arrived for this long: a silent board is not
  // a safe board.
  static constexpr double STATUS_TIMEOUT_S = 0.5;
  // Minimum time a veto is held once it fires, so a board that flickers at the
  // threshold does not make the gate chatter. Matches the worker and rover.
  static constexpr double VETO_MIN_HOLD_S = 2.0;
  // Altitude (metres) above which the UAV counts as airborne and the veto
  // begins to apply. Below it the climb-out is always forwarded. The board's
  // status does not count: a single safe status on the ground would mark the
  // UAV airborne, and the next unsafe one (altitude floor) would hold it on
  // the ground, where the board stays unsafe.
  static constexpr double TAKEOFF_ALTITUDE_M = 3.0;

  /**
   * @brief Forwards or holds each proposed setpoint, per veto_by and the board.
   * @param m The setpoint proposed by the worker.
   */
  void on_proposed(const TrajectorySetpoint::SharedPtr m) {
    // Transparent: the worker honours the veto; forward unchanged.
    if (veto_by_ != "gate") {
      forward(*m);
      return;
    }

    // Until airborne, forward: on the ground the board is unsafe (stale
    // sensors, altitude floor), and a ground veto must not be carried into
    // flight or the UAV would never take off.
    if (!airborne_) {
      vetoed_ = false;
      holding_ = false;
      forward(*m);
      return;
    }

    const rclcpp::Time now = this->now();
    const bool stale = last_status_t_.nanoseconds() == 0 ||
                       (now - last_status_t_).seconds() > STATUS_TIMEOUT_S;
    const bool unsafe = stale || last_status_ < SAFE_THRESHOLD;
    if (unsafe) {
      vetoed_ = true;
      last_unsafe_t_ = now;
    } else if (vetoed_ &&
               (now - last_unsafe_t_).seconds() > VETO_MIN_HOLD_S) {
      vetoed_ = false;
    }

    if (vetoed_) {
      if (!holding_) {
        capture_hold(*m);
        holding_ = true;
      }
      publish_hold();
    } else {
      holding_ = false;
      forward(*m);
    }
  }

  /** @brief Sends the proposed setpoint to PX4 with a fresh timestamp. */
  void forward(const TrajectorySetpoint& m) {
    TrajectorySetpoint out = m;
    out.timestamp = now_us();
    setpoint_pub_->publish(out);
  }

  /** @brief Captures the pose to hold while the board is unsafe. */
  void capture_hold(const TrajectorySetpoint& m) {
    // Hold the real position when known, else the proposed one; keep the
    // proposed heading so the UAV does not yaw while frozen.
    hold_north_ = cur_valid_ ? cur_north_ : m.position[0];
    hold_east_ = cur_valid_ ? cur_east_ : m.position[1];
    hold_down_ = cur_valid_ ? cur_down_ : m.position[2];
    hold_yaw_ = m.yaw;
  }

  /** @brief Publishes the hold setpoint, which keeps the UAV in place. */
  void publish_hold() {
    TrajectorySetpoint out;
    out.timestamp = now_us();
    out.position[0] = static_cast<float>(hold_north_);
    out.position[1] = static_cast<float>(hold_east_);
    out.position[2] = static_cast<float>(hold_down_);
    out.yaw = static_cast<float>(hold_yaw_);
    out.velocity = {NAN, NAN, NAN};
    out.acceleration = {NAN, NAN, NAN};
    out.jerk = {NAN, NAN, NAN};
    out.yawspeed = NAN;
    setpoint_pub_->publish(out);
  }

  /** @brief Current ROS time in microseconds (PX4 timestamp). */
  uint64_t now_us() { return this->get_clock()->now().nanoseconds() / 1000; }

  std::string veto_by_;
  rclcpp::Publisher<TrajectorySetpoint>::SharedPtr setpoint_pub_;
  rclcpp::Subscription<TrajectorySetpoint>::SharedPtr proposed_sub_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr status_sub_;
  rclcpp::Subscription<VehicleLocalPosition>::SharedPtr local_pos_sub_;

  // Board status: last value and when it arrived (stale after STATUS_TIMEOUT_S).
  float last_status_ = 0.0f;
  rclcpp::Time last_status_t_{0, 0, RCL_ROS_TIME};
  bool airborne_ = false;
  bool vetoed_ = false, holding_ = false;
  rclcpp::Time last_unsafe_t_{0, 0, RCL_ROS_TIME};

  double cur_north_ = 0.0, cur_east_ = 0.0, cur_down_ = 0.0;
  bool cur_valid_ = false;
  double hold_north_ = 0.0, hold_east_ = 0.0, hold_down_ = -5.0;
  double hold_yaw_ = 0.0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Px4SafetyGateNode>());
  rclcpp::shutdown();
  return 0;
}