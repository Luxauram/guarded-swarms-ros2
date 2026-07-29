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
 * @file interpretation_node.cpp
 *
 * @brief First-level TB-CSPN interpretation transition (Figure 4, T1 / T2).
 *
 * The two first-level transitions of the coastal case study in Borghoff,
 * Bottoni and Pareschi (2026), IET Radar, Sonar and Navigation, Figure 4, have
 * the same shape: a single ObsToken of one modality is read, a guard on its
 * confidence is applied, and if it passes an InterpToken carrying a semantic
 * label is produced.
 *   T1: a low-altitude radar track   -> PossibleUAV
 *   T2: a drone-telemetry RF emission -> LikelyDroneLink
 *
 * Because the two are structurally identical, this is one parametric node
 * instantiated twice, rather than two copies of the same logic. The source it
 * listens to, the label it emits, and the confidence guard are parameters.
 *
 * WHAT A TRANSITION DOES (from the paper)
 * =======================================
 * A TB-CSPN transition performs validation AND interpretation together, and
 * may produce no output if its guard fails (Section 5, Figure 4 caption). Here
 * the validation is minimal: the observation must be of the expected source
 * and above a confidence floor. Later transitions (T3, T5) add the harder part
 * -- time-windowed joins across sources -- but the shape is the same: consume
 * tokens, check guards, maybe emit.
 *
 * TEMPORAL PROVENANCE OF THE INTERPRETATION
 * =========================================
 * The paper's tokens are "timestamped with the time t of their generation" and
 * carry a ttl, and the time-windowed joins fire only for tokens whose validity
 * intervals are close: abs((t0'+ttl') - (t0+ttl)) <= ths (Section 5). For that
 * rule to mean anything, the age of the underlying evidence must survive
 * interpretation: an interpretation of an OLD observation must itself be old.
 * We therefore inherit the observation's timestamp (obs->t) into the
 * InterpToken rather than stamping it with now(). Two consequences follow, both
 * intended:
 *   - In normal operation the interpretation's t is the observation's t (a few
 *     tenths of a second in the past), which does not change fusion.
 *   - A LATE observation (e.g. a delayed EO confirmation) produces an
 *     interpretation whose validity window is correspondingly in the past, so
 *     it can no longer fuse with a fresh CandidateTarget -- exactly the "stale
 *     EO confirmation" counterfactual of Section 5.3.
 *
 * PROVENANCE
 * ==========
 * The emitted InterpToken records the id of the ObsToken it came from in its
 * origin field. This is the first link of the audit chain the paper requires:
 * every mission can be traced back through its interpretations to the raw
 * observations that justified it.
 *
 * The ttl carried into the InterpToken is what later makes a time-windowed
 * join succeed or fail, so it is taken from a parameter rather than copied
 * blindly from the observation.
 *
 * Topics:
 *   Subscribed:
 *     /obs_tokens     (guarded_swarms_msgs/ObsToken)
 *   Published:
 *     /interp_tokens  (guarded_swarms_msgs/InterpToken)
 *
 * @author Luca D'Aurizio
 */
#include <rclcpp/rclcpp.hpp>
#include <guarded_swarms_msgs/msg/interp_token.hpp>
#include <guarded_swarms_msgs/msg/obs_token.hpp>
#include <string>
class InterpretationNode : public rclcpp::Node {
 public:
  InterpretationNode() : Node("interpretation_node") {
    // Which observation source this transition consumes (radar, rf, ...).
    accept_source_ =
        this->declare_parameter<std::string>("accept_source", "radar");
    // The semantic label it emits (PossibleUAV, LikelyDroneLink, ...).
    emit_label_ =
        this->declare_parameter<std::string>("emit_label", "PossibleUAV");
    // Confidence floor: observations below this are not interpreted. This is
    // the transition guard.
    min_confidence_ = this->declare_parameter<double>("min_confidence", 0.4);
    // Validity of the produced interpretation, in seconds. Governs the
    // downstream time-windowed joins, so it is a parameter of the transition,
    // not inherited from the observation.
    interp_ttl_s_ = this->declare_parameter<double>("interp_ttl_s", 4.0);
    obs_sub_ = this->create_subscription<guarded_swarms_msgs::msg::ObsToken>(
        "/obs_tokens", 50,
        [this](const guarded_swarms_msgs::msg::ObsToken::SharedPtr m) {
          on_observation(m);
        });
    interp_pub_ =
        this->create_publisher<guarded_swarms_msgs::msg::InterpToken>(
            "/interp_tokens", 50);
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
    RCLCPP_INFO(this->get_logger(), "InterpretationNode (TB-CSPN transition)");
    RCLCPP_INFO(this->get_logger(), "  %s  ->  %s", accept_source_.c_str(),
                emit_label_.c_str());
    RCLCPP_INFO(this->get_logger(), "  guard: confidence >= %.2f",
                min_confidence_);
    RCLCPP_INFO(this->get_logger(), "  emitted ttl: %.1f s", interp_ttl_s_);
    RCLCPP_INFO(this->get_logger(),
                "============================================================");
  }
 private:
  void on_observation(
      const guarded_swarms_msgs::msg::ObsToken::SharedPtr obs) {
    // --- Guard 1: this transition only consumes its own modality ---
    if (obs->source != accept_source_) return;
    // --- Guard 2: confidence floor ---
    if (obs->confidence < min_confidence_) return;
    guarded_swarms_msgs::msg::InterpToken tok;
    tok.id = emit_label_ + "-" + std::to_string(seq_++);
    tok.target_id = obs->target_id;
    tok.label = emit_label_;
    tok.origin = {obs->id};  // provenance: the observation this came from
    tok.confidence = obs->confidence;
    // Inherit the observation's timestamp, so the age of the evidence survives
    // interpretation and the downstream time-windowed joins (T3, T5) act on the
    // true validity of the evidence. See "Temporal provenance" above: this is
    // what makes a late observation produce a late interpretation, which is the
    // mechanism behind the stale-EO counterfactual.
    tok.t = obs->t;
    tok.ttl_s = interp_ttl_s_;
    // A track observation carries a position; pass it through so downstream
    // transitions and worker agents have somewhere to send vehicles. A
    // signature or bearing observation does not, and position stays zero.
    if (obs->kind == guarded_swarms_msgs::msg::ObsToken::KIND_TRACK &&
        obs->value.size() >= 3) {
      tok.position.x = obs->value[0];
      tok.position.y = obs->value[1];
      tok.position.z = obs->value[2];
    }
    interp_pub_->publish(tok);
  }
  std::string accept_source_;
  std::string emit_label_;
  double min_confidence_;
  double interp_ttl_s_;
  rclcpp::Subscription<guarded_swarms_msgs::msg::ObsToken>::SharedPtr obs_sub_;
  rclcpp::Publisher<guarded_swarms_msgs::msg::InterpToken>::SharedPtr
      interp_pub_;
  uint64_t seq_ = 0;
};
int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<InterpretationNode>());
  rclcpp::shutdown();
  return 0;
}