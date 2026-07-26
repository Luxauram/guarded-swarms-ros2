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
 * @file candidate_transition_node.cpp
 *
 * @brief Time-windowed join transition (Figure 4, T3): CandidateTarget.
 *
 * The first joining transition of the coastal case study in Borghoff, Bottoni
 * and Pareschi (2026), IET Radar, Sonar and Navigation, Figure 4. Unlike the
 * first-level transitions, which map one observation to one interpretation,
 * T3 fuses two interpretations that arrived from different modalities:
 *
 *   PossibleUAV (from T1, radar)  +  LikelyDroneLink (from T2, RF)
 *       -> CandidateTarget
 *
 * It fires only when both are present, for the same target, concordant, and
 * temporally coherent. This is where the architecture's negative guarantees
 * live: three of the paper's counterfactual trajectories (Section 5.3) are
 * decided here.
 *
 * THE THREE GUARDS
 * ================
 * 1. Same target. Only interpretations carrying the same target_id are fused.
 *
 * 2. Concordance. The two labels must be the concordant pair. If the RF
 *    consultant instead produced LikelyCivilianTraffic, that token never
 *    matches and no candidate is formed. This is the "conflicting
 *    interpretations" counterfactual: the disagreement is preserved in the
 *    net's marking rather than silently resolved.
 *
 * 3. Time window. The paper's rule (Section 3.3): a token generated at t0 is
 *    valid until t0 + ttl, and two tokens may be fused when
 *        abs( (t0' + ttl') - (t0 + ttl) ) <= ths
 *    for a synchronisation threshold ths that depends on the decision. This is
 *    implemented literally. A token whose validity has already elapsed is
 *    dropped from the buffer and cannot contribute -- which is precisely what
 *    makes a late arrival (the "stale EO confirmation" counterfactual, decided
 *    at T5 with the same mechanism) fail to combine.
 *
 * STATE
 * =====
 * T3 is the first transition with memory. It keeps the still-valid tokens of
 * each input label in a small buffer, pruned every tick by TTL. When a new
 * token completes a fusable pair, CandidateTarget is emitted once and the
 * consumed tokens are removed, so a single pair does not fire repeatedly.
 *
 * Topics:
 *   Subscribed:
 *     /interp_tokens  (guarded_swarms_msgs/InterpToken)
 *   Published:
 *     /interp_tokens  (guarded_swarms_msgs/InterpToken)  -- CandidateTarget
 *
 * Publishing back onto the same topic is deliberate: the coordination space is
 * a single shared marking, and downstream transitions (T5) consume the
 * higher-level tokens from it just as this one consumes the lower-level ones.
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <guarded_swarms_msgs/msg/interp_token.hpp>

#include <deque>
#include <string>
#include <vector>

using guarded_swarms_msgs::msg::InterpToken;

class CandidateTransitionNode : public rclcpp::Node {
 public:
  CandidateTransitionNode() : Node("candidate_transition_node") {
    // The concordant input pair. Defaults match T3 in the paper.
    label_a_ = this->declare_parameter<std::string>(
        "label_a", InterpToken::LABEL_POSSIBLE_UAV);
    label_b_ = this->declare_parameter<std::string>(
        "label_b", InterpToken::LABEL_LIKELY_DRONE_LINK);
    emit_label_ = this->declare_parameter<std::string>(
        "emit_label", InterpToken::LABEL_CANDIDATE_TARGET);

    // Synchronisation threshold ths, seconds (paper, Section 3.3).
    sync_threshold_s_ =
        this->declare_parameter<double>("sync_threshold_s", 2.0);
    // Validity of the emitted CandidateTarget.
    emit_ttl_s_ = this->declare_parameter<double>("emit_ttl_s", 4.0);

    sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", 50,
        [this](const InterpToken::SharedPtr m) { on_token(m); });
    pub_ = this->create_publisher<InterpToken>("/interp_tokens", 50);

    // Periodic prune, so expired tokens leave the buffers even when no new
    // token arrives to trigger a fusion attempt.
    timer_ = this->create_wall_timer(std::chrono::milliseconds(200),
                                     [this]() { prune_all(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(),
                "CandidateTransitionNode (TB-CSPN T3, time-windowed join)");
    RCLCPP_INFO(this->get_logger(), "  %s + %s  ->  %s", label_a_.c_str(),
                label_b_.c_str(), emit_label_.c_str());
    RCLCPP_INFO(this->get_logger(), "  sync threshold ths: %.1f s",
                sync_threshold_s_);
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  struct Held {
    InterpToken tok;
    rclcpp::Time expiry;  // t + ttl, the instant the token stops being valid
  };

  void on_token(const InterpToken::SharedPtr m) {
    // This transition ignores its own output and anything that is not one of
    // its two concordant inputs.
    const bool is_a = (m->label == label_a_);
    const bool is_b = (m->label == label_b_);
    if (!is_a && !is_b) return;

    Held h;
    h.tok = *m;
    h.expiry = rclcpp::Time(m->t) + rclcpp::Duration::from_seconds(m->ttl_s);

    // A token that is already stale on arrival contributes nothing.
    if (h.expiry <= this->now()) return;

    if (is_a) {
      buf_a_.push_back(h);
    } else {
      buf_b_.push_back(h);
    }

    try_fuse();
  }

  void try_fuse() {
    prune_all();

    for (size_t i = 0; i < buf_a_.size(); ++i) {
      for (size_t j = 0; j < buf_b_.size(); ++j) {
        const Held& a = buf_a_[i];
        const Held& b = buf_b_[j];

        // Guard 1: same target.
        if (a.tok.target_id != b.tok.target_id) continue;

        // Guard 3: time window, exactly the paper's rule.
        //   abs( (t0' + ttl') - (t0 + ttl) ) <= ths
        const double gap =
            std::abs((b.expiry - a.expiry).seconds());
        if (gap > sync_threshold_s_) continue;

        emit_candidate(a, b);

        // Consume both, so the same pair does not fire again.
        buf_b_.erase(buf_b_.begin() + j);
        buf_a_.erase(buf_a_.begin() + i);
        return;  // one firing per callback; more can fire on the next token
      }
    }
  }

  void emit_candidate(const Held& a, const Held& b) {
    InterpToken tok;
    tok.id = emit_label_ + "-" + std::to_string(seq_++);
    tok.target_id = a.tok.target_id;
    tok.label = emit_label_;

    // Provenance: carry forward the origins of both fused tokens, so the audit
    // chain from mission back to raw observation stays unbroken.
    tok.origin = a.tok.origin;
    tok.origin.insert(tok.origin.end(), b.tok.origin.begin(),
                      b.tok.origin.end());
    tok.origin.push_back(a.tok.id);
    tok.origin.push_back(b.tok.id);

    // Combined confidence: the product, so fusing two uncertain sources does
    // not inflate certainty. A conservative choice; document it.
    tok.confidence = a.tok.confidence * b.tok.confidence;
    tok.t = this->now();
    tok.ttl_s = emit_ttl_s_;

    // Prefer whichever parent carried a position (the radar-derived one does).
    if (a.tok.position.x != 0.0 || a.tok.position.y != 0.0 ||
        a.tok.position.z != 0.0) {
      tok.position = a.tok.position;
    } else {
      tok.position = b.tok.position;
    }

    pub_->publish(tok);
    RCLCPP_INFO(this->get_logger(),
                "%s for '%s' (conf %.2f) from %zu origins",
                emit_label_.c_str(), tok.target_id.c_str(), tok.confidence,
                tok.origin.size());
  }

  void prune_all() {
    prune(buf_a_);
    prune(buf_b_);
  }

  void prune(std::deque<Held>& buf) {
    const rclcpp::Time now = this->now();
    while (!buf.empty() && buf.front().expiry <= now) {
      buf.pop_front();
    }
    // Expiry order is not guaranteed, so sweep the rest too.
    for (auto it = buf.begin(); it != buf.end();) {
      if (it->expiry <= now) {
        it = buf.erase(it);
      } else {
        ++it;
      }
    }
  }

  std::string label_a_, label_b_, emit_label_;
  double sync_threshold_s_, emit_ttl_s_;

  std::deque<Held> buf_a_, buf_b_;

  rclcpp::Subscription<InterpToken>::SharedPtr sub_;
  rclcpp::Publisher<InterpToken>::SharedPtr pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  uint64_t seq_ = 0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CandidateTransitionNode>());
  rclcpp::shutdown();
  return 0;
}