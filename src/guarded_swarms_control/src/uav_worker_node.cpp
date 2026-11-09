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
 *   - Every transit, to a task goal and back to the hover point, is flown at
 *     a bounded speed (APPROACH_SPEED_MPS, in simulated time), so the Safety
 *     Board's proximity veto can brake the UAV in time.
 *   - While its goal is more than a few metres away the UAV faces it, so the
 *     single-ray forward lidar of its Safety Board looks where it is going.
 *     Near a task goal it keeps its heading; in hover over the spawn point it
 *     faces north.
 *   - Under a Safety Board veto, once airborne, it holds the position and
 *     heading it has when the veto begins (see publish_setpoint()).
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
 *     /vehicle_tasks                     (guarded_swarms_msgs/VehicleTask)
 *     /interp_tokens                     (guarded_swarms_msgs/InterpToken)
 *     fmu/out/vehicle_status_v1          (px4_msgs/VehicleStatus)
 *     fmu/out/vehicle_local_position_v1  (px4_msgs/VehicleLocalPosition)
 *     actuator_cmd_safe                  (std_msgs/Float32)
 *   Published:
 *     fmu/in/offboard_control_mode       (px4_msgs/OffboardControlMode)
 *     <setpoint_topic>                   (px4_msgs/TrajectorySetpoint)
 *     fmu/in/vehicle_command             (px4_msgs/VehicleCommand)
 *     actuator_cmd_raw                   (std_msgs/Float32)
 *
 * @author Luca D'Aurizio
 */

#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
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
    // The setpoint goes to PX4 directly by default; in the coastal scenario it
    // is routed to the safety gate (px4_safety_gate_node), which forwards it to
    // fmu/in/trajectory_setpoint, so a separate node can hold the UAV even when
    // this worker is bypassed. A parameter, so other launches are unchanged.
    setpoint_pub_ = this->create_publisher<px4_msgs::msg::TrajectorySetpoint>(
        this->declare_parameter<std::string>("setpoint_topic",
                                              "fmu/in/trajectory_setpoint"),
        QUEUE_SIZE);
    // Proposed-actuation channel into this vehicle's analog Safety Board
    // (relative topic: stays within the vehicle namespace). The board answers
    // on actuator_cmd_safe.
    cmd_raw_pub_ =
        this->create_publisher<std_msgs::msg::Float32>(
            "actuator_cmd_raw", QUEUE_SIZE);
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

    // Current position, so a veto holds the UAV where it actually is rather
    // than re-sending the last goal setpoint (which would keep it flying to
    // the goal). The PX4 out topics use the same BEST_EFFORT QoS.
    local_pos_sub_ =
        this->create_subscription<px4_msgs::msg::VehicleLocalPosition>(
            "fmu/out/vehicle_local_position_v1", status_qos,
            [this](const px4_msgs::msg::VehicleLocalPosition::SharedPtr m) {
              if (m->xy_valid) {
                cur_north_ = m->x;
                cur_east_ = m->y;
              }
              if (m->z_valid) cur_down_ = m->z;
              cur_valid_ = m->xy_valid && m->z_valid;
              update_airborne();
            });

    // Tasks are swarm-wide; this worker filters by kind and system id.
    task_sub_ = this->create_subscription<VehicleTask>(
        "/vehicle_tasks", QUEUE_SIZE,
        [this](const VehicleTask::SharedPtr m) { on_task(m); });

    // Track-lock: once a task has designated a target, follow the system's
    // latest threat estimate for it. The worker acts on what the sensors
    // report (a ConfirmedThreat's position), not on ground truth -- it does
    // not know where the intruder truly is, only what the TB-CSPN layer
    // believes. This mirrors a real interceptor following its own sensor lock.
    threat_sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", THREAT_QUEUE_SIZE,
        [this](const InterpToken::SharedPtr m) { on_threat(m); });
    // The analogue safety board publishes its verdict here, per vehicle
    // (relative topic, namespaced per UAV). This worker is the single command
    // source for its vehicle (see file header), so it is where the board's
    // verdict is honoured -- exactly as rover_control_node does for the UGV.
    // A multirotor cannot be stopped by zeroing throttle (it would fall); the
    // aerial equivalent of the rover's zero-throttle stop is a position hold,
    // implemented in publish_setpoint() by holding the position the UAV has
    // when the veto begins.
    // The board's independence is unchanged: it decides, the worker obeys. The
    // physical PWM-level cut the paper describes lives inside PX4/hardware and
    // is not reachable from SITL -- the same limitation as the rover.
    veto_sub_ = this->create_subscription<std_msgs::msg::Float32>(
        "actuator_cmd_safe", QUEUE_SIZE,
        [this](const std_msgs::msg::Float32::SharedPtr msg) {
          if (msg->data < VETO_CMD_THRESHOLD) {
            vetoed_ = true;
            last_veto_ = this->now();
          } else {
            // A safe verdict while armed means the climb-out is complete, so
            // the veto may start to apply (see airborne_).
            if (armed_) airborne_ = true;
            if (vetoed_ &&
                (this->now() - last_veto_).seconds() > VETO_MIN_HOLD_S) {
              vetoed_ = false;
            }
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
  // Larger queue for the threat stream: track-lock must not miss ConfirmedThreat
  // updates arriving between control ticks.
  static constexpr int THREAT_QUEUE_SIZE = 50;
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
  // Below this actuator_cmd_safe value the board's verdict counts as a veto.
  static constexpr float VETO_CMD_THRESHOLD = 0.01f;
  // A goal farther than this (metres, horizontal) turns the UAV toward it, so
  // its single forward lidar looks along the direction of travel. Nearer, the
  // heading is kept on a task and is 0 (north) in hover over the spawn point,
  // so the detection phase before a task is unchanged.
  static constexpr double HEADING_MIN_DIST_M = 3.0;
  // Horizontal speed of every transit, in simulated time, bounded so the
  // Safety Board's proximity veto can brake the UAV before an obstacle: at
  // this speed it brakes in ~6 m. Set to PX4's own cruise speed
  // (MPC_XY_CRUISE). At the autopilot's maximum (MPC_XY_VEL_MAX, 12 m/s) it
  // brakes in ~28 m, which would need a proximity threshold of some 30 m,
  // stopping the UAV far from anything ahead, the target included.
  static constexpr double APPROACH_SPEED_MPS = 5.0;
  // Longest step of simulated time the approach point advances by at once, so
  // a stalled simulation does not make it jump ahead.
  static constexpr double APPROACH_MAX_DT_S = 0.5;
  // Altitude, as a fraction of the hover altitude, at which the UAV counts as
  // airborne and the veto begins to apply. Below it the climb-out from the
  // ground -- where every sensor is stale and the altitude is below the floor,
  // so the board vetoes -- is never frozen.
  static constexpr double TAKEOFF_ALTITUDE_FRAC = 0.5;

  /**
   * @brief Locks onto a UAV task addressed to this vehicle and sets the goal.
   * @param m Shared pointer to the received @c VehicleTask.
   */
  void on_task(const VehicleTask::SharedPtr m) {
    if (m->vehicle_kind != VehicleTask::KIND_UAV) return;
    if (m->assigned_system != target_system_) return;

    // Lock onto the designated target. The task's target_position is the
    // estimate at dispatch time; adopt it as the first goal, then keep
    // following the target's threat estimate as it updates (see on_threat).
    locked_target_ = m->target_id;
    set_goal_from_enu(m->target_position.x, m->target_position.y);
    // The approach point starts from where the UAV is (see advance_approach).
    reseed_approach();
    has_task_ = true;
    mission_ttl_s_ = m->ttl_s;
    last_target_update_ = this->now();
    track_active_ = true;

    RCLCPP_WARN(this->get_logger(),
                "Task '%s' (%s): locked on '%s', flying to NED (%.1f, %.1f) "
                "at %.1f m",
                m->task_id.c_str(), m->task_type.c_str(),
                locked_target_.c_str(), task_north_, task_east_,
                intercept_altitude_m_);
  }

  /**
   * @brief Follows the locked target's latest ConfirmedThreat estimate.
   * @param m Shared pointer to the received @c InterpToken.
   */
  void on_threat(const InterpToken::SharedPtr m) {
    // Only follow updates once locked, and only for the designated target.
    if (!has_task_ || m->target_id != locked_target_) return;
    if (m->label != InterpToken::LABEL_CONFIRMED_THREAT) return;

    // Update the interception goal to the latest sensor estimate of the
    // target's position. Stand-off altitude is held separately, so the UAV
    // tracks the target horizontally without descending onto it.
    set_goal_from_enu(m->position.x, m->position.y);
    last_target_update_ = this->now();
    track_active_ = true;
  }
  /**
   * @brief Converts a world-ENU point to this vehicle's NED local frame and
   *        stores it as the horizontal goal.
   * @param enu_x,enu_y  Target position in world ENU (east, north).
   */
  void set_goal_from_enu(double enu_x, double enu_y) {
    task_north_ = enu_y - spawn_y_;
    task_east_ = enu_x - spawn_x_;
  }

  /** @brief Marks the UAV airborne once it has climbed clear of the ground. */
  void update_airborne() {
    if (airborne_ || !armed_) return;
    if (-cur_down_ >= TAKEOFF_ALTITUDE_FRAC * hover_altitude_m_) {
      airborne_ = true;
    }
  }
  /** @brief Main loop: proposes actuation, arms, and publishes the setpoint. */
  void control_loop() {
    // Propose actuation to the analog Safety Board every cycle. The board
    // gates this against its own sensor envelope and answers on
    // actuator_cmd_safe (honoured in the veto subscription). Publishing
    // unconditionally keeps the board's verdict live even while vetoed, so the
    // board -- not a local timer -- decides when motion may resume.
    std_msgs::msg::Float32 raw;
    raw.data = 1.0f;
    cmd_raw_pub_->publish(raw);

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

  /** @brief Publishes the offboard control mode (position control). */
  void publish_offboard_mode() {
    px4_msgs::msg::OffboardControlMode msg;
    msg.timestamp = now_us();
    msg.position = true;
    offboard_mode_pub_->publish(msg);
  }

  /** @brief Publishes the trajectory setpoint, holding position under veto. */
  void publish_setpoint() {
    px4_msgs::msg::TrajectorySetpoint msg;
    msg.timestamp = now_us();
    // The veto applies only once airborne: on the ground the board always
    // vetoes (stale sensors, altitude below the floor), and holding position
    // there would keep the UAV from ever taking off.
    if (vetoed_ && airborne_) {
      // Hold the UAV where it actually is. The position is captured from
      // vehicle_local_position when the veto begins, not taken from the goal
      // setpoint, so the UAV stops instead of flying on to its target -- the
      // aerial equivalent of the rover's zero-throttle stop. The heading is
      // held too, so it does not yaw while frozen.
      if (!holding_) {
        capture_hold_pose();
        holding_ = true;
      }
      msg.position[0] = static_cast<float>(hold_north_);
      msg.position[1] = static_cast<float>(hold_east_);
      msg.position[2] = static_cast<float>(hold_down_);
      msg.yaw = static_cast<float>(hold_yaw_);
    } else {
      // After a veto hold, the approach point restarts from where the UAV
      // stopped.
      if (holding_) reseed_approach();
      holding_ = false;
      // A locked task whose target track has gone stale for longer than the
      // mission TTL is released: the mission expires rather than being flown
      // blind toward a last-known position that may no longer be valid.
      if (has_task_ && track_active_ && mission_ttl_s_ > 0.0 &&
          (this->now() - last_target_update_).seconds() > mission_ttl_s_) {
        has_task_ = false;
        track_active_ = false;
        // The way back to the hover point starts from where the UAV is.
        reseed_approach();
        RCLCPP_WARN(this->get_logger(),
                    "Mission on '%s' expired (no track for %.1fs > ttl %.1fs); "
                    "returning to hover.",
                    locked_target_.c_str(),
                    (this->now() - last_target_update_).seconds(),
                    mission_ttl_s_);
      }
      // Where the UAV is going: its task goal, or its hover point over the
      // spawn point. The setpoint is the approach point, which advances toward
      // it at APPROACH_SPEED_MPS (see advance_approach), so no transit is flown
      // at the autopilot's maximum.
      const double aim_north = has_task_ ? task_north_ : 0.0;
      const double aim_east = has_task_ ? task_east_ : 0.0;
      advance_approach(aim_north, aim_east);
      msg.position[0] = static_cast<float>(approach_north_);
      msg.position[1] = static_cast<float>(approach_east_);
      msg.position[2] = static_cast<float>(
          has_task_ ? -intercept_altitude_m_ : -hover_altitude_m_);
      // Face the goal while it is more than a few metres away (not the nearby
      // approach point), so the single forward lidar looks where the UAV is
      // going. Near a task goal the heading is kept; over the spawn point it
      // is 0 (north), so the detection phase is unchanged.
      double yaw_cmd = has_task_ ? last_yaw_cmd_ : 0.0;
      const double dn = aim_north - cur_north_;
      const double de = aim_east - cur_east_;
      if (cur_valid_ && std::hypot(dn, de) > HEADING_MIN_DIST_M) {
        yaw_cmd = std::atan2(de, dn);
      }
      msg.yaw = static_cast<float>(yaw_cmd);
      last_yaw_cmd_ = yaw_cmd;
    }
    msg.velocity = {NAN, NAN, NAN};
    msg.acceleration = {NAN, NAN, NAN};
    msg.jerk = {NAN, NAN, NAN};
    msg.yawspeed = NAN;
    setpoint_pub_->publish(msg);
  }

  /** @brief Captures the current pose to hold for the duration of a veto. */
  void capture_hold_pose() {
    // Freeze at the real position when available; otherwise keep the previous
    // hold rather than snapping to the origin.
    if (cur_valid_) {
      hold_north_ = cur_north_;
      hold_east_ = cur_east_;
      hold_down_ = cur_down_;
    }
    hold_yaw_ = last_yaw_cmd_;
  }

  /**
   * @brief Moves the approach point toward (aim_north, aim_east) by at most
   *        APPROACH_SPEED_MPS times the simulated time since the last call.
   *
   * The step is measured on the node clock, which is simulated time, rather
   * than counted in ticks of the wall-clock control timer: when the
   * simulation runs slower than real time, a fixed step per tick moves the
   * point faster than APPROACH_SPEED_MPS in simulated time.
   */
  void advance_approach(double aim_north, double aim_east) {
    const rclcpp::Time now = this->now();
    const double dt = std::fmin(
        std::fmax((now - last_approach_t_).seconds(), 0.0), APPROACH_MAX_DT_S);
    last_approach_t_ = now;
    const double step = APPROACH_SPEED_MPS * dt;
    const double gn = aim_north - approach_north_;
    const double ge = aim_east - approach_east_;
    const double g = std::hypot(gn, ge);
    if (g > step) {
      approach_north_ += gn / g * step;
      approach_east_ += ge / g * step;
    } else {
      approach_north_ = aim_north;
      approach_east_ = aim_east;
    }
  }

  /** @brief Restarts the approach point from the UAV's current position. */
  void reseed_approach() {
    if (cur_valid_) {
      approach_north_ = cur_north_;
      approach_east_ = cur_east_;
    }
    last_approach_t_ = this->now();
  }

  /**
   * @brief Sends a vehicle command to PX4.
   * @param command MAVLink command ID.
   * @param p1,p2   Command parameters (command-specific meaning).
   */
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

  /** @brief Returns the current ROS time in microseconds (PX4 timestamp). */
  uint64_t now_us() { return this->get_clock()->now().nanoseconds() / 1000; }

  rclcpp::Publisher<px4_msgs::msg::OffboardControlMode>::SharedPtr
      offboard_mode_pub_;
  rclcpp::Publisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr setpoint_pub_;
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr cmd_raw_pub_;
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
  // Mission validity: TTL from the task, and the time of the last target
  // update (dispatch or latest ConfirmedThreat). When the track is lost, the
  // mission is held for ttl_s more, then released rather than flown blind
  // (see MissionToken.msg: "should expire rather than be flown blind").
  double mission_ttl_s_ = 0.0;
  rclcpp::Time last_target_update_;
  bool track_active_ = false;
  // Analogue safety board veto (honoured as in rover_control_node).
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr veto_sub_;
  bool vetoed_ = false;
  rclcpp::Time last_veto_;
  bool holding_ = false;  // currently commanding a veto hold pose
  // The veto takes effect only after take-off; see TAKEOFF_ALTITUDE_FRAC.
  bool airborne_ = false;
  // Current vehicle position in NED local, from vehicle_local_position.
  rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr
      local_pos_sub_;
  double cur_north_ = 0.0, cur_east_ = 0.0, cur_down_ = 0.0;
  bool cur_valid_ = false;
  // Pose captured when a veto begins and held until it lifts, and the last
  // yaw commanded (held under veto so the UAV does not rotate while frozen).
  double hold_north_ = 0.0, hold_east_ = 0.0, hold_down_ = -5.0;
  double hold_yaw_ = 0.0;
  double last_yaw_cmd_ = 0.0;
  // Bounded-speed approach point, the setpoint the UAV tracks, and the
  // simulated time at which it was last advanced.
  double approach_north_ = 0.0, approach_east_ = 0.0;
  rclcpp::Time last_approach_t_{0, 0, RCL_ROS_TIME};
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<UavWorkerNode>());
  rclcpp::shutdown();
  return 0;
}