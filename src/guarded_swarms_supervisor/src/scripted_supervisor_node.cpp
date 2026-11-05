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
 * @file scripted_supervisor_node.cpp
 *
 * @brief Scripted supervisor: the human decision of T6, played by a declared
 *        policy in automated runs.
 *
 * The mission-release transition (T6) releases an InterceptMission only when a
 * ConfirmedThreat and a SupervisorAuth for the same target are both live. In
 * an interactive run the authorisation comes from a person, through the
 * supervisor console. In an experiment campaign it must come from something
 * repeatable: this node.
 *
 * THE POLICY
 * ==========
 *   - Watch /interp_tokens for ConfirmedThreat tokens.
 *   - At the FIRST ConfirmedThreat of a target, start a timer of
 *     decision_delay_s seconds of SIMULATED time: the supervisor's decision
 *     time (0 = immediate).
 *   - When it expires, issue one decision for that target on /supervisor_auth:
 *     authorise, deny, or none (no answer at all).
 *
 * One decision per target per run. T6 consumes an authorisation when it
 * releases a mission, so one decision releases at most one mission. A later
 * ConfirmedThreat for a target already decided is ignored.
 *
 * The delay starts when the ConfirmedThreat reaches the supervisor, measured on
 * the simulation clock: a supervisor can only start deciding once the threat
 * is in front of them.
 *
 * WHY A NODE AND NOT A COMMAND-LINE PUBLISHER
 * ===========================================
 * The thesis campaign authorised with `ros2 topic pub` from the test script,
 * after three `gz model` calls. That put 12-15 s of test-harness overhead
 * between the threat and the authorisation, and a publisher that lived only a
 * few seconds could miss T6 altogether. This node removes both problems:
 *
 *   - the delay is a parameter, measured on the simulation clock, so it is the
 *     supervisor's decision time and nothing else;
 *   - the publisher lives for the whole run with RELIABLE + TRANSIENT_LOCAL
 *     QoS, the same as T6's subscription, so a decision cannot be lost;
 *   - the decision carries its simulated timestamp, so the instant of the
 *     authorisation is recorded in the bag (the command-line stub left it 0).
 *
 * Topics:
 *   Subscribed:
 *     /interp_tokens   (guarded_swarms_msgs/InterpToken)     -- ConfirmedThreat
 *   Published:
 *     /supervisor_auth (guarded_swarms_msgs/SupervisorAuth)  -- the decision
 *
 * Parameters:
 *   decision          authorise | deny | none                 [authorise]
 *   decision_delay_s  decision time, simulated seconds, >= 0  [0.0]
 *   ttl_s             validity of the decision, seconds, > 0  [15.0]
 *   authorised_by     identity recorded in the decision       [scripted_supervisor]
 *   require_label     the label that calls for a decision     [ConfirmedThreat]
 *
 * @author Luca D'Aurizio
 */

#include <rclcpp/create_timer.hpp>
#include <rclcpp/rclcpp.hpp>

#include <guarded_swarms_msgs/msg/interp_token.hpp>
#include <guarded_swarms_msgs/msg/supervisor_auth.hpp>

#include <chrono>
#include <exception>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>

using guarded_swarms_msgs::msg::InterpToken;
using guarded_swarms_msgs::msg::SupervisorAuth;

namespace {
constexpr int TOKEN_QUEUE_SIZE = 50;
constexpr int AUTH_QUEUE_SIZE = 10;  // same depth as T6's subscription
constexpr int CHECK_PERIOD_MS = 50;  // how often pending decisions are checked
// "No answer": the supervisor never decides. Not a SupervisorAuth constant,
// because nothing is published for it.
constexpr char DECISION_NONE[] = "none";
}  // namespace

class ScriptedSupervisorNode : public rclcpp::Node {
 public:
  ScriptedSupervisorNode() : Node("scripted_supervisor") {
    decision_ = this->declare_parameter<std::string>(
        "decision", SupervisorAuth::DECISION_AUTHORISE);
    delay_s_ = this->declare_parameter<double>("decision_delay_s", 0.0);
    ttl_s_ = this->declare_parameter<double>("ttl_s", 15.0);
    authorised_by_ = this->declare_parameter<std::string>(
        "authorised_by", "scripted_supervisor");
    require_label_ = this->declare_parameter<std::string>(
        "require_label", InterpToken::LABEL_CONFIRMED_THREAT);
    validate_parameters();

    // RELIABLE + TRANSIENT_LOCAL, as T6's subscription: a decision is a
    // must-not-be-missed event, and since this publisher lives for the whole
    // run, a late-joining T6 or recorder still receives it.
    rclcpp::QoS auth_qos(AUTH_QUEUE_SIZE);
    auth_qos.reliable().transient_local();
    auth_pub_ =
        this->create_publisher<SupervisorAuth>("/supervisor_auth", auth_qos);

    interp_sub_ = this->create_subscription<InterpToken>(
        "/interp_tokens", TOKEN_QUEUE_SIZE,
        [this](const InterpToken::SharedPtr m) { on_interp(m); });

    // Pending decisions are checked every CHECK_PERIOD_MS of simulated time,
    // against the node clock (simulated time under use_sim_time). A decision
    // therefore fires when simulated time reaches its due instant, within one
    // check period, whatever the real-time factor of the run.
    timer_ = rclcpp::create_timer(
        this, this->get_clock(),
        rclcpp::Duration::from_seconds(CHECK_PERIOD_MS / 1000.0),
        [this]() { decide_due(); });

    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(),
                "ScriptedSupervisorNode (stands in for the supervisor of T6)");
    RCLCPP_INFO(this->get_logger(),
                "  on the first %s of each target: '%s' after %.2f s (sim)",
                require_label_.c_str(), decision_.c_str(), delay_s_);
    RCLCPP_INFO(this->get_logger(), "  valid %.1f s, issued as '%s'", ttl_s_,
                authorised_by_.c_str());
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }

 private:
  struct Pending {
    rclcpp::Time due;
    bool decided = false;
  };

  /**
   * @brief Rejects a configuration that would make a run meaningless.
   * @throws std::invalid_argument naming the offending parameter.
   */
  void validate_parameters() const {
    if (decision_ != SupervisorAuth::DECISION_AUTHORISE &&
        decision_ != SupervisorAuth::DECISION_DENY &&
        decision_ != DECISION_NONE) {
      throw std::invalid_argument(
          "decision must be 'authorise', 'deny' or 'none', got '" + decision_ +
          "'");
    }
    if (delay_s_ < 0.0) {
      throw std::invalid_argument("decision_delay_s must be >= 0");
    }
    if (ttl_s_ <= 0.0) {
      throw std::invalid_argument("ttl_s must be > 0");
    }
    if (authorised_by_.empty()) {
      throw std::invalid_argument("authorised_by must not be empty");
    }
  }

  /**
   * @brief Starts the decision timer at the first threat of each target.
   * @param m Shared pointer to the received @c InterpToken.
   */
  void on_interp(const InterpToken::SharedPtr m) {
    if (m->label != require_label_) return;
    // One decision per target per run: a target already pending or decided
    // does not restart the timer.
    if (targets_.count(m->target_id) > 0) return;

    Pending& p = targets_[m->target_id];
    p.due = this->now() + rclcpp::Duration::from_seconds(delay_s_);
    RCLCPP_INFO(this->get_logger(),
                "%s for '%s' received; decision due in %.2f s (sim)",
                require_label_.c_str(), m->target_id.c_str(), delay_s_);

    if (delay_s_ <= 0.0) decide(m->target_id, p);
  }

  /**
   * @brief Issues every decision whose due instant has been reached.
   */
  void decide_due() {
    const rclcpp::Time now = this->now();
    for (auto& [target_id, p] : targets_) {
      if (!p.decided && now >= p.due) decide(target_id, p);
    }
  }

  /**
   * @brief Issues the decision for one target, once.
   * @param target_id The target the decision refers to.
   * @param p         Its pending entry, marked as decided.
   */
  void decide(const std::string& target_id, Pending& p) {
    p.decided = true;
    if (decision_ == DECISION_NONE) {
      RCLCPP_WARN(this->get_logger(),
                  "Decision for '%s': none - no authorisation issued.",
                  target_id.c_str());
      return;
    }

    SupervisorAuth auth;
    auth.target_id = target_id;
    auth.authorised_by = authorised_by_;
    auth.decision = decision_;
    auth.t = this->now();
    auth.ttl_s = ttl_s_;
    auth_pub_->publish(auth);
    RCLCPP_WARN(this->get_logger(),
                "Decision for '%s': %s (issued as '%s', valid %.1f s)",
                target_id.c_str(), decision_.c_str(), authorised_by_.c_str(),
                ttl_s_);
  }

  std::string decision_, authorised_by_, require_label_;
  double delay_s_, ttl_s_;

  std::map<std::string, Pending> targets_;

  rclcpp::Subscription<InterpToken>::SharedPtr interp_sub_;
  rclcpp::Publisher<SupervisorAuth>::SharedPtr auth_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  int rc = 0;
  try {
    rclcpp::spin(std::make_shared<ScriptedSupervisorNode>());
  } catch (const std::exception& e) {
    // A rejected parameter (wrong value or wrong type) stops the node here,
    // with the reason, instead of letting a misconfigured run go ahead.
    RCLCPP_FATAL(rclcpp::get_logger("scripted_supervisor"), "Stopped: %s",
                 e.what());
    rc = 1;
  }
  rclcpp::shutdown();
  return rc;
}