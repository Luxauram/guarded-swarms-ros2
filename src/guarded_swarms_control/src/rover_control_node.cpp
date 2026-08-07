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
 * @file rover_control_node.cpp
 *
 * @brief Autonomous patrol controller for the UGV differential rover.
 *
 * Implements a simple waypoint-based patrol loop along the urban_ugv street
 * corridor. The rover advances toward the obstacle (abandoned vehicle at ~10m)
 * and returns to the start, continuously cycling.
 *
 * The analog safety board independently monitors the frontal lidar and vetoes
 * actuator commands when the rover comes within 1.5m of any obstacle — this
 * node does NOT need to know about that; the decoupling is intentional and
 * mirrors the Guarded Swarms architecture described in the paper.
 *
 * Waypoint sequence (NED frame, relative to spawn):
 *   WP0: (0, 0)    — start / home
 *   WP1: (8, 0)    — advance (obstacle is at ~10m, veto fires before arrival)
 *   WP0: (0, 0)    — return home
 *   (repeat)
 *
 * Topics:
 *   Published:
 *     /fmu/in/rover_position_setpoint  (px4_msgs/RoverPositionSetpoint)
 *     /fmu/in/vehicle_command          (px4_msgs/VehicleCommand) — arming
*   Subscribed:
 *     /fmu/out/vehicle_local_position_v1 (px4_msgs/VehicleLocalPosition)
 *
 * Parameters:
 *   target_system (int, default 1) — PX4 MAV_SYS_ID of the target vehicle.
 *     Multi-vehicle: instance N has MAV_SYS_ID N+1, so instance 1 needs
 *     target_system:=2. Topics are namespaced separately (__ns:=/px4_1).
 *   waypoints (double[], default [0,0,8,0]) — patrol waypoints in the NED
 *     frame relative to spawn, flattened as north,east,north,east,...
 *     NED East = Gazebo X, so a shore-parallel patrol varies the second value.
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/rover_position_setpoint.hpp>
#include <px4_msgs/msg/rover_throttle_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <std_msgs/msg/float32.hpp>
#include <cmath>
#include <vector>
#include <array>

using namespace std::chrono_literals;

// ============================================================================
// Constants
// ============================================================================

static constexpr float WAYPOINT_RADIUS_M   = 0.8f;   // m - arrival tolerance
static constexpr float CRUISING_SPEED_MS   = 1.0f;   // m/s
static constexpr float ARRIVAL_SPEED_MS    = 0.3f;   // m/s - slow on approach
static constexpr double PUBLISH_RATE_HZ    = 10.0;
static constexpr double ARM_DELAY_S        = 5.0;    // s - wait before arming
// After this long under a sustained veto the current waypoint is treated as
// unreachable and the patrol reverses. Without it the rover waits forever in
// front of the first obstacle on its route.
static constexpr double VETO_GIVEUP_S      = 6.0;
// Minimum time a veto is honoured once it fires. Without it the vehicle stops,
// the obstacle drops out of the lidar cone, the veto clears, and the vehicle
// resumes: it edges forward a few centimetres per cycle and the give-up timer
// never matures.
static constexpr double VETO_MIN_HOLD_S    = 2.0;
// Below this actuator_cmd_safe value the board's verdict counts as a veto.
static constexpr float  VETO_CMD_THRESHOLD = 0.01f;
static constexpr int    QUEUE_SIZE         = 10;
static constexpr uint8_t PX4_COMPONENT_ID  = 1;
// Magic value PX4 requires in param2 to force-arm, bypassing preflight checks.
// Acceptable in SITL, where the preflight sensors are simulated.
static constexpr float  PARAM_FORCE_ARM    = 21196.0f;
static constexpr float  PARAM_ARM          = 1.0f;

// Waypoints in NED frame (north, east) relative to spawn origin
// Default patrol: 8 m straight ahead (NED north). Overridden by the
// "waypoints" parameter, flattened as north,east,north,east,...
static const std::vector<double> DEFAULT_WAYPOINTS = { 0.0, 0.0, 8.0, 0.0 };

// ============================================================================
// RoverControlNode
// ============================================================================

class RoverControlNode : public rclcpp::Node
{
public:
    RoverControlNode() : Node("rover_control_node")
    {
        // PX4 MAV_SYS_ID of the target vehicle.
        // SITL assigns instance 0 -> 1, instance 1 -> 2, etc. A command
        // addressed to the wrong system ID is silently ignored by PX4.
        target_system_ = static_cast<uint8_t>(
            this->declare_parameter<int>("target_system", 1));

        // Patrol waypoints, NED relative to spawn, flattened as
        // north,east,north,east,... Making these a parameter lets one node
        // serve different scenarios: the urban rover advances north toward
        // the obstacle, the coastal rover patrols east along the shore.
        const auto flat = this->declare_parameter<std::vector<double>>(
            "waypoints", DEFAULT_WAYPOINTS);

        if (flat.size() < 4 || flat.size() % 2 != 0) {
            RCLCPP_ERROR(this->get_logger(),
                "Parameter 'waypoints' must hold an even count of at least 4 "
                "values (got %zu). Falling back to the default patrol.",
                flat.size());
            waypoints_ = {{0.0f, 0.0f}, {8.0f, 0.0f}};
        } else {
            for (size_t i = 0; i + 1 < flat.size(); i += 2) {
                waypoints_.push_back({static_cast<float>(flat[i]),
                                      static_cast<float>(flat[i + 1])});
            }
        }

        // QoS for PX4 topics
        auto qos = rclcpp::QoS(QUEUE_SIZE)
            .reliability(rclcpp::ReliabilityPolicy::BestEffort)
            .durability(rclcpp::DurabilityPolicy::TransientLocal);

        pos_setpoint_pub_ = this->create_publisher<
            px4_msgs::msg::RoverPositionSetpoint>(
            "fmu/in/rover_position_setpoint", QUEUE_SIZE);

        vehicle_cmd_pub_ = this->create_publisher<
            px4_msgs::msg::VehicleCommand>(
            "fmu/in/vehicle_command", QUEUE_SIZE);

        // Under veto the rover is stopped by commanding zero throttle, not by
        // commanding its own position: a position setpoint at zero distance
        // leaves the target heading undefined and the vehicle spins in place.
        throttle_pub_ = this->create_publisher<
            px4_msgs::msg::RoverThrottleSetpoint>(
            "fmu/in/rover_throttle_setpoint", QUEUE_SIZE);

        local_pos_sub_ = this->create_subscription<
            px4_msgs::msg::VehicleLocalPosition>(
            "fmu/out/vehicle_local_position_v1", qos,
            [this](const px4_msgs::msg::VehicleLocalPosition::SharedPtr msg) {
                on_local_position(msg);
            });
        
        // The analogue safety board publishes its verdict here. The control
        // node does not evaluate safety itself and does not know why a veto
        // fires: it only stops commanding motion while one is active. The
        // asymmetry is deliberate and mirrors the paper's decoupling.
        //
        // In simulation the board cannot physically interrupt actuation the
        // way an analogue circuit would, so the gate lives in the commanding
        // node. Document this as a simulation limitation.
        cmd_safe_sub_ = this->create_subscription<std_msgs::msg::Float32>(
            "actuator_cmd_safe", QUEUE_SIZE,
            [this](const std_msgs::msg::Float32::SharedPtr msg) {
                if (msg->data < VETO_CMD_THRESHOLD) {
                    vetoed_ = true;
                    last_veto_ = this->now();
                } else if (vetoed_ &&
                           (this->now() - last_veto_).seconds() > VETO_MIN_HOLD_S) {
                    // Guarded on vetoed_, not on veto_timing_: the give-up
                    // logic clears veto_timing_, and gating the release on it
                    // would make the veto impossible to lift afterwards.
                    vetoed_ = false;
                }
            });

        timer_ = this->create_wall_timer(
            std::chrono::duration<double>(1.0 / PUBLISH_RATE_HZ),
            [this]() { control_loop(); });

        start_time_ = this->now();

        RCLCPP_INFO(this->get_logger(),
            "============================================================");
        RCLCPP_INFO(this->get_logger(),
            "RoverControlNode initialized");
        RCLCPP_INFO(this->get_logger(),
            "  Patrol waypoints: %zu", waypoints_.size());
        RCLCPP_INFO(this->get_logger(),
            "  Cruising speed:   %.1f m/s", CRUISING_SPEED_MS);
        RCLCPP_INFO(this->get_logger(),
            "  Waypoint radius:  %.1f m", WAYPOINT_RADIUS_M);
        RCLCPP_INFO(this->get_logger(),
            "  Arming in:        %.0f s", ARM_DELAY_S);
        RCLCPP_INFO(this->get_logger(),
            "  Target system ID: %u", target_system_);
        RCLCPP_INFO(this->get_logger(),
            "============================================================");
    }

private:
    // -----------------------------------------------------------------------
    // Subscribers / Publishers / Timer
    // -----------------------------------------------------------------------
    rclcpp::Publisher<px4_msgs::msg::RoverPositionSetpoint>::SharedPtr pos_setpoint_pub_;
    rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr vehicle_cmd_pub_;
    rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr local_pos_sub_;
    rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr cmd_safe_sub_;
    bool vetoed_ = false;
    rclcpp::TimerBase::SharedPtr timer_;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    rclcpp::Time start_time_;
    uint8_t target_system_ = 1;
    std::vector<std::array<float, 2>> waypoints_;
    bool armed_          = false;
    bool patrol_active_  = false;
    size_t wp_index_     = 0;
    bool wp_forward_     = true;   // true = advancing, false = returning

    float rover_north_   = 0.0f;
    float rover_east_    = 0.0f;
    bool  pos_valid_     = false;

    rclcpp::Publisher<px4_msgs::msg::RoverThrottleSetpoint>::SharedPtr throttle_pub_;
    rclcpp::Time veto_start_;
    rclcpp::Time last_veto_;
    bool  veto_timing_   = false;

    // -----------------------------------------------------------------------
    // Local position callback
    // -----------------------------------------------------------------------

    /**
     * @brief Caches the rover's NED position from PX4 local position.
     * @param msg Shared pointer to the received @c VehicleLocalPosition.
     */
    void on_local_position(
        const px4_msgs::msg::VehicleLocalPosition::SharedPtr msg)
    {
        rover_north_ = msg->x;
        rover_east_  = msg->y;
        pos_valid_   = true;
    }

    // -----------------------------------------------------------------------
    // Main control loop
    // -----------------------------------------------------------------------

    /** @brief Main loop: arms, then patrols, honouring the safety veto. */
    void control_loop()
    {
        double elapsed = (this->now() - start_time_).seconds();

        // --- Phase 1: wait for PX4 to initialise, then arm ---
        if (!armed_) {
            if (elapsed > ARM_DELAY_S) {
                arm_rover();
                armed_ = true;
                patrol_active_ = true;
                RCLCPP_INFO(this->get_logger(), "Rover armed. Starting patrol.");
            }
            return;
        }

        if (!patrol_active_ || !pos_valid_) return;

        // --- Phase 2: publish current waypoint, unless vetoed ---
        if (vetoed_) {
            publish_stop();

            if (!veto_timing_) {
                veto_timing_ = true;
                veto_start_ = this->now();
                RCLCPP_WARN(this->get_logger(),
                    "Veto active: stopping at (%.1f, %.1f)",
                    rover_north_, rover_east_);
            } else if ((this->now() - veto_start_).seconds() > VETO_GIVEUP_S) {
                RCLCPP_WARN(this->get_logger(),
                    "WP%zu unreachable under sustained veto, reversing patrol.",
                    wp_index_);
                advance_waypoint();
                veto_timing_ = false;
            }
            return;
        }
        veto_timing_ = false;
        publish_waypoint(waypoints_[wp_index_]);

        // --- Phase 3: check arrival ---
        if (reached_waypoint(waypoints_[wp_index_])) {
            RCLCPP_INFO(this->get_logger(),
                "Reached WP%zu (%.1f, %.1f)",
                wp_index_,
                waypoints_[wp_index_][0],
                waypoints_[wp_index_][1]);

            advance_waypoint();
        }
    }

    // -----------------------------------------------------------------------
    // Waypoint logic
    // -----------------------------------------------------------------------

    /** @brief Advances to the next patrol waypoint, reversing at either end. */
    void advance_waypoint()
    {
        if (wp_forward_) {
            if (wp_index_ + 1 < waypoints_.size()) {
                wp_index_++;
            } else {
                // reached end — reverse
                wp_forward_ = false;
                if (wp_index_ > 0) wp_index_--;
            }
        } else {
            if (wp_index_ > 0) {
                wp_index_--;
            } else {
                // back at home — go forward again
                wp_forward_ = true;
                wp_index_++;
            }
        }

        RCLCPP_INFO(this->get_logger(),
            "Next WP%zu (%.1f, %.1f) | direction: %s",
            wp_index_,
            waypoints_[wp_index_][0],
            waypoints_[wp_index_][1],
            wp_forward_ ? "forward" : "returning");
    }

    /**
     * @brief True if the rover is within WAYPOINT_RADIUS_M of the waypoint.
     * @param wp  Target waypoint, NED (north, east).
     */
    bool reached_waypoint(const std::array<float, 2>& wp) const
    {
        float dn = rover_north_ - wp[0];
        float de = rover_east_  - wp[1];
        return std::sqrt(dn * dn + de * de) < WAYPOINT_RADIUS_M;
    }

    // -----------------------------------------------------------------------
    // PX4 command helpers
    // -----------------------------------------------------------------------

    /**
     * @brief Publishes a rover position setpoint for the given waypoint.
     * @param wp  Target waypoint, NED (north, east).
     */
    void publish_waypoint(const std::array<float, 2>& wp)
    {
        px4_msgs::msg::RoverPositionSetpoint msg;
        msg.timestamp       = this->now().nanoseconds() / 1000;
        msg.position_ned[0] = wp[0];
        msg.position_ned[1] = wp[1];
        msg.cruising_speed  = CRUISING_SPEED_MS;
        msg.arrival_speed   = ARRIVAL_SPEED_MS;
        msg.yaw             = std::numeric_limits<float>::quiet_NaN();
        msg.start_ned[0]    = std::numeric_limits<float>::quiet_NaN();
        msg.start_ned[1]    = std::numeric_limits<float>::quiet_NaN();
        pos_setpoint_pub_->publish(msg);
    }

    /** @brief Commands zero throttle to hold the rover still under veto. */
    void publish_stop()
    {
        px4_msgs::msg::RoverThrottleSetpoint msg;
        msg.timestamp       = this->now().nanoseconds() / 1000;
        msg.throttle_body_x = 0.0f;
        msg.throttle_body_y = 0.0f;
        throttle_pub_->publish(msg);
    }

    /** @brief Sends the force-arm command to PX4. */
    void arm_rover()
    {
        px4_msgs::msg::VehicleCommand cmd;
        cmd.timestamp        = this->now().nanoseconds() / 1000;
        cmd.command          = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM;
        cmd.param1           = PARAM_ARM;
        cmd.param2           = PARAM_FORCE_ARM;
        cmd.target_system    = target_system_;
        cmd.target_component = PX4_COMPONENT_ID;
        cmd.source_system    = target_system_;
        cmd.source_component = PX4_COMPONENT_ID;
        cmd.from_external    = true;
        vehicle_cmd_pub_->publish(cmd);

        RCLCPP_INFO(this->get_logger(), "Arming command sent.");
    }
};

// ============================================================================
// Main
// ============================================================================

int main(int argc, char* argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<RoverControlNode>());
    rclcpp::shutdown();
    return 0;
}