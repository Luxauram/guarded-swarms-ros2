#!/usr/bin/env python3
# Copyright 2026 Luca D'Aurizio. Apache-2.0.
"""Console bridge: republish the ConfirmedThreat tokens for the console.

The supervisor console reaches ROS 2 through rosbridge, which sends every
message of a subscribed topic to the browser as JSON over a WebSocket. This
node subscribes to /interp_tokens with the profile of its publishers
(reliable, volatile, keep-last), keeps the one label the console acts on,
ConfirmedThreat, and republishes it unchanged on /console/threat, a topic of
its own with this node as its only publisher. The console then receives the
threats alone, not every intermediate interpretation of the chain.

Publishes:  /console/threat   (guarded_swarms_msgs/InterpToken)  ConfirmedThreat only
Subscribes: /interp_tokens    (guarded_swarms_msgs/InterpToken)
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from guarded_swarms_msgs.msg import InterpToken


class ConsoleBridgeNode(Node):
    def __init__(self):
        super().__init__("console_bridge_node")

        # Match the publishers of /interp_tokens: reliable, volatile, keep-last.
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.pub = self.create_publisher(InterpToken, "/console/threat", qos)
        self.sub = self.create_subscription(
            InterpToken, "/interp_tokens", self.on_interp, qos)

        self.forwarded = 0
        self.get_logger().info(
            "ConsoleBridge up: /interp_tokens (ConfirmedThreat) -> /console/threat")

    def on_interp(self, msg):
        if msg.label != InterpToken.LABEL_CONFIRMED_THREAT:
            return
        self.pub.publish(msg)
        self.forwarded += 1
        if self.forwarded % 20 == 1:
            self.get_logger().info(
                f"forwarded {self.forwarded} ConfirmedThreat(s) to the console")


def main():
    rclpy.init()
    node = ConsoleBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
