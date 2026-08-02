#!/usr/bin/env python3
# Copyright 2026 Luca D'Aurizio. Apache-2.0.
"""Console bridge: republish ConfirmedThreat tokens on a QoS-clean topic.

Why this node exists
====================
rosbridge (the WebSocket bridge the supervisor console connects through)
subscribes to a topic with a QoS profile it chooses itself, and on a topic that
already has publishers it can end up with a subscription profile incompatible
with those publishers -- a known rosbridge behaviour. The symptom is silent:
the browser client connects, rosbridge logs "Subscribed", but no message is
ever delivered to the callback.

Rather than fight rosbridge's QoS selection from the browser (roslibjs QoS
support is version-dependent and fragile), this node owns a clean, dedicated
topic for the console. It subscribes to /interp_tokens with the same default
QoS the publishers use (reliable, volatile, keep-last), filters for the one
label the decision panel needs (ConfirmedThreat), and republishes on
/console/threat with an explicit, plain default QoS. rosbridge then subscribes
to /console/threat -- a topic whose only publisher is this node, with a profile
rosbridge matches cleanly -- and the messages flow.

It also serves as a natural place to decouple the console from the internal
token stream: the console sees only what a supervisor should act on, not every
intermediate interpretation.

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
