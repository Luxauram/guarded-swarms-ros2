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
peak_speed.py - the horizontal speed of every vehicle in recorded runs.

Read-only: it reads bags that are already recorded, and starts nothing.

For each bag, and for each vehicle whose local position is in it
(fmu/out/vehicle_local_position_v1 of PX4), it gives the peak horizontal speed
while the vehicle moves away from its spawn point (outbound) and while it
comes back (inbound), with the time of each, and the first vehicle task with
its vehicle and time. Closer than MIN_RADIUS_M to the spawn point, the
direction away from it is noise, so those samples count in neither direction.

The speeds come from the velocity in the local position of PX4, which is in
simulated time. The times are in simulated time from the start of the
recording: the receive time of each message mapped onto the recorded /clock.
A bag without /clock gives the receive times instead, on the real clock, and
says so.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/peak_speed.py bags/<run>...

@author Luca D'Aurizio
"""

import argparse
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

from analyze_scaling import POSITION, split_topic, vehicle_name
from audit_timing import ClockMap, storage_id

TASKS = "/vehicle_tasks"
# Closer than this to the spawn point, the direction away from it is noise.
MIN_RADIUS_M = 1.0

Peak = Tuple[float, Optional[float]]       # speed (m/s), time (s) or None


def read_bag(bag_dir: str) -> Dict[str, list]:
    """Read the messages of /clock, of the vehicle tasks and of the local
    position of every vehicle.

    @return {topic: [(rx_s, msg), ...]}, rx_s the receive time relative to
            the first message of the bag.
    """
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as e:
        sys.exit("Cannot import the ROS 2 Python modules ({}).\n"
                 "Run `source /opt/ros/humble/setup.bash && "
                 "source install/setup.bash` first.".format(e))
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id=storage_id(bag_dir)),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                    output_serialization_format="cdr"))
    classes = {}
    for topic in reader.get_all_topics_and_types():
        if topic.name in ("/clock", TASKS) or \
                split_topic(topic.name)[1] == POSITION:
            try:
                classes[topic.name] = get_message(topic.type)
            except (AttributeError, ModuleNotFoundError, ValueError):
                pass
    msgs: Dict[str, list] = {topic: [] for topic in classes}
    base_ns = None
    while reader.has_next():
        topic, data, recv_ns = reader.read_next()
        if base_ns is None:
            base_ns = recv_ns
        if topic in classes:
            msgs[topic].append(((recv_ns - base_ns) * 1e-9,
                                deserialize_message(data, classes[topic])))
    return msgs


def fmt_time(t: Optional[float]) -> str:
    return "—" if t is None else "{:.1f} s".format(t)


def fmt_peak(peak: Peak) -> str:
    speed, t = peak
    if t is None:
        return "{:<21}".format("—")
    return "{:5.2f} m/s at {:6.1f} s".format(speed, t)


def speeds(bag_dir: str) -> List[str]:
    """The report of one bag, as lines."""
    msgs = read_bag(bag_dir)
    clk = ClockMap(msgs.get("/clock", []))
    sim = clk.ok()
    t0 = clk(0.0) if sim else 0.0

    def when(rx: float) -> Optional[float]:
        """The time of a receive time, or None outside the recorded /clock."""
        if not sim:
            return rx
        return clk(rx) - t0 if clk.inside(rx) else None

    lines = [bag_dir, "  times: " + (
        "simulated time from the start of the recording" if sim
        else "real time from the first message: no /clock in the bag")]

    tasks = msgs.get(TASKS, [])
    if tasks:
        rx, task = tasks[0]
        lines.append("  first vehicle task: {} at {}".format(
            vehicle_name(task.assigned_system - 1), fmt_time(when(rx))))
    else:
        lines.append("  first vehicle task: none")

    vehicles = sorted((split_topic(topic)[0], topic) for topic in msgs
                      if split_topic(topic)[1] == POSITION)
    if not vehicles:
        lines.append("  no local position in the bag")
    for instance, topic in vehicles:
        outbound: Peak = (0.0, None)
        inbound: Peak = (0.0, None)
        for rx, m in msgs[topic]:
            t = when(rx)
            if t is None or not getattr(m, "v_xy_valid", True):
                continue
            if math.hypot(m.x, m.y) < MIN_RADIUS_M:
                continue
            speed = math.hypot(m.vx, m.vy)
            # The sign of the velocity along the position from the spawn
            # point: away from it, or back toward it.
            if m.x * m.vx + m.y * m.vy >= 0.0:
                if speed > outbound[0]:
                    outbound = (speed, t)
            elif speed > inbound[0]:
                inbound = (speed, t)
        lines.append("  {:<5} outbound {} | inbound {}".format(
            vehicle_name(instance), fmt_peak(outbound),
            fmt_peak(inbound)).rstrip())
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Horizontal speed of every vehicle in recorded runs "
                    "(read-only).")
    ap.add_argument("bags", nargs="+", help="bag directories")
    args = ap.parse_args()

    read = 0
    for bag in args.bags:
        if not os.path.isfile(os.path.join(bag, "metadata.yaml")):
            print("[speed] skipping {}: not a bag directory".format(bag),
                  file=sys.stderr)
            continue
        try:
            lines = speeds(bag)
        except Exception as e:  # report and go on with the other bags
            print("[speed] {}: failed ({})".format(bag, e), file=sys.stderr)
            continue
        print("\n".join(lines))
        read += 1
    if not read:
        print("no readable bags", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())