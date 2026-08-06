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
 * @file rf_agent_node.cpp
 *
 * @brief Passive RF monitoring consultant agent.
 *
 * One of the four sensing modalities of the coastal surveillance scenario in
 * Borghoff, Bottoni and Pareschi (2026), IET Radar, Sonar and Navigation,
 * Section 5.1: "passive RF monitoring equipment to identify possible drone
 * communication signals".
 *
 * WHAT MAKES THIS MODALITY DIFFERENT
 * ==================================
 * The RF agent does NOT localise. It emits ObsToken(KIND_SIGNATURE): it can
 * tell that a radio control link is present and characterise it (centre
 * frequency, bandwidth, received power), but not where the emitter is. This is
 * the information that lets a PossibleUAV become a LikelyDroneLink: the radar
 * says something is there, the RF says it is a drone.
 *
 * Because it is passive and omnidirectional, it has no sector: coverage is a
 * simple range test from the monitoring mast. But it only sees a target that
 * is actually transmitting. A target under radio silence (intruder parameter
 * transmitting:=false) is invisible to it, which is one of the counterfactual
 * trajectories of Section 5.3: without the RF confirmation the interpretation
 * chain cannot reach LikelyDroneLink and the mission is never synthesised.
 *
 * The coverage geometry, the signature values and the error model are a
 * simulation model, not specified by the paper. State this in the thesis.
 *
 * Topics:
 *   Subscribed:
 *     <ground_truth_topic>    (geometry_msgs/PoseStamped)  per target
 *     <transmitting_topic>    (std_msgs/Bool)              per target
 *   Published:
 *     /obs_tokens             (guarded_swarms_msgs/ObsToken)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <guarded_swarms_msgs/msg/obs_token.hpp>
#include <std_msgs/msg/bool.hpp>

#include <cmath>
#include <random>
#include <string>
#include <vector>

namespace {
constexpr int kQueueSize = 10;
// RF signature noise: centre-frequency jitter (Hz) and RSSI jitter (dB).
constexpr double kFreqNoiseHz = 1.0e6;
constexpr double kRssiNoiseDb = 1.5;
// Free-space-like path-loss coefficient for the log-distance RSSI model.
constexpr double kPathLossCoeff = 20.0;
// Ghost false alarm: nominal received power (dBm) and confidence discount.
constexpr double kGhostRssiDbm = -90.0;
constexpr double kGhostConfidenceFactor = 0.5;
}

class RfAgentNode : public rclcpp::Node {
 public:
  RfAgentNode() : Node("rf_agent_node"), rng_(std::random_device{}()) {
    // Placement (simulation model). The mast sits inland, well away from the
    // radar so the two modalities are visually distinct in the demo.
    pos_x_ = this->declare_parameter<double>("pos_x", -150.0);
    pos_y_ = this->declare_parameter<double>("pos_y", -158.0);
    pos_z_ = this->declare_parameter<double>("pos_z", 28.0);

    // Omnidirectional: coverage is a plain range test, no sector.
    max_range_m_ = this->declare_parameter<double>("max_range_m", 320.0);

    // Signature the modality reports for a detected drone link. Fixed nominal
    // values with noise: the study is about coordination, not RF analysis.
    centre_freq_hz_ =
        this->declare_parameter<double>("centre_freq_hz", 2.44e9);
    bandwidth_hz_ = this->declare_parameter<double>("bandwidth_hz", 2.0e7);
    tx_power_dbm_ = this->declare_parameter<double>("tx_power_dbm", 20.0);

    detection_prob_ = this->declare_parameter<double>("detection_prob", 0.9);
    false_positive_hz_ =
        this->declare_parameter<double>("false_positive_hz", 0.0);
    latency_s_ = this->declare_parameter<double>("latency_s", 0.3);
    ttl_s_ = this->declare_parameter<double>("ttl_s", 3.0);
    update_rate_hz_ = this->declare_parameter<double>("update_rate_hz", 4.0);
    confidence_ = this->declare_parameter<double>("confidence", 0.7);

    target_ids_ = this->declare_parameter<std::vector<std::string>>(
        "target_ids", std::vector<std::string>{"intruder"});
    const auto gt_topics = this->declare_parameter<std::vector<std::string>>(
        "ground_truth_topics",
        std::vector<std::string>{"/intruder/ground_truth"});
    const auto tx_topics = this->declare_parameter<std::vector<std::string>>(
        "transmitting_topics",
        std::vector<std::string>{"/intruder/transmitting"});

    const size_t n = target_ids_.size();
    if (gt_topics.size() != n || tx_topics.size() != n) {
      RCLCPP_ERROR(this->get_logger(),
                   "target_ids (%zu), ground_truth_topics (%zu) and "
                   "transmitting_topics (%zu) must match.",
                   n, gt_topics.size(), tx_topics.size());
    } else {
      last_pose_.resize(n);
      pose_valid_.assign(n, false);
      transmitting_.assign(n, false);
      for (size_t i = 0; i < n; ++i) {
        const size_t idx = i;
        gt_subs_.push_back(
            this->create_subscription<geometry_msgs::msg::PoseStamped>(
                gt_topics[i], kQueueSize,
                [this, idx](const geometry_msgs::msg::PoseStamped::SharedPtr m) {
                  last_pose_[idx] = *m;
                  pose_valid_[idx] = true;
                }));
        tx_subs_.push_back(this->create_subscription<std_msgs::msg::Bool>(
            tx_topics[i], kQueueSize,
            [this, idx](const std_msgs::msg::Bool::SharedPtr m) {
              transmitting_[idx] = m->data;
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
    RCLCPP_INFO(this->get_logger(), "RfAgent (passive RF monitoring)");
    RCLCPP_INFO(this->get_logger(), "  at (%.0f, %.0f, %.0f), range %.0f m",
                pos_x_, pos_y_, pos_z_, max_range_m_);
    RCLCPP_INFO(this->get_logger(),
                "  omnidirectional; sees transmitting targets only");
    RCLCPP_INFO(this->get_logger(), "  tracking %zu target(s)", n);
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:

  /** @brief Scans every valid target, then rolls for a ghost false alarm. */
  void scan() {
    for (size_t i = 0; i < pose_valid_.size(); ++i) {
      if (pose_valid_[i]) {
        evaluate_target(i);
      }
    }
    if (false_positive_hz_ > 0.0) {
      const double p = false_positive_hz_ / update_rate_hz_;
      if (uniform_(rng_) < p) emit_ghost();
    }
  }

  /**
   * @brief Emits a signature ObsToken if target i is transmitting and in range.
   * @param i  Index into target_ids_ / last_pose_.
   */
  void evaluate_target(size_t i) {
    // Silent target: nothing to detect. This is the radio-silence
    // counterfactual.
    if (!transmitting_[i]) return;

    const auto& p = last_pose_[i].pose.position;
    const double dx = p.x - pos_x_;
    const double dy = p.y - pos_y_;
    const double dz = p.z - pos_z_;
    const double range = std::sqrt(dx * dx + dy * dy + dz * dz);

    if (range > max_range_m_) return;
    if (uniform_(rng_) > detection_prob_) return;

    guarded_swarms_msgs::msg::ObsToken tok;
    tok.id = "rf-" + std::to_string(seq_++);
    tok.target_id = target_ids_[i];
    tok.source = guarded_swarms_msgs::msg::ObsToken::SOURCE_RF;
    tok.kind = guarded_swarms_msgs::msg::ObsToken::KIND_SIGNATURE;

    // No position: centre frequency, bandwidth, received power. RSSI falls off
    // with range by a simple log model, enough to be range-dependent without
    // pretending to be a propagation study.
    std::normal_distribution<double> f_noise(0.0, kFreqNoiseHz);
    std::normal_distribution<double> p_noise(0.0, kRssiNoiseDb);
    const double rssi =
        tx_power_dbm_ - kPathLossCoeff * std::log10(std::max(range, 1.0)) +
        p_noise(rng_);
    tok.value = {centre_freq_hz_ + f_noise(rng_), bandwidth_hz_, rssi};

    tok.confidence = confidence_;
    tok.t = builtin_interfaces::msg::Time(
        this->now() - rclcpp::Duration::from_seconds(latency_s_));
    tok.ttl_s = ttl_s_;
    obs_pub_->publish(tok);
  }

  /** @brief Emits a ghost signature: a false alarm with no real target. */
  void emit_ghost() {
    guarded_swarms_msgs::msg::ObsToken tok;
    tok.id = "rf-" + std::to_string(seq_++);
    tok.target_id = "";
    tok.source = guarded_swarms_msgs::msg::ObsToken::SOURCE_RF;
    tok.kind = guarded_swarms_msgs::msg::ObsToken::KIND_SIGNATURE;
    tok.value = {centre_freq_hz_, bandwidth_hz_, kGhostRssiDbm};
    tok.confidence = confidence_ * kGhostConfidenceFactor;
    tok.t = builtin_interfaces::msg::Time(
        this->now() - rclcpp::Duration::from_seconds(latency_s_));
    tok.ttl_s = ttl_s_;
    obs_pub_->publish(tok);
  }

  double pos_x_, pos_y_, pos_z_, max_range_m_;
  double centre_freq_hz_, bandwidth_hz_, tx_power_dbm_;
  double detection_prob_, false_positive_hz_, latency_s_, ttl_s_;
  double update_rate_hz_, confidence_;

  std::vector<std::string> target_ids_;
  std::vector<geometry_msgs::msg::PoseStamped> last_pose_;
  std::vector<bool> pose_valid_;
  std::vector<bool> transmitting_;

  std::vector<rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr>
      gt_subs_;
  std::vector<rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr> tx_subs_;
  rclcpp::Publisher<guarded_swarms_msgs::msg::ObsToken>::SharedPtr obs_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  std::mt19937 rng_;
  std::uniform_real_distribution<double> uniform_{0.0, 1.0};
  uint64_t seq_ = 0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<RfAgentNode>());
  rclcpp::shutdown();
  return 0;
}
