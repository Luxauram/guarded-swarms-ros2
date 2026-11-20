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
 * @file eo_agent_node.cpp
 *
 * @brief Electro-optical (EO) camera consultant agent, mounted on a UAV.
 *
 * The fourth sensing modality of the coastal surveillance scenario: an
 * electro-optical (EO) camera on a UAV that provides visual confirmation
 * when required.
 *
 * WHAT MAKES THIS MODALITY DIFFERENT
 * ==================================
 * Unlike the fixed radar, RF mast and buoys, the EO camera is carried by a
 * UAV, so its coverage MOVES with the platform. The agent reads the UAV's live
 * position and points a camera cone from there; a target is seen only if it
 * falls inside that cone right now. As the UAV flies, the covered volume flies
 * with it, at no change to this code.
 *
 * The EO modality emits ObsToken(KIND_VISUAL): a high-confidence position fix,
 * but only over a short range and a narrow field of view. It is the
 * confirmation that turns a track into a ConfirmedAerialObject. Because it is
 * scarce and conditional, a late EO confirmation is what makes the
 * time-windowed join of T5 fail: the mission is not released if the visual
 * arrives after the window has closed.
 *
 * THE STALE-EO COUNTERFACTUAL
 * ===========================
 * emit_delay_s (parameter, or the EO_DELAY_S environment variable) holds each
 * EO observation back by a fixed sim-time delay before publishing it. With a
 * large enough delay the ConfirmedAerialObject reaches T5 only after the
 * CandidateTarget's validity window has closed, so the two cannot fuse and no
 * ConfirmedThreat is produced: the confirmation IS generated and IS
 * delivered, but too late to matter. The default is 0 (no delay), so normal
 * runs are unaffected.
 *
 * The camera is modelled as a cone: an axis direction, a fixed bearing and
 * pitch in the world frame, and a half-angle. The cone is placed at the live
 * position of the UAV, so the coverage follows the UAV as its worker flies it;
 * the axis does not turn with the heading of the UAV.
 *
 * The UAV position arrives in NED from PX4 (vehicle_local_position). It is
 * converted to the world ENU frame that the target ground truth uses. The
 * conversion assumes the PX4 local frame origin coincides with the UAV's
 * Gazebo spawn pose, which is set per vehicle and passed in as a parameter.
 *
 * The coverage geometry and error model are a simulation model, not part of
 * the architecture.
 *
 * Topics:
 *   Subscribed:
 *     <uav_pose_topic>       (px4_msgs/VehicleLocalPosition)   the carrier UAV
 *     <ground_truth_topic>   (geometry_msgs/PoseStamped)       per target
 *   Published:
 *     /obs_tokens            (guarded_swarms_msgs/ObsToken)
 *
 * @author Luca D'Aurizio
 */

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <guarded_swarms_msgs/msg/obs_token.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <random>
#include <rclcpp/create_timer.hpp>
#include <rclcpp/rclcpp.hpp>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr int kQueueSize = 10;
// Period of the timer that drains the delayed-publication queue.
constexpr int kDrainPeriodMs = 50;
// The generator takes 32-bit seeds.
constexpr int64_t kMaxSeed = 4294967295;
}  // namespace

class EoAgentNode : public rclcpp::Node {
 public:
  EoAgentNode() : Node("eo_agent_node") {
    // --- Random generator ---
    // A seed above 0 fixes the noise of the run, so that it can be reproduced;
    // 0 draws a seed at random. Either way the seed in use is logged below.
    const int64_t seed = this->declare_parameter<int64_t>("seed", 0);
    if (seed < 0 || seed > kMaxSeed) {
      throw std::invalid_argument("seed must be between 0 and 4294967295");
    }
    seed_drawn_ = (seed == 0);
    seed_ = seed_drawn_ ? std::random_device{}() : static_cast<uint32_t>(seed);
    rng_.seed(seed_);
    // Carrier UAV identity, used only in the ObsToken.id prefix.
    carrier_ = this->declare_parameter<std::string>("carrier", "uav0");
    // The UAV's Gazebo spawn pose (world ENU). PX4 local position is relative
    // to this, so it is needed to place the camera in the world frame.
    spawn_x_ = this->declare_parameter<double>("spawn_x", -24.0);
    spawn_y_ = this->declare_parameter<double>("spawn_y", -24.0);
    spawn_z_ = this->declare_parameter<double>("spawn_z", 0.0);
    // Camera cone. bearing 90 deg points north (toward the sea); pitch below
    // horizontal looks down at low-altitude tracks over the water.
    cam_bearing_deg_ = this->declare_parameter<double>("cam_bearing_deg", 90.0);
    cam_pitch_deg_ = this->declare_parameter<double>("cam_pitch_deg", -20.0);
    half_angle_deg_ = this->declare_parameter<double>("half_angle_deg", 30.0);
    max_range_m_ = this->declare_parameter<double>("max_range_m", 120.0);
    position_noise_m_ =
        this->declare_parameter<double>("position_noise_m", 1.0);
    detection_prob_ = this->declare_parameter<double>("detection_prob", 0.98);
    latency_s_ = this->declare_parameter<double>("latency_s", 0.15);
    ttl_s_ = this->declare_parameter<double>("ttl_s", 2.0);
    update_rate_hz_ = this->declare_parameter<double>("update_rate_hz", 5.0);
    confidence_ = this->declare_parameter<double>("confidence", 0.95);
    // Stale-EO counterfactual: hold each observation back by this many seconds
    // before publishing. Parameter default 0; overridable by EO_DELAY_S in the
    // environment so a counterfactual run needs no rebuild or YAML edit.
    emit_delay_s_ = this->declare_parameter<double>("emit_delay_s", 0.0);
    if (const char* env = std::getenv("EO_DELAY_S")) {
      try {
        emit_delay_s_ = std::stod(env);
      } catch (...) {
        RCLCPP_WARN(this->get_logger(),
                    "EO_DELAY_S='%s' is not a number; ignoring.", env);
      }
    }
    const auto uav_topic = this->declare_parameter<std::string>(
        "uav_pose_topic", "/fmu/out/vehicle_local_position_v1");
    target_ids_ = this->declare_parameter<std::vector<std::string>>(
        "target_ids", std::vector<std::string>{"intruder"});
    const auto gt_topics = this->declare_parameter<std::vector<std::string>>(
        "ground_truth_topics",
        std::vector<std::string>{"/intruder/ground_truth"});
    auto px4_qos = rclcpp::QoS(10)
                       .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                       .durability(rclcpp::DurabilityPolicy::TransientLocal);
    uav_sub_ = this->create_subscription<px4_msgs::msg::VehicleLocalPosition>(
        uav_topic, px4_qos,
        [this](const px4_msgs::msg::VehicleLocalPosition::SharedPtr m) {
          // PX4 NED -> world ENU, offset by the spawn pose.
          // ENU east  = NED east   = m->y ; ENU north = NED north = m->x
          // ENU up    = -NED down  = -m->z
          uav_x_ = spawn_x_ + m->y;
          uav_y_ = spawn_y_ + m->x;
          uav_z_ = spawn_z_ - m->z;
          uav_valid_ = true;
        });
    const size_t n = target_ids_.size();
    if (gt_topics.size() != n) {
      RCLCPP_ERROR(this->get_logger(),
                   "target_ids (%zu) and ground_truth_topics (%zu) must match.",
                   n, gt_topics.size());
    } else {
      last_pose_.resize(n);
      pose_valid_.assign(n, false);
      for (size_t i = 0; i < n; ++i) {
        const size_t idx = i;
        gt_subs_.push_back(
            this->create_subscription<geometry_msgs::msg::PoseStamped>(
                gt_topics[i], kQueueSize,
                [this,
                 idx](const geometry_msgs::msg::PoseStamped::SharedPtr m) {
                  last_pose_[idx] = *m;
                  pose_valid_[idx] = true;
                }));
      }
    }
    obs_pub_ = this->create_publisher<guarded_swarms_msgs::msg::ObsToken>(
        "/obs_tokens", kQueueSize);
    // Scans run on the node clock (simulated time): update_rate_hz_ scans per
    // simulated second, whatever the real-time factor.
    timer_ = rclcpp::create_timer(
        this, this->get_clock(),
        rclcpp::Duration::from_seconds(1.0 / update_rate_hz_),
        [this]() { scan(); });
    // A second timer drains the delayed-publication queue, so a held-back EO
    // observation is released once its delay has elapsed even if no new scan
    // happens meanwhile.
    if (emit_delay_s_ > 0.0) {
      drain_timer_ = rclcpp::create_timer(
          this, this->get_clock(),
          rclcpp::Duration::from_seconds(kDrainPeriodMs / 1000.0),
          [this]() { drain_delayed(); });
    }
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "EoAgent (UAV-mounted EO camera)");
    RCLCPP_INFO(this->get_logger(), "  carrier %s, spawn (%.0f, %.0f, %.0f)",
                carrier_.c_str(), spawn_x_, spawn_y_, spawn_z_);
    RCLCPP_INFO(this->get_logger(),
                "  cone: bearing %.0f, pitch %.0f, half-angle %.0f, range %.0f",
                cam_bearing_deg_, cam_pitch_deg_, half_angle_deg_,
                max_range_m_);
    if (emit_delay_s_ > 0.0) {
      RCLCPP_WARN(this->get_logger(),
                  "  STALE-EO counterfactual: emit delay %.1f s",
                  emit_delay_s_);
    }
    RCLCPP_INFO(this->get_logger(),
                "  coverage moves with the platform; emits VISUAL");
    RCLCPP_INFO(this->get_logger(), "  seed %lu%s",
                static_cast<unsigned long>(seed_),
                seed_drawn_ ? " (drawn at random: seed parameter was 0)" : "");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  struct Pending {
    guarded_swarms_msgs::msg::ObsToken tok;
    rclcpp::Time release_at;  // simulated instant to publish
  };

  /** @brief Scans every target with a valid pose, if the carrier pose is known.
   */
  void scan() {
    if (!uav_valid_) return;  // no carrier pose yet, no camera to point
    for (size_t i = 0; i < pose_valid_.size(); ++i) {
      if (pose_valid_[i]) {
        evaluate_target(i);
      }
    }
  }

  /**
   * @brief Emits a visual ObsToken if target i falls inside the camera cone.
   * @param i  Index into target_ids_ / last_pose_.
   */
  void evaluate_target(size_t i) {
    const auto& p = last_pose_[i].pose.position;
    // Vector from the camera (at the UAV) to the target.
    const double dx = p.x - uav_x_;
    const double dy = p.y - uav_y_;
    const double dz = p.z - uav_z_;
    const double range = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (range > max_range_m_) return;
    // Camera axis unit vector from bearing and pitch.
    const double b = cam_bearing_deg_ * kPi / 180.0;
    const double pit = cam_pitch_deg_ * kPi / 180.0;
    const double ax = std::cos(pit) * std::cos(b);
    const double ay = std::cos(pit) * std::sin(b);
    const double az = std::sin(pit);
    // Angle between the camera axis and the line to the target.
    const double dot = (dx * ax + dy * ay + dz * az) / std::max(range, 1e-6);
    const double ang = std::acos(std::max(-1.0, std::min(1.0, dot)));
    if (ang > half_angle_deg_ * kPi / 180.0) return;  // outside the cone
    if (uniform_(rng_) > detection_prob_) return;
    guarded_swarms_msgs::msg::ObsToken tok;
    tok.id = "eo-" + carrier_ + "-" + std::to_string(seq_++);
    tok.target_id = target_ids_[i];
    tok.source = guarded_swarms_msgs::msg::ObsToken::SOURCE_EO;
    tok.kind = guarded_swarms_msgs::msg::ObsToken::KIND_VISUAL;
    // A high-quality position fix: x, y, z in world ENU.
    tok.value = {p.x + noise(), p.y + noise(), p.z + noise()};
    tok.confidence = confidence_;
    tok.t = builtin_interfaces::msg::Time(
        this->now() - rclcpp::Duration::from_seconds(latency_s_));
    tok.ttl_s = ttl_s_;
    if (emit_delay_s_ > 0.0) {
      // Stale-EO counterfactual: queue for later publication. The token's own
      // timestamp is left as observed; it is the DELIVERY that is late, which
      // is what pushes the ConfirmedAerialObject outside T5's fusion window.
      Pending pend;
      pend.tok = tok;
      pend.release_at =
          this->now() + rclcpp::Duration::from_seconds(emit_delay_s_);
      delayed_.push_back(pend);
      return;
    }
    obs_pub_->publish(tok);
  }

  /** @brief Publishes any queued observations whose delay has elapsed. */
  void drain_delayed() {
    const rclcpp::Time now = this->now();
    while (!delayed_.empty() && delayed_.front().release_at <= now) {
      obs_pub_->publish(delayed_.front().tok);
      delayed_.pop_front();
    }
  }

  /** @brief Returns a Gaussian position-noise sample (metres). */
  double noise() {
    std::normal_distribution<double> d(0.0, position_noise_m_);
    return d(rng_);
  }

  std::string carrier_;
  double spawn_x_, spawn_y_, spawn_z_;
  double cam_bearing_deg_, cam_pitch_deg_, half_angle_deg_, max_range_m_;
  double position_noise_m_, detection_prob_, latency_s_, ttl_s_;
  double update_rate_hz_, confidence_, emit_delay_s_;
  double uav_x_ = 0.0, uav_y_ = 0.0, uav_z_ = 0.0;
  bool uav_valid_ = false;
  std::vector<std::string> target_ids_;
  std::vector<geometry_msgs::msg::PoseStamped> last_pose_;
  std::vector<bool> pose_valid_;
  std::deque<Pending> delayed_;
  rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr uav_sub_;
  std::vector<rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr>
      gt_subs_;
  rclcpp::Publisher<guarded_swarms_msgs::msg::ObsToken>::SharedPtr obs_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::TimerBase::SharedPtr drain_timer_;
  std::mt19937 rng_;
  uint32_t seed_ = 0;        // the seed in use, logged at start-up
  bool seed_drawn_ = false;  // drawn at random (seed parameter was 0)
  std::uniform_real_distribution<double> uniform_{0.0, 1.0};
  uint64_t seq_ = 0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<EoAgentNode>());
  rclcpp::shutdown();
  return 0;
}