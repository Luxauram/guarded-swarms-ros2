#!/usr/bin/env python3
"""
Copyright 2026 Luca D'Aurizio

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
@file agent_node.py

Agent node for geometry token publishing.

This node simulates monitoring agents that publish geometry tokens representing
spatial area requests for UAV operations. Each agent operates within a predefined
zone and periodically requests spatial volumes with cryptographic signatures.

The agent workflow:
1. Initialize with unique ID and operational zone
2. Publish geometry tokens at 1Hz with randomized positions
3. Sign each token with SHA256 for coordinator validation
4. Include position, dimensions, and duration in each request

Typical usage:
    ros2 run guarded_swarms_coordinator agent_node --ros-args -p agent_id:=agent_A

@author Luca D'Aurizio
"""

import rclpy
from rclpy.node import Node
from guarded_swarms_coordinator.msg import GeometryToken as GeometryTokenMsg
from guarded_swarms_coordinator.token import create_geometry_token
import random


class AgentNode(Node):
    """
    ROS 2 node representing a monitoring agent.

    Publishes geometry tokens to request spatial areas for drone operations.
    Each agent is assigned a specific operational zone to simulate distributed
    monitoring responsibilities.
    """

    # ========================================================================
    # Constants
    # ========================================================================

    TOPIC_GEOMETRY_TOKENS = "/geometry_tokens"
    QUEUE_SIZE = 10

    DEFAULT_PUBLISH_RATE_HZ = 1.0
    DEFAULT_PRIORITY = 5

    STANDARD_BBOX_WIDTH = 5.0
    STANDARD_BBOX_HEIGHT = 5.0
    STANDARD_BBOX_DEPTH = 3.0

    ALTITUDE_VARIATION_METERS = 2.0

    DURATION_MIN_SECONDS = 5.0
    DURATION_MAX_SECONDS = 15.0

    # ========================================================================
    # Initialization
    # ========================================================================

    def __init__(
        self,
        agent_id: str,
        publish_rate: float = DEFAULT_PUBLISH_RATE_HZ,
        priority: int = DEFAULT_PRIORITY,
    ):
        """
        Initialize agent node with operational parameters.

        @param agent_id Unique agent identifier (e.g., "agent_A")
        @param publish_rate Token publishing frequency in Hz (default: 1.0)
        @param priority Mission priority level 0-10 (default: 5)
        """
        super().__init__(f"{agent_id}_node")

        self.agent_id = agent_id
        self.priority = priority
        self.operational_area = self._initialize_operational_area()

        self.geometry_publisher = self.create_publisher(
            GeometryTokenMsg, self.TOPIC_GEOMETRY_TOKENS, self.QUEUE_SIZE
        )

        timer_period = 1.0 / publish_rate
        self.timer = self.create_timer(timer_period, self.publish_geometry_token)

        self.get_logger().info(
            f"{self.agent_id} initialized. " f"Publishing at {publish_rate} Hz, priority={priority}"
        )

    def _initialize_operational_area(self) -> dict:
        """
        Assigns operational zone based on agent ID.

        Each agent is allocated a distinct spatial zone to simulate
        distributed monitoring across different geographic areas.

        @return Dictionary containing zone center and size
        """
        zones = {
            "agent_A": {"center": [0.0, 0.0, 5.0], "size": 10.0},
            "agent_B": {"center": [0.0, 0.0, 5.0], "size": 10.0},
            "agent_C": {"center": [0.0, 15.0, 5.0], "size": 10.0},
            "agent_D": {"center": [15.0, 15.0, 5.0], "size": 10.0},
        }

        return zones.get(self.agent_id, {"center": [0.0, 0.0, 5.0], "size": 10.0})

    # ========================================================================
    # Publishing
    # ========================================================================

    def publish_geometry_token(self):
        """
        Publishes geometry token with randomized position within zone.

        Generates spatial request with random offset from zone center to
        simulate dynamic monitoring scenarios. Token includes cryptographic
        signature and priority level for coordinator validation.
        """
        center = self.operational_area["center"]
        zone_size = self.operational_area["size"]

        position = [
            center[0] + random.uniform(-zone_size / 2, zone_size / 2),
            center[1] + random.uniform(-zone_size / 2, zone_size / 2),
            center[2]
            + random.uniform(-self.ALTITUDE_VARIATION_METERS, self.ALTITUDE_VARIATION_METERS),
        ]

        dimensions = [self.STANDARD_BBOX_WIDTH, self.STANDARD_BBOX_HEIGHT, self.STANDARD_BBOX_DEPTH]

        duration = random.uniform(self.DURATION_MIN_SECONDS, self.DURATION_MAX_SECONDS)

        # Create token with priority
        token = create_geometry_token(
            agent_id=self.agent_id,
            x=position[0],
            y=position[1],
            z=position[2],
            width=dimensions[0],
            height=dimensions[1],
            depth=dimensions[2],
            duration=duration,
            priority=self.priority,
        )

        msg = token.to_msg()
        self.geometry_publisher.publish(msg)

        self.get_logger().info(
            f"{self.agent_id} published token: "
            f"pos=[{position[0]:.1f}, {position[1]:.1f}, {position[2]:.1f}], "
            f"priority={self.priority}, "
            f"id={token.token_id[:8]}..."
        )


# ============================================================================
# Main Function
# ============================================================================


def main(args=None):
    """
    Main entry point for agent node.

    Initializes ROS 2, parses agent ID and priority from parameters,
    and spins the node until shutdown.
    """
    rclpy.init(args=args)

    temp_node = rclpy.create_node("temp_param_reader")
    temp_node.declare_parameter("agent_id", "agent_A")
    temp_node.declare_parameter("priority", 5)

    agent_id = temp_node.get_parameter("agent_id").value
    priority = temp_node.get_parameter("priority").value
    temp_node.destroy_node()

    node = AgentNode(agent_id=agent_id, priority=priority)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info(f"{agent_id} shutting down")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
