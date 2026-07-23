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
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/rover_position_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
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

// Waypoints in NED frame (north, east) relative to spawn origin
static const std::vector<std::array<float, 2>> WAYPOINTS = {
    {  0.0f,  0.0f },   // WP0: home / return point
    {  8.0f,  0.0f },   // WP1: advance toward obstacle (veto fires at ~8.5m)
};

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

        // QoS for PX4 topics
        auto qos = rclcpp::QoS(10)
            .reliability(rclcpp::ReliabilityPolicy::BestEffort)
            .durability(rclcpp::DurabilityPolicy::TransientLocal);

        pos_setpoint_pub_ = this->create_publisher<
            px4_msgs::msg::RoverPositionSetpoint>(
            "fmu/in/rover_position_setpoint", 10);

        vehicle_cmd_pub_ = this->create_publisher<
            px4_msgs::msg::VehicleCommand>(
            "fmu/in/vehicle_command", 10);

        local_pos_sub_ = this->create_subscription<
            px4_msgs::msg::VehicleLocalPosition>(
            "fmu/out/vehicle_local_position_v1", qos,
            [this](const px4_msgs::msg::VehicleLocalPosition::SharedPtr msg) {
                on_local_position(msg);
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
            "  Patrol waypoints: %zu", WAYPOINTS.size());
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
    rclcpp::TimerBase::SharedPtr timer_;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    rclcpp::Time start_time_;
    uint8_t target_system_ = 1;
    bool armed_          = false;
    bool patrol_active_  = false;
    size_t wp_index_     = 0;
    bool wp_forward_     = true;   // true = advancing, false = returning

    float rover_north_   = 0.0f;
    float rover_east_    = 0.0f;
    bool  pos_valid_     = false;

    // -----------------------------------------------------------------------
    // Local position callback
    // -----------------------------------------------------------------------
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

        // --- Phase 2: publish current waypoint ---
        publish_waypoint(WAYPOINTS[wp_index_]);

        // --- Phase 3: check arrival ---
        if (reached_waypoint(WAYPOINTS[wp_index_])) {
            RCLCPP_INFO(this->get_logger(),
                "Reached WP%zu (%.1f, %.1f)",
                wp_index_,
                WAYPOINTS[wp_index_][0],
                WAYPOINTS[wp_index_][1]);

            advance_waypoint();
        }
    }

    // -----------------------------------------------------------------------
    // Waypoint logic
    // -----------------------------------------------------------------------
    void advance_waypoint()
    {
        if (wp_forward_) {
            if (wp_index_ + 1 < WAYPOINTS.size()) {
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
            WAYPOINTS[wp_index_][0],
            WAYPOINTS[wp_index_][1],
            wp_forward_ ? "forward" : "returning");
    }

    bool reached_waypoint(const std::array<float, 2>& wp) const
    {
        float dn = rover_north_ - wp[0];
        float de = rover_east_  - wp[1];
        return std::sqrt(dn * dn + de * de) < WAYPOINT_RADIUS_M;
    }

    // -----------------------------------------------------------------------
    // PX4 command helpers
    // -----------------------------------------------------------------------
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

    void arm_rover()
    {
        px4_msgs::msg::VehicleCommand cmd;
        cmd.timestamp        = this->now().nanoseconds() / 1000;
        cmd.command          = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM;
        cmd.param1           = 1.0f;   // 1 = arm
        cmd.param2           = 21196.0f; // force arm magic number
        cmd.target_system    = target_system_;
        cmd.target_component = 1;
        cmd.source_system    = target_system_;
        cmd.source_component = 1;
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