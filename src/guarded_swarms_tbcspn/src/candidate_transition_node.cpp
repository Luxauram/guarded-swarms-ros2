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
 * @brief Time-windowed join transition (T3, and T5 with other labels).
 *
 * The first joining transition of the coastal scenario. Unlike the
 * first-level transitions, which map one observation to one interpretation,
 * T3 fuses two interpretations that arrived from different modalities:
 *
 *   PossibleUAV (from T1, radar)  +  LikelyDroneLink (from T2, RF)
 *       -> CandidateTarget
 *
 * It fires only when both are present, for the same target, concordant, and
 * temporally coherent. This is where the architecture's negative guarantees
 * live: the conflicting-interpretation counterfactual is decided here, and the
 * stale-confirmation one at T5, by the same code.
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
 * 3. Time window. A token generated at t0 is
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
#include <deque>
#include <guarded_swarms_msgs/msg/interp_token.hpp>
#include <rclcpp/rclcpp.hpp>
#include <string>
#include <vector>

using guarded_swarms_msgs::msg::InterpToken;

namespace {
// Larger queue for the shared marking: transitions publish back onto
// /interp_tokens, so the buffer must absorb bursts without dropping tokens.
constexpr int TOKEN_QUEUE_SIZE = 50;
// Period of the periodic TTL prune (ms).
constexpr int PRUNE_PERIOD_MS = 200;
}  // namespace

class CandidateTransitionNode : public rclcpp::Node {
 public:
  CandidateTransitionNode() : Node("candidate_transition_node") {
    // The concordant input pair. The defaults are those of T3.
    label_a_ = this->declare_parameter<std::string>(
        "label_a", InterpToken::LABEL_POSSIBLE_UAV);
    label_b_ = this->declare_parameter<std::string>(
        "label_b", InterpToken::LABEL_LIKELY_DRONE_LINK);
    emit_label_ = this->declare_parameter<std::string>(
        "emit_label", InterpToken::LABEL_CANDIDATE_TARGET);
    // Synchronisation threshold ths, seconds.
    sync_threshold_s_ =
        this->declare_parameter<double>("sync_threshold_s", 2.0);
    // Validity of the emitted CandidateTarget.
    emit_ttl_s_ = this->declare_parameter<double>("emit_ttl_s", 4.0);
    sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", TOKEN_QUEUE_SIZE,
        [this](const InterpToken::SharedPtr m) { on_token(m); });
    pub_ =
        this->create_publisher<InterpToken>("/interp_tokens", TOKEN_QUEUE_SIZE);
    // Periodic prune, so expired tokens leave the buffers even when no new
    // token arrives to trigger a fusion attempt.
    timer_ = this->create_wall_timer(std::chrono::milliseconds(PRUNE_PERIOD_MS),
                                     [this]() { prune_all(); });
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(),
                "CandidateTransitionNode (TB-CSPN time-windowed join)");
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

  /**
   * @brief Buffers a valid input token and attempts a fusion.
   * @param m Shared pointer to the received @c InterpToken.
   */
  void on_token(const InterpToken::SharedPtr m) {
    // This transition ignores its own output and anything that is not one of
    // its two concordant inputs.
    const bool is_a = (m->label == label_a_);
    const bool is_b = (m->label == label_b_);
    if (!is_a && !is_b) return;
    Held h;
    h.tok = *m;
    // Build the token's time in the node's own clock domain. Under
    // use_sim_time the node clock is RCL_ROS_TIME, while a default-constructed
    // rclcpp::Time(m->t) is RCL_SYSTEM_TIME; comparing the two throws. Passing
    // the clock type keeps every time comparison in one domain. (Same fix as
    // in mission_transition_node / T6.)
    const rcl_clock_type_t clk = this->now().get_clock_type();
    h.expiry =
        rclcpp::Time(m->t, clk) + rclcpp::Duration::from_seconds(m->ttl_s);
    // A token that is already stale on arrival contributes nothing. This is the
    // structural mechanism of the stale-EO counterfactual: a
    // ConfirmedAerialObject interpreted from a long-delayed EO observation
    // carries an old t, so its validity has already elapsed and it is dropped
    // here, before it can fuse.
    if (h.expiry <= this->now()) return;
    if (is_a) {
      buf_a_.push_back(h);
    } else {
      buf_b_.push_back(h);
    }
    try_fuse();
  }

  /** @brief Fuses the first concordant, same-target, in-window pair found. */
  void try_fuse() {
    prune_all();
    for (size_t i = 0; i < buf_a_.size(); ++i) {
      for (size_t j = 0; j < buf_b_.size(); ++j) {
        const Held& a = buf_a_[i];
        const Held& b = buf_b_[j];
        // Guard 1: same target.
        if (a.tok.target_id != b.tok.target_id) continue;
        // Guard 3: time window.
        //   abs( (t0' + ttl') - (t0 + ttl) ) <= ths
        const double gap = std::abs((b.expiry - a.expiry).seconds());
        if (gap > sync_threshold_s_) continue;
        emit_candidate(a, b);
        // Consume both, so the same pair does not fire again.
        buf_b_.erase(buf_b_.begin() + j);
        buf_a_.erase(buf_a_.begin() + i);
        return;  // one firing per callback; more can fire on the next token
      }
    }
  }

  /**
   * @brief Emits the fused CandidateTarget, carrying forward provenance.
   * @param a,b  The two fused parent tokens.
   */
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
    // The fused token is generated now, but its validity should reflect the
    // age of the evidence it summarises: it is emitted with the node's clock
    // and its own ttl. Downstream (T5) applies the same windowed rule again.
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
    RCLCPP_INFO(this->get_logger(), "%s for '%s' (conf %.2f) from %zu origins",
                emit_label_.c_str(), tok.target_id.c_str(), tok.confidence,
                tok.origin.size());
  }

  /** @brief Prunes expired tokens from both input buffers. */
  void prune_all() {
    prune(buf_a_);
    prune(buf_b_);
  }

  /**
   * @brief Removes tokens whose validity has elapsed from one buffer.
   * @param buf  Input buffer to prune in place.
   */
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
