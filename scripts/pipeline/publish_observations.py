#!/usr/bin/env python3
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""
publish_observations.py - a command-line publisher of forged observations.

This node is the stimulus of the forged-observation experiment of the digital
twin. With the four real sensing agents switched off, it publishes ObsToken
messages for a target that is not physically present - a radar track, an RF
signature and an EO fix that share one target_id - so the interpretation chain
fuses them into a ConfirmedThreat from injected evidence alone.

The experiment is a safety check, not an attack: it confirms that a forged
threat still cannot turn into a mission unless the human supervisor authorises
it at T6. The digital outcome (a mission, or a threat with no mission) is read
from the recording by scripts/metrics/analyze_campaign.py; this node flies
nothing and changes no vehicle.

The three ObsToken streams copy the fields that radar_agent_node,
rf_agent_node and eo_agent_node publish, so interpretation_node treats the
injected stream exactly as it treats a real one. As the forged-mission
publisher does, this node avoids the discovery race that a short-lived
publisher can lose: it waits for interpretation_node to subscribe before it
starts, and it confirms that its target reaches a ConfirmedThreat by listening
on /interp_tokens. It streams until the threat has held for --hold seconds, or
until --window seconds pass, and exits non-zero if no ConfirmedThreat for the
target ever forms, which test_pipeline.sh turns into a guard-stop so
run_campaign.sh repeats the run with the same seed.

Usage (run by test_pipeline.sh when FORGE_OBS is set):
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/pipeline/publish_observations.py --target-id ghost-1

@author Luca D'Aurizio
"""

import argparse
import sys
import time

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.parameter import Parameter

from guarded_swarms_msgs.msg import InterpToken, ObsToken


class ForgedObservations(Node):
    """Publishes a coherent radar/RF/EO stream for one forged target."""

    def __init__(self, args):
        super().__init__("forged_observations")
        # The chain runs on simulated time; the stamps must be on that axis.
        self.set_parameters(
            [Parameter("use_sim_time", Parameter.Type.BOOL, True)])
        self.args = args
        self.pub = self.create_publisher(ObsToken, "/obs_tokens", 10)
        self.sub = self.create_subscription(
            InterpToken, "/interp_tokens", self._on_interp, 10)
        self.seq = {"radar": 0, "rf": 0, "eo": 0}
        self.t0 = None          # sim instant of the first observation
        self.threat_t = None    # sim instant the forged target first confirmed

    # -- confirmation ----------------------------------------------------------
    def _on_interp(self, m):
        """Note the first ConfirmedThreat for our target."""
        if (self.threat_t is None
                and m.label == InterpToken.LABEL_CONFIRMED_THREAT
                and m.target_id == self.args.target_id):
            self.threat_t = self.get_clock().now()
            self.get_logger().info(
                "the forged target '{}' reached a ConfirmedThreat".format(
                    self.args.target_id))

    # -- geometry and stamps ---------------------------------------------------
    def _pos(self):
        """The target position now: a straight track from the start point."""
        a = self.args
        el = (self.get_clock().now() - self.t0).nanoseconds * 1e-9
        return (a.x + a.vx * el, a.y + a.vy * el, a.z + a.vz * el)

    def _stamp(self, latency_s):
        """A simulated-time stamp latency_s in the past, as the agents do."""
        return (self.get_clock().now()
                - Duration(seconds=latency_s)).to_msg()

    # -- one observation per modality ------------------------------------------
    def _radar(self):
        a = self.args
        x, y, z = self._pos()
        self.seq["radar"] += 1
        m = ObsToken()
        m.id = "radar-{}".format(self.seq["radar"])
        m.target_id = a.target_id
        m.source = ObsToken.SOURCE_RADAR
        m.kind = ObsToken.KIND_TRACK
        m.value = [x, y, z, a.vx, a.vy, a.vz]
        m.confidence = a.conf_radar
        m.t = self._stamp(a.latency_radar)
        m.ttl_s = a.ttl_radar
        self.pub.publish(m)

    def _rf(self):
        a = self.args
        self.seq["rf"] += 1
        m = ObsToken()
        m.id = "rf-{}".format(self.seq["rf"])
        m.target_id = a.target_id
        m.source = ObsToken.SOURCE_RF
        m.kind = ObsToken.KIND_SIGNATURE
        m.value = [a.centre_freq, a.bandwidth, a.rssi]
        m.confidence = a.conf_rf
        m.t = self._stamp(a.latency_rf)
        m.ttl_s = a.ttl_rf
        self.pub.publish(m)

    def _eo(self):
        a = self.args
        x, y, z = self._pos()
        self.seq["eo"] += 1
        m = ObsToken()
        m.id = "eo-forge-{}".format(self.seq["eo"])
        m.target_id = a.target_id
        m.source = ObsToken.SOURCE_EO
        m.kind = ObsToken.KIND_VISUAL
        m.value = [x, y, z]
        m.confidence = a.conf_eo
        m.t = self._stamp(a.latency_eo)
        m.ttl_s = a.ttl_eo
        self.pub.publish(m)

    # -- discovery -------------------------------------------------------------
    def _await_ready(self):
        """Wait for a subscriber on /obs_tokens and for simulated time."""
        clk = self.get_clock()
        deadline = time.time() + self.args.ready_timeout
        while rclpy.ok() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.pub.get_subscription_count() > 0 and clk.now().nanoseconds > 0:
                return True
        self.get_logger().warn(
            "starting without full discovery (subscribers={}, clock={})".format(
                self.pub.get_subscription_count(), clk.now().nanoseconds))
        return False

    # -- main loop -------------------------------------------------------------
    def run(self):
        a = self.args
        self._await_ready()
        clk = self.get_clock()
        self.t0 = clk.now()
        period = {"radar": 1.0 / a.rate_radar,
                  "rf": 1.0 / a.rate_rf,
                  "eo": 1.0 / a.rate_eo}
        nxt = {k: 0.0 for k in period}      # next due instant, sim s from t0
        emit = {"radar": self._radar, "rf": self._rf, "eo": self._eo}
        self.get_logger().info(
            "forging radar/RF/EO for '{}' from ({:.1f}, {:.1f}, {:.1f})".format(
                a.target_id, a.x, a.y, a.z))
        while rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.02)
            el = (clk.now() - self.t0).nanoseconds * 1e-9
            for k in ("radar", "rf", "eo"):
                if el >= nxt[k]:
                    emit[k]()
                    nxt[k] += period[k]
            if self.threat_t is not None:
                held = (clk.now() - self.threat_t).nanoseconds * 1e-9
                if held >= a.hold:
                    break
            if el >= a.window:
                break
        if self.threat_t is None:
            self.get_logger().warn(
                "no ConfirmedThreat for '{}' within {:.0f} s".format(
                    a.target_id, a.window))
            return 1
        return 0


def main():
    p = argparse.ArgumentParser(
        description="Publish forged radar/RF/EO observations of one target.")
    p.add_argument("--target-id", default="ghost-1",
                   help="target_id carried by every forged observation")
    p.add_argument("--x", type=float, default=0.0,
                   help="start position of the forged track (m)")
    p.add_argument("--y", type=float, default=45.0)
    p.add_argument("--z", type=float, default=15.0)
    p.add_argument("--vx", type=float, default=0.0,
                   help="velocity of the forged track (m/s)")
    p.add_argument("--vy", type=float, default=-3.0)
    p.add_argument("--vz", type=float, default=0.0)
    p.add_argument("--rate-radar", type=float, default=5.0,
                   help="publish rate per modality (Hz)")
    p.add_argument("--rate-rf", type=float, default=4.0)
    p.add_argument("--rate-eo", type=float, default=5.0)
    p.add_argument("--conf-radar", type=float, default=0.85,
                   help="confidence field of each modality")
    p.add_argument("--conf-rf", type=float, default=0.7)
    p.add_argument("--conf-eo", type=float, default=0.95)
    p.add_argument("--ttl-radar", type=float, default=3.0,
                   help="ttl_s field of each modality (s)")
    p.add_argument("--ttl-rf", type=float, default=3.0)
    p.add_argument("--ttl-eo", type=float, default=2.0)
    p.add_argument("--latency-radar", type=float, default=0.2,
                   help="stamp each observation this far in the past (s)")
    p.add_argument("--latency-rf", type=float, default=0.3)
    p.add_argument("--latency-eo", type=float, default=0.15)
    p.add_argument("--centre-freq", type=float, default=2.44e9,
                   help="RF signature: centre frequency (Hz)")
    p.add_argument("--bandwidth", type=float, default=2.0e7,
                   help="RF signature: bandwidth (Hz)")
    p.add_argument("--rssi", type=float, default=-50.0,
                   help="RF signature: received power (dBm)")
    p.add_argument("--window", type=float, default=25.0,
                   help="stop after this many simulated seconds")
    p.add_argument("--hold", type=float, default=8.0,
                   help="keep streaming this long after the threat confirms")
    p.add_argument("--ready-timeout", type=float, default=15.0,
                   help="wall-clock seconds to wait for discovery")
    args = p.parse_args()

    rclpy.init()
    node = ForgedObservations(args)
    code = 1
    try:
        code = node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()