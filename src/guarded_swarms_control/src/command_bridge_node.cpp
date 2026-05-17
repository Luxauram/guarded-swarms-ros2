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
 * @file command_bridge_node.cpp
 * @brief Command bridge between the digital coordination layer and the
 *        analog safety enforcement layer - implementation.
 *
 * See command_bridge_node.hpp for the full architecture description.
 *
 * @author Luca D'Aurizio
 */

#include "guarded_swarms_control/command_bridge_node.hpp"

using AuthToken = guarded_swarms_coordinator::msg::AuthToken;

// ============================================================================
// Constructor
// ============================================================================

CommandBridgeNode::CommandBridgeNode() : Node("command_bridge_node") {
  auth_sub_ = this->create_subscription<AuthToken>(
      TOPIC_AUTH_TOKENS, QUEUE_SIZE,
      [this](const AuthToken::SharedPtr msg) { auth_token_callback(msg); });

  cmd_raw_pub_ =
      this->create_publisher<std_msgs::msg::Float32>(TOPIC_CMD_RAW, QUEUE_SIZE);

  RCLCPP_INFO(this->get_logger(), "CommandBridge initialized | %s -> %s",
              TOPIC_AUTH_TOKENS, TOPIC_CMD_RAW);
}

// ============================================================================
// Auth Token Callback
// ============================================================================

void CommandBridgeNode::auth_token_callback(const AuthToken::SharedPtr msg) {
  tokens_received_++;

  const std::string& agent_id = msg->base_token.agent_id;
  const std::string& reason = msg->reason;

  if (!msg->approved) {
    tokens_rejected_++;
    RCLCPP_DEBUG(this->get_logger(), "[Bridge] REJECTED for %s | reason: %s",
                 agent_id.c_str(), reason.c_str());
    return;
  }

  tokens_approved_++;
  float thrust = compute_thrust(agent_id);

  std_msgs::msg::Float32 cmd;
  cmd.data = thrust;
  cmd_raw_pub_->publish(cmd);

  RCLCPP_INFO(this->get_logger(),
              "[Bridge] APPROVED for %s | thrust=%.2f -> %s", agent_id.c_str(),
              thrust, TOPIC_CMD_RAW);
}

// ============================================================================
// Helpers
// ============================================================================

float CommandBridgeNode::compute_thrust(const std::string& agent_id) const {
  (void)agent_id;
  return DEFAULT_THRUST;
}

// ============================================================================
// Main
// ============================================================================

/**
 * @brief Entry point. Initialises the ROS 2 runtime and spins the
 *        CommandBridgeNode until shutdown.
 *
 * @param argc Argument count forwarded to @c rclcpp::init.
 * @param argv Argument vector forwarded to @c rclcpp::init.
 * @return 0 on clean exit.
 */
int main(int argc, char* argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<CommandBridgeNode>());
  rclcpp::shutdown();
  return 0;
}
