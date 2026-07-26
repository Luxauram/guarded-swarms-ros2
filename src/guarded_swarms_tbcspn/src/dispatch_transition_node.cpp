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
 * @file dispatch_transition_node.cpp
 *
 * @brief Dispatch transition (Figure 4, T7): mission -> vehicle tasks.
 *
 * The dispatch transition of the coastal case study in Borghoff, Bottoni and
 * Pareschi (2026), IET Radar, Sonar and Navigation, Figure 4 and Section 5.2.
 * It consumes an authorised InterceptMission and produces the vehicle-specific
 * tasks that worker agents will translate into platform commands:
 *
 *   InterceptMission  ->  UAVTask (intercept)  +  UGVTask (observe)
 *
 * The paper fixes the architecture but not the assignment algorithm, so the
 * assignment here is an implementation choice, to be declared as such:
 *
 *   - the intercept task goes to the UAV nearest the target at dispatch time;
 *   - an observe task goes to the UGV, for shore-based support and recovery.
 *
 * With a single target this is trivial; the same structure extends to an
 * N-vehicles-to-M-targets assignment later. Nearest-UAV needs the UAVs' live
 * positions, which the node reads from their vehicle_local_position (NED->ENU
 * by each UAV's spawn offset, exactly as the EO agent does).
 *
 * A mission is dispatched once. Its mission_id is remembered so repeated
 * MissionTokens for the same mission (the release transition may emit several
 * while the threat persists) do not scramble the swarm with duplicate tasks.
 *
 * Topics:
 *   Subscribed:
 *     /mission_tokens   (guarded_swarms_msgs/MissionToken)
 *     <uav_pose_topics> (px4_msgs/VehicleLocalPosition)  one per UAV
 *   Published:
 *     /vehicle_tasks    (guarded_swarms_msgs/VehicleTask)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <guarded_swarms_msgs/msg/mission_token.hpp>
#include <guarded_swarms_msgs/msg/vehicle_task.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>

#include <cmath>
#include <limits>
#include <set>
#include <string>
#include <vector>

using guarded_swarms_msgs::msg::MissionToken;
using guarded_swarms_msgs::msg::VehicleTask;

class DispatchTransitionNode : public rclcpp::Node {
 public:
  DispatchTransitionNode() : Node("dispatch_transition_node") {
    // UAV fleet: system IDs, pose topics and spawn poses, index-aligned. The
    // spawn pose converts each UAV's NED local position into the world ENU
    // frame the target lives in.
    uav_systems_ = read_int_list("uav_systems", {int64_t{1}, int64_t{2}});
    const auto uav_topics = this->declare_parameter<std::vector<std::string>>(
        "uav_pose_topics",
        std::vector<std::string>{"/fmu/out/vehicle_local_position_v1",
                                 "/px4_1/fmu/out/vehicle_local_position_v1"});
    const auto spawn_flat = this->declare_parameter<std::vector<double>>(
        "uav_spawns", std::vector<double>{-24.0, -24.0, 0.0, 24.0, -24.0, 0.0});

    ugv_system_ = static_cast<uint8_t>(
        this->declare_parameter<int>("ugv_system", 3));

    const size_t n = uav_systems_.size();
    uav_pose_.assign(n, {0.0, 0.0, 0.0});
    uav_valid_.assign(n, false);
    for (size_t i = 0; i < n; ++i) {
      std::array<double, 3> spawn{spawn_flat.at(3 * i), spawn_flat.at(3 * i + 1),
                                  spawn_flat.at(3 * i + 2)};
      uav_spawn_.push_back(spawn);
    }

    auto px4_qos = rclcpp::QoS(10)
                       .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                       .durability(rclcpp::DurabilityPolicy::TransientLocal);

    for (size_t i = 0; i < n && i < uav_topics.size(); ++i) {
      const size_t idx = i;
      uav_subs_.push_back(
          this->create_subscription<px4_msgs::msg::VehicleLocalPosition>(
              uav_topics[i], px4_qos,
              [this, idx](
                  const px4_msgs::msg::VehicleLocalPosition::SharedPtr m) {
                // NED -> ENU, offset by spawn pose (same as the EO agent).
                uav_pose_[idx] = {uav_spawn_[idx][0] + m->y,
                                  uav_spawn_[idx][1] + m->x,
                                  uav_spawn_[idx][2] - m->z};
                uav_valid_[idx] = true;
              }));
    }

    mission_sub_ = this->create_subscription<MissionToken>(
        "/mission_tokens", 10,
        [this](const MissionToken::SharedPtr m) { on_mission(m); });

    task_pub_ = this->create_publisher<VehicleTask>("/vehicle_tasks", 10);

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(),
                "DispatchTransitionNode (TB-CSPN T7)");
    RCLCPP_INFO(this->get_logger(),
                "  InterceptMission -> UAVTask(intercept) + UGVTask(observe)");
    RCLCPP_INFO(this->get_logger(), "  %zu UAV(s), UGV system %u",
                uav_systems_.size(), ugv_system_);
    RCLCPP_INFO(this->get_logger(),
                "  assignment: nearest UAV to the target (implementation "
                "choice, not from the paper)");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  void on_mission(const MissionToken::SharedPtr m) {
    // Dispatch each mission exactly once.
    if (dispatched_.count(m->mission_id)) return;
    dispatched_.insert(m->mission_id);

    const uint8_t uav = nearest_uav(m->target_position);

    // Intercept task to the chosen UAV.
    VehicleTask uav_task;
    uav_task.task_id = m->mission_id + "-uav";
    uav_task.mission_id = m->mission_id;
    uav_task.target_id = m->target_id;
    uav_task.target_position = m->target_position;
    uav_task.vehicle_kind = VehicleTask::KIND_UAV;
    uav_task.assigned_system = uav;
    uav_task.task_type = VehicleTask::TASK_INTERCEPT;
    uav_task.justification = m->justification;
    uav_task.justification.push_back("mission:" + m->mission_id);
    uav_task.t = this->now();
    uav_task.ttl_s = m->ttl_s;
    task_pub_->publish(uav_task);

    // Observe task to the UGV.
    VehicleTask ugv_task;
    ugv_task.task_id = m->mission_id + "-ugv";
    ugv_task.mission_id = m->mission_id;
    ugv_task.target_id = m->target_id;
    ugv_task.target_position = m->target_position;
    ugv_task.vehicle_kind = VehicleTask::KIND_UGV;
    ugv_task.assigned_system = ugv_system_;
    ugv_task.task_type = VehicleTask::TASK_OBSERVE;
    ugv_task.justification = m->justification;
    ugv_task.justification.push_back("mission:" + m->mission_id);
    ugv_task.t = this->now();
    ugv_task.ttl_s = m->ttl_s;
    task_pub_->publish(ugv_task);

    RCLCPP_WARN(this->get_logger(),
                "Dispatched mission '%s' for '%s': intercept -> UAV sys %u, "
                "observe -> UGV sys %u",
                m->mission_id.c_str(), m->target_id.c_str(), uav, ugv_system_);
  }

  uint8_t nearest_uav(const geometry_msgs::msg::Point& target) {
    int best = -1;
    double best_d = std::numeric_limits<double>::max();
    for (size_t i = 0; i < uav_systems_.size(); ++i) {
      if (!uav_valid_[i]) continue;
      const double dx = uav_pose_[i][0] - target.x;
      const double dy = uav_pose_[i][1] - target.y;
      const double dz = uav_pose_[i][2] - target.z;
      const double d = dx * dx + dy * dy + dz * dz;
      if (d < best_d) {
        best_d = d;
        best = static_cast<int>(i);
      }
    }
    // If no pose has arrived yet, fall back to the first UAV rather than
    // dispatching to nobody.
    if (best < 0) {
      RCLCPP_WARN(this->get_logger(),
                  "No live UAV pose; assigning the first UAV by default.");
      return uav_systems_.empty() ? 1 : uav_systems_.front();
    }
    return uav_systems_[best];
  }

  std::vector<uint8_t> read_int_list(const std::string& name,
                                     const std::vector<int64_t>& def) {
    // ROS 2 delivers integer-array parameters as int64, so declare and read
    // them as int64 and narrow to the uint8 system IDs afterwards.
    const auto raw = this->declare_parameter<std::vector<int64_t>>(name, def);
    std::vector<uint8_t> out;
    for (int64_t v : raw) out.push_back(static_cast<uint8_t>(v));
    return out;
  }

  std::vector<uint8_t> uav_systems_;
  uint8_t ugv_system_ = 3;
  std::vector<std::array<double, 3>> uav_spawn_;
  std::vector<std::array<double, 3>> uav_pose_;
  std::vector<bool> uav_valid_;

  std::vector<rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr>
      uav_subs_;
  rclcpp::Subscription<MissionToken>::SharedPtr mission_sub_;
  rclcpp::Publisher<VehicleTask>::SharedPtr task_pub_;

  std::set<std::string> dispatched_;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<DispatchTransitionNode>());
  rclcpp::shutdown();
  return 0;
}