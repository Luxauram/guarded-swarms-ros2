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
 * @file acoustic_agent_node.cpp
 *
 * @brief Acoustic buoy network consultant agent.
 *
 * One of the four sensing modalities of the coastal surveillance scenario in
 * Borghoff, Bottoni and Pareschi (2026), IET Radar, Sonar and Navigation,
 * Section 5.1: "a network of acoustic sensors deployed on buoys near the
 * shoreline".
 *
 * WHAT MAKES THIS MODALITY DIFFERENT
 * ==================================
 * The acoustic network does NOT localise either. Each buoy hears a target and
 * reports a BEARING to it, not a position. The agent emits
 * ObsToken(KIND_BEARING): azimuth and elevation from the buoy that heard the
 * target, plus a coarse range estimate. Bearings from several buoys could in
 * principle be triangulated, but that fusion is the job of the interpretation
 * transitions, not of this agent.
 *
 * The buoys sit in the water near the shore, so the network only covers
 * targets over the sea and at short range: an inland ingress is inaudible to
 * it. Together with the sea-facing radar sector, this is what makes the
 * detection picture depend on the attack vector.
 *
 * The buoy positions, the short range and the error model are a simulation
 * model, not specified by the paper. State this in the thesis.
 *
 * Topics:
 *   Subscribed:
 *     <ground_truth_topic>    (geometry_msgs/PoseStamped)  per target
 *   Published:
 *     /obs_tokens             (guarded_swarms_msgs/ObsToken)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <guarded_swarms_msgs/msg/obs_token.hpp>

#include <array>
#include <cmath>
#include <cstdint>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double kPi = 3.14159265358979323846;
constexpr int kQueueSize = 10;
// How much confidence falls off at max range (fraction of the base value).
constexpr double kConfidenceRangeFalloff = 0.4;
// The generator takes 32-bit seeds.
constexpr int64_t kMaxSeed = 4294967295;
}

class AcousticAgentNode : public rclcpp::Node {
 public:
  AcousticAgentNode() : Node("acoustic_agent_node") {
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

    // Buoy positions (simulation model). Flattened x,y,x,y,... in world ENU.
    // Defaults match the inner ring of buoys in the generated coastal world.
    const auto flat = this->declare_parameter<std::vector<double>>(
        "buoy_positions",
        std::vector<double>{-130, 72, -70, 64, -10, 76, 55, 66, 120, 70});
    for (size_t i = 0; i + 1 < flat.size(); i += 2) {
      buoys_.push_back({flat[i], flat[i + 1]});
    }

    // Short range: hydroacoustic detection near the surface is limited, and
    // this is what keeps the modality sea-only.
    max_range_m_ = this->declare_parameter<double>("max_range_m", 90.0);

    bearing_noise_deg_ =
        this->declare_parameter<double>("bearing_noise_deg", 4.0);
    range_noise_m_ = this->declare_parameter<double>("range_noise_m", 12.0);
    detection_prob_ = this->declare_parameter<double>("detection_prob", 0.85);
    latency_s_ = this->declare_parameter<double>("latency_s", 0.5);
    ttl_s_ = this->declare_parameter<double>("ttl_s", 3.0);
    update_rate_hz_ = this->declare_parameter<double>("update_rate_hz", 3.0);
    confidence_ = this->declare_parameter<double>("confidence", 0.6);

    target_ids_ = this->declare_parameter<std::vector<std::string>>(
        "target_ids", std::vector<std::string>{"intruder"});
    const auto gt_topics = this->declare_parameter<std::vector<std::string>>(
        "ground_truth_topics",
        std::vector<std::string>{"/intruder/ground_truth"});

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
                [this, idx](const geometry_msgs::msg::PoseStamped::SharedPtr m) {
                  last_pose_[idx] = *m;
                  pose_valid_[idx] = true;
                }));
      }
    }

    obs_pub_ = this->create_publisher<guarded_swarms_msgs::msg::ObsToken>(
        "/obs_tokens", kQueueSize);

    timer_ = this->create_wall_timer(
        std::chrono::duration<double>(1.0 / update_rate_hz_),
        [this]() { scan(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "AcousticAgent (buoy network)");
    RCLCPP_INFO(this->get_logger(), "  %zu buoys, range %.0f m each",
                buoys_.size(), max_range_m_);
    RCLCPP_INFO(this->get_logger(), "  emits BEARING, sea coverage only");
    RCLCPP_INFO(this->get_logger(), "  tracking %zu target(s)", n);
    RCLCPP_INFO(this->get_logger(), "  seed %lu%s",
                static_cast<unsigned long>(seed_),
                seed_drawn_ ? " (drawn at random: seed parameter was 0)" : "");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  /** @brief Scans every target with a valid ground-truth pose. */
  void scan() {
    for (size_t i = 0; i < pose_valid_.size(); ++i) {
      if (pose_valid_[i]) {
        evaluate_target(i);
      }
    }
  }

  /**
   * @brief Emits a bearing ObsToken if a buoy hears target i.
   * @param i  Index into target_ids_ / last_pose_.
   */
  void evaluate_target(size_t i) {
    const auto& p = last_pose_[i].pose.position;

    // Find the closest buoy that can hear the target.
    int best = -1;
    double best_range = max_range_m_;
    for (size_t b = 0; b < buoys_.size(); ++b) {
      const double dx = p.x - buoys_[b][0];
      const double dy = p.y - buoys_[b][1];
      const double dz = p.z;  // buoys sit at the surface, z = 0
      const double r = std::sqrt(dx * dx + dy * dy + dz * dz);
      if (r < best_range) {
        best_range = r;
        best = static_cast<int>(b);
      }
    }
    if (best < 0) return;  // out of range of every buoy
    if (uniform_(rng_) > detection_prob_) return;

    const double dx = p.x - buoys_[best][0];
    const double dy = p.y - buoys_[best][1];
    const double dz = p.z;

    std::normal_distribution<double> b_noise(
        0.0, bearing_noise_deg_ * kPi / 180.0);
    std::normal_distribution<double> r_noise(0.0, range_noise_m_);

    const double bearing = std::atan2(dy, dx) + b_noise(rng_);
    const double horiz = std::sqrt(dx * dx + dy * dy);
    const double elevation = std::atan2(dz, horiz) + b_noise(rng_);
    const double range_est = best_range + r_noise(rng_);

    guarded_swarms_msgs::msg::ObsToken tok;
    tok.id = "acoustic-" + std::to_string(seq_++);
    tok.target_id = target_ids_[i];
    tok.source = guarded_swarms_msgs::msg::ObsToken::SOURCE_ACOUSTIC;
    tok.kind = guarded_swarms_msgs::msg::ObsToken::KIND_BEARING;

    // bearing_rad, elevation_rad, range_m (from the reporting buoy)
    tok.value = {bearing, elevation, range_est};

    // Confidence is higher for a closer target.
    const double frac = std::min(1.0, best_range / max_range_m_);
    tok.confidence = confidence_ * (1.0 - kConfidenceRangeFalloff * frac);
    tok.t = builtin_interfaces::msg::Time(
        this->now() - rclcpp::Duration::from_seconds(latency_s_));
    tok.ttl_s = ttl_s_;
    obs_pub_->publish(tok);
  }

  double max_range_m_, bearing_noise_deg_, range_noise_m_;
  double detection_prob_, latency_s_, ttl_s_, update_rate_hz_, confidence_;

  std::vector<std::array<double, 2>> buoys_;
  std::vector<std::string> target_ids_;
  std::vector<geometry_msgs::msg::PoseStamped> last_pose_;
  std::vector<bool> pose_valid_;

  std::vector<rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr>
      gt_subs_;
  rclcpp::Publisher<guarded_swarms_msgs::msg::ObsToken>::SharedPtr obs_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  std::mt19937 rng_;
  uint32_t seed_ = 0;        // the seed in use, logged at start-up
  bool seed_drawn_ = false;  // drawn at random (seed parameter was 0)
  std::uniform_real_distribution<double> uniform_{0.0, 1.0};
  uint64_t seq_ = 0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<AcousticAgentNode>());
  rclcpp::shutdown();
  return 0;
}
