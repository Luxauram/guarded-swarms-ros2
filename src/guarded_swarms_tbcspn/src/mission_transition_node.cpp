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
 * @file mission_transition_node.cpp
 *
 * @brief Mission-release transition (T6): the human-in-the-loop.
 *
 * The governed-action-release transition of the coastal scenario. It is the
 * point at which automated evidence accumulation meets human authority:
 *
 *   ConfirmedThreat (from T5)  +  SupervisorAuth (from a human supervisor)
 *       -> InterceptMission
 *
 * WHY THIS TRANSITION MATTERS
 * ===========================
 * Every transition before this one is automatic: sensors, interpretations,
 * joins. This one cannot fire on evidence alone. A ConfirmedThreat, however
 * strong, produces no mission until a supervisor issues an authorisation for
 * that target. This is the architecture's governed action release: no
 * consequential action proceeds without explicit governance.
 *
 * Unlike the joins of T3 and T5, the release does not compare the two tokens'
 * instants: it fires while both a ConfirmedThreat and an authorisation for the
 * same target are valid, each within its own ttl_s. A stale authorisation
 * therefore cannot release a mission against a threat whose track has expired,
 * and a stale threat cannot be released by a late authorisation.
 *
 * THE COUNTERFACTUAL COMES FREE
 * =============================
 * "Authorisation withheld" needs no special code: if no
 * SupervisorAuth arrives, or a DENY arrives, no InterceptMission is produced.
 * The ConfirmedThreat persists in the coordination space, available for
 * inspection and possible later authorisation. A DENY is recorded (logged)
 * rather than being merely the silent absence of a token.
 *
 * PROVENANCE
 * ==========
 * The MissionToken carries the full justification chain: the origins of the
 * ConfirmedThreat, plus the ids of the threat and the authorisation. This is
 * the audit trail the supervisor console shows before the decision and the
 * record of why the swarm acted. authorised_by names the human; an empty
 * authorised_by on a dispatched mission would be a fault, so it is only set
 * from a genuine AUTHORISE token.
 *
 * Topics:
 *   Subscribed:
 *     /interp_tokens   (guarded_swarms_msgs/InterpToken)  -- ConfirmedThreat
 *     /supervisor_auth (guarded_swarms_msgs/SupervisorAuth)     -- supervisor
 *   Published:
 *     /mission_tokens  (guarded_swarms_msgs/MissionToken)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <guarded_swarms_msgs/msg/interp_token.hpp>
#include <guarded_swarms_msgs/msg/mission_token.hpp>
#include <guarded_swarms_msgs/msg/supervisor_auth.hpp>

#include <deque>
#include <string>

using guarded_swarms_msgs::msg::InterpToken;
using guarded_swarms_msgs::msg::MissionToken;
using guarded_swarms_msgs::msg::SupervisorAuth;

namespace {
constexpr int TOKEN_QUEUE_SIZE = 50;
constexpr int AUTH_QUEUE_SIZE = 10;
constexpr int PRUNE_PERIOD_MS = 200;
}  // namespace

class MissionTransitionNode : public rclcpp::Node {
 public:
  MissionTransitionNode() : Node("mission_transition_node") {
    // The interpretation label that authorises release, and the mission type
    // produced. Parameters so the same node can serve other threat/mission
    // pairings later.
    require_label_ = this->declare_parameter<std::string>(
        "require_label", InterpToken::LABEL_CONFIRMED_THREAT);
    mission_type_ = this->declare_parameter<std::string>(
        "mission_type", MissionToken::TYPE_INTERCEPT);

    mission_ttl_s_ = this->declare_parameter<double>("mission_ttl_s", 10.0);

    threat_sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", TOKEN_QUEUE_SIZE,
        [this](const InterpToken::SharedPtr m) { on_interp(m); });
    // Durable QoS for the authorisation: an authorisation is a one-shot,
    // must-not-be-missed event. transient_local means a late-joining T6 still
    // receives the last authorisation a supervisor published, and removes the
    // startup race where a briefly-lived command-line publisher delivers to no
    // one. Depth 10 keeps the recent authorisations, not just the very last.
    rclcpp::QoS auth_qos(AUTH_QUEUE_SIZE);
    auth_qos.transient_local();
    auth_sub_ = this->create_subscription<SupervisorAuth>(
        "/supervisor_auth", auth_qos,
        [this](const SupervisorAuth::SharedPtr m) { on_auth(m); });

    mission_pub_ = this->create_publisher<MissionToken>("/mission_tokens",
                                                        AUTH_QUEUE_SIZE);

    timer_ = this->create_wall_timer(std::chrono::milliseconds(PRUNE_PERIOD_MS),
                                     [this]() { prune(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(),
                "MissionTransitionNode (TB-CSPN T6, human-in-the-loop)");
    RCLCPP_INFO(this->get_logger(), "  %s + SupervisorAuth(authorise)  ->  %s",
                require_label_.c_str(), mission_type_.c_str());
    RCLCPP_INFO(this->get_logger(),
                "  awaiting supervisor authorisation on /supervisor_auth");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  struct Held {
    InterpToken tok;
    rclcpp::Time expiry;
  };
  // A pending authorisation is buffered symmetrically with a threat: the join
  // must fire regardless of which of the two arrives first. Holding only
  // threats (and consuming auths on arrival) loses an authorisation that
  // arrives a moment before its threat is buffered.
  struct HeldAuth {
    SupervisorAuth auth;
    rclcpp::Time expiry;
  };

  /**
   * @brief Buffers a live ConfirmedThreat and attempts a release.
   * @param m Shared pointer to the received @c InterpToken.
   */
  void on_interp(const InterpToken::SharedPtr m) {
    // Only ConfirmedThreat tokens are held; everything else on the shared
    // marking is ignored by this transition.
    if (m->label != require_label_) return;

    Held h;
    h.tok = *m;
    // Build the token's time in the node's own clock domain. Under
    // use_sim_time the node clock is RCL_ROS_TIME, while a default-constructed
    // rclcpp::Time(m->t) is RCL_SYSTEM_TIME; comparing the two throws. Passing
    // the clock type keeps every time comparison in one domain.
    const rcl_clock_type_t clk = this->now().get_clock_type();
    h.expiry =
        rclcpp::Time(m->t, clk) + rclcpp::Duration::from_seconds(m->ttl_s);
    if (h.expiry <= this->now()) return;

    // Keep only the freshest threat per target, so the buffer does not grow
    // while a threat is continuously re-confirmed.
    bool updated = false;
    for (auto& held : threats_) {
      if (held.tok.target_id == m->target_id) {
        held = h;
        updated = true;
        break;
      }
    }
    if (!updated) threats_.push_back(h);

    // A threat has just arrived or refreshed: if an authorisation for this
    // target is already waiting, the join can fire now.
    try_release(m->target_id);
  }

  /**
   * @brief Buffers a live AUTHORISE (or logs a DENY) and attempts a release.
   * @param m Shared pointer to the received @c SupervisorAuth.
   */
  void on_auth(const SupervisorAuth::SharedPtr m) {
    // A denial is recorded and consumed: it is an explicit refusal, not the
    // mere absence of authorisation.
    if (m->decision == SupervisorAuth::DECISION_DENY) {
      RCLCPP_WARN(
          this->get_logger(),
          "Authorisation DENIED for '%s' by '%s' - no mission released.",
          m->target_id.c_str(), m->authorised_by.c_str());
      return;
    }
    if (m->decision != SupervisorAuth::DECISION_AUTHORISE) return;
    if (m->authorised_by.empty()) {
      RCLCPP_WARN(this->get_logger(),
                  "AUTHORISE for '%s' has empty authorised_by - ignored.",
                  m->target_id.c_str());
      return;
    }

    // A manual authorisation (ros2 topic pub) or one issued from the console
    // may leave the timestamp unset. Treat an unset stamp as "now", so the
    // supervisor does not have to reason about the simulation clock: a human
    // decision is taken at the moment it is issued.
    const rcl_clock_type_t clk = this->now().get_clock_type();
    rclcpp::Time auth_t = rclcpp::Time(m->t, clk);
    if (auth_t.nanoseconds() == 0) {
      auth_t = this->now();
    }
    HeldAuth ha;
    ha.auth = *m;
    ha.expiry = auth_t + rclcpp::Duration::from_seconds(m->ttl_s);
    if (ha.expiry <= this->now()) return;

    // Buffer the authorisation (freshest per target) and attempt the join. The
    // threat may already be present (auth arrived second) or may still be on
    // its way (auth arrived first): try_release fires as soon as both are here.
    bool updated = false;
    for (auto& held : auths_) {
      if (held.auth.target_id == m->target_id) {
        held = ha;
        updated = true;
        break;
      }
    }
    if (!updated) auths_.push_back(ha);

    try_release(m->target_id);
  }

  // Fire the join for one target if BOTH a live threat and a live
  // authorisation are buffered for it. Symmetric in threat/auth arrival order.
  // A threat or auth survives in its buffer only while unexpired (prune runs
  // every tick), so mere presence means "valid now" -- the join is on
  // validity windows, never on comparing the two tokens' differing expiry
  // instants.
  void try_release(const std::string& target_id) {
    prune();
    long ti = -1, ai = -1;
    for (size_t i = 0; i < threats_.size(); ++i) {
      if (threats_[i].tok.target_id == target_id) {
        ti = static_cast<long>(i);
        break;
      }
    }
    for (size_t i = 0; i < auths_.size(); ++i) {
      if (auths_[i].auth.target_id == target_id) {
        ai = static_cast<long>(i);
        break;
      }
    }
    if (ti < 0 || ai < 0) return;  // one side missing: wait for it

    release_mission(threats_[ti], auths_[ai].auth);
    threats_.erase(threats_.begin() + ti);
    auths_.erase(auths_.begin() + ai);
  }

  /**
   * @brief Emits the InterceptMission with its full justification chain.
   * @param threat  The releasing ConfirmedThreat.
   * @param auth    The supervisor authorisation.
   */
  void release_mission(const Held& threat, const SupervisorAuth& auth) {
    MissionToken msn;
    msn.mission_id = "mission-" + std::to_string(seq_++);
    msn.type = mission_type_;
    msn.target_id = threat.tok.target_id;
    msn.target_position = threat.tok.position;

    // Full provenance: the threat's own origins, then the threat and the
    // authorisation themselves.
    msn.justification = threat.tok.origin;
    msn.justification.push_back(threat.tok.id);
    msn.justification.push_back("auth:" + auth.authorised_by);

    msn.authorised_by = auth.authorised_by;
    msn.t = this->now();
    msn.ttl_s = mission_ttl_s_;

    mission_pub_->publish(msn);
    RCLCPP_WARN(this->get_logger(),
                "InterceptMission RELEASED for '%s', authorised by '%s' "
                "(%zu justification entries)",
                msn.target_id.c_str(), msn.authorised_by.c_str(),
                msn.justification.size());
  }

  void prune() {
    const rclcpp::Time now = this->now();
    for (auto it = threats_.begin(); it != threats_.end();) {
      if (it->expiry <= now) {
        it = threats_.erase(it);
      } else {
        ++it;
      }
    }
    // Authorisations expire on their own TTL too: a supervisor's decision does
    // not authorise action indefinitely.
    for (auto it = auths_.begin(); it != auths_.end();) {
      if (it->expiry <= now) {
        it = auths_.erase(it);
      } else {
        ++it;
      }
    }
  }

  std::string require_label_, mission_type_;
  double mission_ttl_s_;

  std::deque<Held> threats_;
  std::deque<HeldAuth> auths_;

  rclcpp::Subscription<InterpToken>::SharedPtr threat_sub_;
  rclcpp::Subscription<SupervisorAuth>::SharedPtr auth_sub_;
  rclcpp::Publisher<MissionToken>::SharedPtr mission_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  uint64_t seq_ = 0;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MissionTransitionNode>());
  rclcpp::shutdown();
  return 0;
}