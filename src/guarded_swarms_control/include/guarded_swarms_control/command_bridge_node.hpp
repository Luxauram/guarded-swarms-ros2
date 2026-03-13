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
 * @file command_bridge_node.hpp
 * @brief Command bridge between the digital coordination layer and the
 *        analog safety enforcement layer — class declaration.
 *
 * Translates approved @c AuthToken messages received from the coordinator
 * into normalised thrust commands forwarded to the SafetyBoard node.
 * Rejected tokens are silently discarded and produce no actuator output.
 *
 * Pipeline position:
 * @code
 *   coordinator_node  -->  /auth_tokens        -->  command_bridge_node
 *   command_bridge_node  -->  /actuator_cmd_raw  -->  safety_board_node
 *   safety_board_node  -->  /actuator_cmd_safe  -->  offboard_control_node
 * @endcode
 *
 * @author Luca D'Aurizio
 */

#pragma once

#include <guarded_swarms_coordinator/msg/auth_token.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float32.hpp>
#include <string>
#include <unordered_map>

// ============================================================================
// CommandBridgeNode
// ============================================================================

/**
 * @brief ROS 2 node bridging the digital token layer to the analog safety
 * layer.
 *
 * Subscribes to @c /auth_tokens and converts each approved token into a
 * normalised thrust command published on @c /actuator_cmd_raw. Tokens whose
 * approval flag is not set are dropped without generating any output.
 */
class CommandBridgeNode : public rclcpp::Node {
 public:
  /**
   * @brief Constructs the node, declares ROS parameters, and initialises the
   *        subscription and publisher.
   */
  explicit CommandBridgeNode();

 private:
  static constexpr const char* TOPIC_AUTH_TOKENS = "/auth_tokens";
  static constexpr const char* TOPIC_CMD_RAW = "/actuator_cmd_raw";

  static constexpr int QUEUE_SIZE = 10;

  static constexpr float DEFAULT_THRUST =
      0.6f;  ///< Normalised thrust issued on token approval (60 %).

  /**
   * @brief Handles incoming @c AuthToken messages from the coordinator.
   *
   * Increments the received counter unconditionally. Approved tokens trigger
   * a thrust command via @c compute_thrust; rejected tokens increment the
   * rejected counter and are otherwise ignored.
   *
   * @param msg Shared pointer to the received @c AuthToken message.
   */
  void auth_token_callback(
      const guarded_swarms_coordinator::msg::AuthToken::SharedPtr msg);

  /**
   * @brief Computes the normalised thrust value for a given agent.
   *
   * The current implementation returns @c DEFAULT_THRUST for all agents.
   * Override this method to implement per-agent thrust policies.
   *
   * @param agent_id Identifier of the agent whose token was approved.
   * @return Normalised thrust in the range [0.0, 1.0].
   */
  float compute_thrust(const std::string& agent_id) const;

  uint64_t tokens_received_ = 0;
  uint64_t tokens_approved_ = 0;
  uint64_t tokens_rejected_ = 0;
  rclcpp::Subscription<guarded_swarms_coordinator::msg::AuthToken>::SharedPtr
      auth_sub_;
  rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr cmd_raw_pub_;
};
