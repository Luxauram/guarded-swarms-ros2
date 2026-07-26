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
 * @brief Mission-release transition (Figure 4, T6): the human-in-the-loop.
 *
 * The governed-action-release transition of the coastal case study in
 * Borghoff, Bottoni and Pareschi (2026), IET Radar, Sonar and Navigation,
 * Figure 4 and Section 3.3. It is the point at which automated evidence
 * accumulation meets human authority:
 *
 *   ConfirmedThreat (from T5)  +  SupervisorAuth (from a human supervisor)
 *       -> InterceptMission
 *
 * WHY THIS TRANSITION MATTERS
 * ===========================
 * Every transition before this one is automatic: sensors, interpretations,
 * joins. This one cannot fire on evidence alone. A ConfirmedThreat, however
 * strong, produces no mission until a supervisor issues an authorisation for
 * that target. This is the architecture's governed action release: "no
 * consequential action proceeds without explicit governance" (Section 5.3).
 *
 * The mechanism is the same time-windowed join used by T3 and T5, so the
 * safety properties carry over: a stale authorisation cannot release a mission
 * against a threat whose track has expired, and a stale threat cannot be
 * released by a late authorisation.
 *
 * THE COUNTERFACTUAL COMES FREE
 * =============================
 * "Authorisation withheld" (Section 5.3) needs no special code: if no
 * SupervisorAuth arrives, or a DENY arrives, no InterceptMission is produced. The
 * ConfirmedThreat persists in the coordination space, available for inspection
 * and possible later authorisation, exactly as the paper describes. A DENY is
 * recorded (logged) rather than being merely the silent absence of a token.
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
 *     /auth_tokens     (guarded_swarms_msgs/SupervisorAuth)     -- supervisor
 *   Published:
 *     /mission_tokens  (guarded_swarms_msgs/MissionToken)
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/rclcpp.hpp>

#include <guarded_swarms_msgs/msg/supervisor_auth.hpp>
#include <guarded_swarms_msgs/msg/interp_token.hpp>
#include <guarded_swarms_msgs/msg/mission_token.hpp>

#include <deque>
#include <string>

using guarded_swarms_msgs::msg::SupervisorAuth;
using guarded_swarms_msgs::msg::InterpToken;
using guarded_swarms_msgs::msg::MissionToken;

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

    sync_threshold_s_ =
        this->declare_parameter<double>("sync_threshold_s", 3.0);
    mission_ttl_s_ = this->declare_parameter<double>("mission_ttl_s", 10.0);

    threat_sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", 50,
        [this](const InterpToken::SharedPtr m) { on_interp(m); });
    auth_sub_ = this->create_subscription<SupervisorAuth>(
        "/auth_tokens", 10,
        [this](const SupervisorAuth::SharedPtr m) { on_auth(m); });

    mission_pub_ =
        this->create_publisher<MissionToken>("/mission_tokens", 10);

    timer_ = this->create_wall_timer(std::chrono::milliseconds(200),
                                     [this]() { prune(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(),
                "MissionTransitionNode (TB-CSPN T6, human-in-the-loop)");
    RCLCPP_INFO(this->get_logger(), "  %s + SupervisorAuth(authorise)  ->  %s",
                require_label_.c_str(), mission_type_.c_str());
    RCLCPP_INFO(this->get_logger(),
                "  awaiting supervisor authorisation on /auth_tokens");
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  struct Held {
    InterpToken tok;
    rclcpp::Time expiry;
  };

  void on_interp(const InterpToken::SharedPtr m) {
    // Only ConfirmedThreat tokens are held; everything else on the shared
    // marking is ignored by this transition.
    if (m->label != require_label_) return;

    Held h;
    h.tok = *m;
    h.expiry = rclcpp::Time(m->t) + rclcpp::Duration::from_seconds(m->ttl_s);
    if (h.expiry <= this->now()) return;

    // Keep only the freshest threat per target, so the buffer does not grow
    // while a threat is continuously re-confirmed.
    for (auto& held : threats_) {
      if (held.tok.target_id == m->target_id) {
        held = h;
        return;
      }
    }
    threats_.push_back(h);
  }

  void on_auth(const SupervisorAuth::SharedPtr m) {
    // A denial is recorded and consumed: it is an explicit refusal, not the
    // mere absence of authorisation.
    if (m->decision == SupervisorAuth::DECISION_DENY) {
      RCLCPP_WARN(this->get_logger(),
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
    rclcpp::Time auth_t = rclcpp::Time(m->t);
    if (auth_t.nanoseconds() == 0) {
      auth_t = this->now();
    }
    const rclcpp::Time auth_expiry =
        auth_t + rclcpp::Duration::from_seconds(m->ttl_s);
    if (auth_expiry <= this->now()) return;

    prune();  // drops any ConfirmedThreat whose validity has elapsed

    // Release against any ConfirmedThreat for this target that is still live.
    // A threat survives in the buffer only while unexpired (prune runs every
    // tick and on entry here), so its mere presence means it is within its own
    // validity window. Comparing the two tokens' expiry INSTANTS would be
    // wrong: they carry different TTLs, so their expiries differ by design even
    // when both are valid right now. What matters is that the threat is live at
    // the moment of authorisation, which is exactly what a non-empty buffer
    // entry guarantees.
    for (size_t i = 0; i < threats_.size(); ++i) {
      if (threats_[i].tok.target_id != m->target_id) continue;
      release_mission(threats_[i], *m);
      threats_.erase(threats_.begin() + i);
      return;
    }

    // Authorisation arrived but no live threat matches it. This is not an
    // error: the threat may have expired, or the operator may have acted on a
    // stale view. Recorded, no mission.
    RCLCPP_WARN(this->get_logger(),
                "AUTHORISE for '%s' by '%s' but no live ConfirmedThreat within "
                "the window - no mission released.",
                m->target_id.c_str(), m->authorised_by.c_str());
  }

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
  }

  std::string require_label_, mission_type_;
  double sync_threshold_s_, mission_ttl_s_;

  std::deque<Held> threats_;

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