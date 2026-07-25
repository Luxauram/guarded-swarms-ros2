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
 * @file radar_agent_node.cpp
 *
 * @brief Coastal radar consultant agent.
 *
 * One of the four sensing modalities of the coastal surveillance scenario in
 * Borghoff, Bottoni and Pareschi (2026), IET Radar, Sonar and Navigation,
 * Section 5.1: "a coastal radar capable of detecting low-altitude aerial
 * tracks". It emits ObsToken(KIND_TRACK) with a position and velocity
 * estimate of the target.
 *
 * WHAT IS FROM THE PAPER, AND WHAT IS NOT
 * ======================================
 * The paper names the modality and says what it detects. It does NOT specify a
 * coverage geometry: the sector, orientation, range and error model below are
 * a simulation model, and must be presented as such in the thesis rather than
 * attributed to the paper.
 *
 * The coverage model is the point of the exercise. A coastal radar faces the
 * sea, so it is described by a position, a bore direction and an angular
 * half-width. A target ingressing from the sea enters the sector early and is
 * detected quickly; a target ingressing from inland, over the town, enters the
 * sector late or never. That detection-latency asymmetry by attack vector is
 * one of the metrics the evaluation is built around, and it emerges from this
 * geometry rather than being coded in.
 *
 * HOW OBSERVATIONS ARE SYNTHESISED
 * ================================
 * Real detection is out of scope. The agent reads the target's ground-truth
 * pose, tests it against the coverage model, and if the target is inside the
 * covered volume, emits an ObsToken with:
 *   - Gaussian position noise (position_noise_m)
 *   - a detection probability, so it occasionally misses a target in coverage
 *     (1 - detection_prob) and occasionally reports a ghost (false_positive_hz)
 *   - a confidence that falls off with range
 *   - a fixed processing latency (latency_s), applied by timestamping the
 *     token in the past rather than by delaying publication, so replays stay
 *     deterministic
 * These are exactly the knobs the evaluation sweeps.
 *
 * Multi-target: the agent subscribes to one ground-truth topic per target and
 * stamps every ObsToken with that target's id. Data association is assumed, a
 * declared simplification.
 *
 * Topics:
 *   Subscribed:
 *     <ground_truth_topic>   (geometry_msgs/PoseStamped)  per target
 *   Published:
 *     /obs_tokens            (guarded_swarms_msgs/ObsToken)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <guarded_swarms_msgs/msg/obs_token.hpp>

#include <cmath>
#include <random>
#include <string>
#include <vector>

using namespace std::chrono_literals;

namespace {
constexpr double kPi = 3.14159265358979323846;
}

class RadarAgentNode : public rclcpp::Node {
 public:
  RadarAgentNode() : Node("radar_agent_node"), rng_(std::random_device{}()) {
    // --- Placement and coverage geometry (simulation model) ---
    pos_x_ = this->declare_parameter<double>("pos_x", 0.0);
    pos_y_ = this->declare_parameter<double>("pos_y", -160.0);
    pos_z_ = this->declare_parameter<double>("pos_z", 20.0);

    // Bore direction as a compass-like bearing in the ENU plane, degrees.
    // 90 deg points along +Y (north, toward the sea in this world).
    bore_deg_ = this->declare_parameter<double>("bore_deg", 90.0);
    // Angular half-width of the sector, degrees. A target is in-sector if the
    // angle between the bore and the line to the target is below this.
    half_angle_deg_ = this->declare_parameter<double>("half_angle_deg", 70.0);

    max_range_m_ = this->declare_parameter<double>("max_range_m", 260.0);
    min_altitude_m_ = this->declare_parameter<double>("min_altitude_m", 2.0);

    // --- Error and rate model (the evaluation knobs) ---
    position_noise_m_ = this->declare_parameter<double>("position_noise_m", 3.0);
    detection_prob_ = this->declare_parameter<double>("detection_prob", 0.95);
    false_positive_hz_ =
        this->declare_parameter<double>("false_positive_hz", 0.0);
    latency_s_ = this->declare_parameter<double>("latency_s", 0.2);
    ttl_s_ = this->declare_parameter<double>("ttl_s", 3.0);
    update_rate_hz_ = this->declare_parameter<double>("update_rate_hz", 5.0);
    confidence_near_ = this->declare_parameter<double>("confidence_near", 0.9);
    confidence_far_ = this->declare_parameter<double>("confidence_far", 0.5);

    // --- Targets ---
    // One ground-truth topic per target, and a matching id per topic. Defaults
    // cover the single intruder in play today; a wave is added by extending
    // both lists.
    target_ids_ = this->declare_parameter<std::vector<std::string>>(
        "target_ids", std::vector<std::string>{"intruder"});
    const auto topics = this->declare_parameter<std::vector<std::string>>(
        "ground_truth_topics",
        std::vector<std::string>{"/intruder/ground_truth"});

    if (topics.size() != target_ids_.size()) {
      RCLCPP_ERROR(this->get_logger(),
                   "ground_truth_topics (%zu) and target_ids (%zu) must have "
                   "the same length. Radar agent will not track anything.",
                   topics.size(), target_ids_.size());
    } else {
      last_pose_.resize(topics.size());
      pose_valid_.assign(topics.size(), false);
      for (size_t i = 0; i < topics.size(); ++i) {
        const size_t idx = i;
        gt_subs_.push_back(
            this->create_subscription<geometry_msgs::msg::PoseStamped>(
                topics[i], 10,
                [this, idx](const geometry_msgs::msg::PoseStamped::SharedPtr m) {
                  last_pose_[idx] = *m;
                  pose_valid_[idx] = true;
                }));
      }
    }

    obs_pub_ = this->create_publisher<guarded_swarms_msgs::msg::ObsToken>(
        "/obs_tokens", 10);

    timer_ = this->create_wall_timer(
        std::chrono::duration<double>(1.0 / update_rate_hz_),
        [this]() { scan(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "RadarAgent (coastal radar)");
    RCLCPP_INFO(this->get_logger(), "  at (%.0f, %.0f, %.0f)", pos_x_, pos_y_,
                pos_z_);
    RCLCPP_INFO(this->get_logger(), "  bore %.0f deg, half-angle %.0f deg",
                bore_deg_, half_angle_deg_);
    RCLCPP_INFO(this->get_logger(), "  range %.0f m, detection_prob %.2f",
                max_range_m_, detection_prob_);
    RCLCPP_INFO(this->get_logger(), "  tracking %zu target(s)",
                target_ids_.size());
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  void scan() {
    for (size_t i = 0; i < pose_valid_.size(); ++i) {
      if (pose_valid_[i]) {
        evaluate_target(i);
      }
    }

    // Ghosts: a Poisson-like false alarm, thinned to this tick.
    if (false_positive_hz_ > 0.0) {
      const double p = false_positive_hz_ / update_rate_hz_;
      if (uniform_(rng_) < p) {
        emit_ghost();
      }
    }
  }

  void evaluate_target(size_t i) {
    const auto& p = last_pose_[i].pose.position;

    const double dx = p.x - pos_x_;
    const double dy = p.y - pos_y_;
    const double dz = p.z - pos_z_;
    const double range = std::sqrt(dx * dx + dy * dy + dz * dz);

    // --- Coverage tests ---
    if (range > max_range_m_) return;
    if (p.z < min_altitude_m_) return;

    // Angle between the bore and the line to the target, in the ENU plane.
    const double bearing = std::atan2(dy, dx);
    const double bore = bore_deg_ * kPi / 180.0;
    double delta = bearing - bore;
    while (delta > kPi) delta -= 2.0 * kPi;
    while (delta < -kPi) delta += 2.0 * kPi;
    if (std::abs(delta) > half_angle_deg_ * kPi / 180.0) return;

    // --- Detection probability: an in-coverage target is sometimes missed ---
    if (uniform_(rng_) > detection_prob_) return;

    // --- Velocity estimate from consecutive poses ---
    double vx = 0.0, vy = 0.0, vz = 0.0;
    const rclcpp::Time now = this->now();
    if (have_prev_[i]) {
      const double dt = (now - prev_time_[i]).seconds();
      if (dt > 1e-3) {
        vx = (p.x - prev_pos_[i].x) / dt;
        vy = (p.y - prev_pos_[i].y) / dt;
        vz = (p.z - prev_pos_[i].z) / dt;
      }
    }
    prev_pos_[i] = p;
    prev_time_[i] = now;
    have_prev_[i] = true;

    // --- Emit ---
    guarded_swarms_msgs::msg::ObsToken tok;
    tok.id = make_id();
    tok.target_id = target_ids_[i];
    tok.source = guarded_swarms_msgs::msg::ObsToken::SOURCE_RADAR;
    tok.kind = guarded_swarms_msgs::msg::ObsToken::KIND_TRACK;

    tok.value = {p.x + noise(), p.y + noise(), p.z + noise(), vx, vy, vz};

    // Confidence falls off linearly with range across the covered span.
    const double frac = std::min(1.0, range / max_range_m_);
    tok.confidence = confidence_near_ + frac * (confidence_far_ - confidence_near_);

    // Latency is expressed by stamping the observation in the past, so that a
    // replay with the same seed is bit-identical regardless of scheduling.
    tok.t = to_msg(now - rclcpp::Duration::from_seconds(latency_s_));
    tok.ttl_s = ttl_s_;

    obs_pub_->publish(tok);
  }

  void emit_ghost() {
    guarded_swarms_msgs::msg::ObsToken tok;
    tok.id = make_id();
    tok.target_id = "";  // a ghost belongs to no real target
    tok.source = guarded_swarms_msgs::msg::ObsToken::SOURCE_RADAR;
    tok.kind = guarded_swarms_msgs::msg::ObsToken::KIND_TRACK;

    // Somewhere plausible inside the sector, at low altitude.
    std::uniform_real_distribution<double> rng_range(20.0, max_range_m_);
    std::uniform_real_distribution<double> rng_ang(
        -half_angle_deg_ * kPi / 180.0, half_angle_deg_ * kPi / 180.0);
    const double r = rng_range(rng_);
    const double a = bore_deg_ * kPi / 180.0 + rng_ang(rng_);
    const double gx = pos_x_ + r * std::cos(a);
    const double gy = pos_y_ + r * std::sin(a);

    tok.value = {gx, gy, 15.0, 0.0, 0.0, 0.0};
    tok.confidence = confidence_far_;
    tok.t = to_msg(this->now() - rclcpp::Duration::from_seconds(latency_s_));
    tok.ttl_s = ttl_s_;

    obs_pub_->publish(tok);
    RCLCPP_DEBUG(this->get_logger(), "radar ghost at (%.0f, %.0f)", gx, gy);
  }

  double noise() {
    std::normal_distribution<double> d(0.0, position_noise_m_);
    return d(rng_);
  }

  std::string make_id() {
    return "radar-" + std::to_string(seq_++);
  }

  static builtin_interfaces::msg::Time to_msg(const rclcpp::Time& t) {
    return builtin_interfaces::msg::Time(t);
  }

  // Geometry
  double pos_x_, pos_y_, pos_z_;
  double bore_deg_, half_angle_deg_, max_range_m_, min_altitude_m_;
  // Error and rate model
  double position_noise_m_, detection_prob_, false_positive_hz_, latency_s_;
  double ttl_s_, update_rate_hz_, confidence_near_, confidence_far_;

  std::vector<std::string> target_ids_;
  std::vector<geometry_msgs::msg::PoseStamped> last_pose_;
  std::vector<bool> pose_valid_;

  std::vector<geometry_msgs::msg::Point> prev_pos_{64};
  std::vector<rclcpp::Time> prev_time_{64};
  std::vector<bool> have_prev_{std::vector<bool>(64, false)};

  std::vector<rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr>
      gt_subs_;
  rclcpp::Publisher<guarded_swarms_msgs::msg::ObsToken>::SharedPtr obs_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  std::mt19937 rng_;
  std::uniform_real_distribution<double> uniform_{0.0, 1.0};
  uint64_t seq_ = 0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<RadarAgentNode>());
  rclcpp::shutdown();
  return 0;
}