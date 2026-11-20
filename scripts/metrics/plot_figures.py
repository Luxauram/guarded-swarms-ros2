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
plot_figures.py - two figures of the coastal scenario, from recorded runs.

Read-only: it reads bags that are already recorded, and writes PDF and PNG
files.

  trajectories  The runs seen from above, in two panels on the same map: a
                nominal run (--nominal) and a run with a faulty UAV worker
                (--fault). Each panel draws the sea and the solids of the
                world (buildings, harbour, obstacles) from coastal.sdf, the
                acoustic buoys, the intruder ground truth and the track of
                every vehicle, with the UAV of the first UAV task highlighted
                and the intruder where it was at that task. In the faulty run
                the building of the faulty worker is highlighted, and the
                track of its UAV ends at the impact: the estimate of a crashed
                vehicle is not its position.
  verdicts      The Safety Board of the faulty UAV over time, in two panels:
                the veto left to the faulty worker (--fault) and applied by
                the safety gate (--gate). Each panel draws, from the first UAV
                task on, the lidar range the board reads and its proximity
                threshold, the distance of the UAV to the wall, the distance
                to the wall of each setpoint that reached PX4 (negative inside
                the building), and the intervals in which the board reported
                unsafe. A panel ends at the impact if the UAV hits the
                building. The distance to the wall is the one of the tables
                of analyze_faults.py; the lidar range is measured along the
                heading of the UAV, so it is larger when the UAV does not fly
                straight at the wall. It is also drawn in one column,
                verdicts-column: 252 x 250 pt, with short legend labels on
                one row.

Positions are in the world frame (Gazebo ENU): the local position of PX4,
north-east-down from the spawn point, plus the spawn point of the vehicle in
coastal_fleet.yaml. Times are in simulated time: the receive time of each
message mapped onto the recorded /clock. The UAV of the task, its building,
the impact and the threshold are those of analyze_faults.py.

Usage:
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 scripts/metrics/plot_figures.py \\
        --nominal bags/campaigns/auth-delay/nominal/run-01-seed1000/bag \\
        --fault bags/campaigns/faults/fault-worker/run-01-seed1000/bag \\
        --gate bags/campaigns/faults/fault-gate/run-01-seed1000/bag \\
        [--out results/figures]

A figure is drawn when its bags are given: trajectories needs --nominal and
--fault, verdicts needs --fault and --gate. The runs should come from
campaigns recorded with the same version of the code.

Output, in --out (default results/figures):
    trajectories.pdf, trajectories.png
    verdicts.pdf, verdicts.png
    verdicts-column.pdf, verdicts-column.png

@author Luca D'Aurizio
"""

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml

from analyze_faults import (CONTACT_M, STATUS_UNSAFE, TRIP_M, UAVS, Building,
                            UavTrack, first_task, wall_m)
from analyze_faults import read_bag as read_safety_layer
from analyze_scaling import POSITION, UGV_INSTANCE, split_topic, vehicle_name
from audit_timing import GT_TYPE, ClockMap, storage_id

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
WORLD = os.path.join(REPO, "src", "guarded_swarms_gz", "worlds",
                     "coastal.sdf")
FLEET = os.path.join(REPO, "src", "guarded_swarms_bringup", "config",
                     "coastal_fleet.yaml")

# The map of the trajectories, world ENU (m): the launch pads, the first row
# of buildings and the frontal approach from the sea.
XLIM = (-75.0, 75.0)
YLIM = (-62.0, 130.0)
BEFORE_TASK_S = 2.0    # the verdicts start this long before the first task
AFTER_TRIP_S = 8.0     # and end this long after the later lidar trip
MAX_DISTANCE_M = 30.0  # the verdicts draw distances up to this
GAP_S = 0.25           # lidar samples farther apart: no return in between
COLUMN_IN = (252.0 / 72.0, 250.0 / 72.0)  # one-column verdicts: 252 x 250 pt

# Three series, the reserved critical status for the veto and the impact,
# and neutral inks for the context.
BLUE, ORANGE, AQUA, CRITICAL = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8984"
SEA, SOLID, SOLID_EDGE, HIGHLIGHT = "#e6effa", "#dcdbd6", "#a8a7a1", "#9c9b95"


# =============================================================================
# The world and the fleet
# =============================================================================
@dataclass
class World:
    solids: List[List[Tuple[float, float]]] = field(default_factory=list)
    sea: Optional[Tuple[float, float, float, float]] = None  # x, y, w, h
    buoys: List[Tuple[float, float]] = field(default_factory=list)


def box_outline(x: float, y: float, yaw: float, sx: float, sy: float
                ) -> List[Tuple[float, float]]:
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * u - s * v, y + s * u + c * v)
            for u, v in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2),
                         (sx / 2, sy / 2), (-sx / 2, sy / 2))]


def circle_outline(x: float, y: float, r: float
                   ) -> List[Tuple[float, float]]:
    return [(x + r * math.cos(a), y + r * math.sin(a))
            for a in (2 * math.pi * k / 32 for k in range(32))]


def read_world(path: str) -> World:
    """The solids of coastal.sdf (every model with a collision box or
    cylinder), the sea surface and the acoustic buoys, in world ENU."""
    world = World()

    def walk(node, parent: Tuple[float, float, float]) -> None:
        for m in node.findall("model"):
            v = [float(t) for t in (m.findtext("pose") or "").split()]
            v += [0.0] * (6 - len(v))
            px, py, pyaw = parent
            c, s = math.cos(pyaw), math.sin(pyaw)
            pose = (px + c * v[0] - s * v[1], py + s * v[0] + c * v[1],
                    pyaw + v[5])
            name = m.get("name", "")
            geo = m.find("link/collision/geometry")
            if geo is not None:
                box, cyl = geo.find("box/size"), geo.find("cylinder/radius")
                if box is not None:
                    sx, sy = (float(t) for t in box.text.split()[:2])
                    world.solids.append(box_outline(*pose, sx, sy))
                elif cyl is not None:
                    world.solids.append(
                        circle_outline(pose[0], pose[1], float(cyl.text)))
            if name == "sea_surface":
                size = m.find("link/visual/geometry/box/size")
                if size is not None:
                    sx, sy = (float(t) for t in size.text.split()[:2])
                    world.sea = (pose[0] - sx / 2, pose[1] - sy / 2, sx, sy)
            if name.startswith("acoustic_buoy_") and name.endswith("_hull"):
                world.buoys.append((pose[0], pose[1]))
            walk(m, pose)

    walk(ET.parse(path).getroot().find("world"), (0.0, 0.0, 0.0))
    return world


def read_fleet(path: str) -> Dict[int, Tuple[float, float]]:
    """Spawn point (world ENU) of every PX4 instance of coastal_fleet.yaml."""
    with open(path) as f:
        fleet = yaml.safe_load(f)
    spawn = {int(fleet["ugv"]["instance"]):
             (float(fleet["ugv"]["x"]), float(fleet["ugv"]["y"]))}
    for u in fleet["uavs"]:
        spawn[int(u["instance"])] = (float(u["x"]), float(u["y"]))
    return spawn


# =============================================================================
# Bag reading
# =============================================================================
@dataclass
class Recording:
    """The tracks of one run, in simulated time and world ENU."""
    bag: str
    tracks: Dict[int, List[Tuple[float, float, float, float]]]  # t, x, y, z
    intruder: List[Tuple[float, float, float]]                  # t, x, y
    task_t: Optional[float] = None
    task_instance: Optional[int] = None


def read_tracks(bag_dir: str, spawn: Dict[int, Tuple[float, float]]
                ) -> Recording:
    """Read /clock, the vehicle tasks, the intruder ground truth and the local
    position of every vehicle of the fleet."""
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
        if topic.name in ("/clock", "/vehicle_tasks") or \
                split_topic(topic.name)[1] == POSITION or \
                (topic.type == GT_TYPE and "intruder" in topic.name):
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

    clk = ClockMap(msgs.get("/clock", []))
    if not clk.ok():
        raise ValueError("no /clock in the bag: no simulated time")
    tracks = {}
    for topic, lst in msgs.items():
        instance, name = split_topic(topic)
        if name != POSITION or instance not in spawn:
            continue
        sx, sy = spawn[instance]
        tracks[instance] = [(clk(rx), sx + m.y, sy + m.x, -m.z)
                            for rx, m in lst if clk.inside(rx)]
    # The intruder ground truth: the topic of its type that has messages.
    gt = max((lst for topic, lst in msgs.items() if topic not in
              ("/clock", "/vehicle_tasks") and split_topic(topic)[1]
              != POSITION), key=len, default=[])
    intruder = [(clk(rx), m.pose.position.x, m.pose.position.y)
                for rx, m in gt if clk.inside(rx)]
    rec = Recording(bag_dir, tracks, intruder)
    for rx, m in msgs.get("/vehicle_tasks", []):
        if m.assigned_system - 1 != UGV_INSTANCE and clk.inside(rx):
            rec.task_t, rec.task_instance = clk(rx), m.assigned_system - 1
            break
    return rec


def impact_of(track: List[Tuple[float, float, float, float]], t0: float,
              b: Building) -> Optional[int]:
    """Index of the first sample from t0 on whose centre is within CONTACT_M
    of the footprint of b, below its roof (the impact of analyze_faults.py)."""
    return next((i for i, (t, x, y, z) in enumerate(track)
                 if t >= t0 and wall_m(x, y, b) <= CONTACT_M
                 and z < b.height), None)


@dataclass
class Verdicts:
    """The safety layer of the UAV of the task, in simulated time from it."""
    bag: str
    uav: str
    lidar: List[Tuple[float, float]]
    distance: List[Tuple[float, float]]
    setpoint: List[Tuple[float, float]]
    unsafe: List[Tuple[float, float]]
    trip: Optional[float]
    impact: Optional[float]
    end: float


def read_verdicts(bag_dir: str) -> Verdicts:
    """The lidar range, the position, the setpoints at PX4 and the status of
    the UAV of the first UAV task, against the building of its faulty
    worker."""
    data = read_safety_layer(bag_dir)
    clk = ClockMap(data["/clock"])
    if not clk.ok():
        raise ValueError("no /clock in the bag: no simulated time")
    sid, t_task, _ = first_task(data, clk)
    if sid is None:
        raise ValueError("no UAV task in the run")
    tr = UavTrack(data, clk, sid)
    b = tr.building
    t_end = next((t for t, p in zip(*tr.pos) if t >= t_task
                  and wall_m(p[0], p[1], b) <= CONTACT_M
                  and p[2] < b.height), None)
    stop = math.inf if t_end is None else t_end
    lidar = [(t - t_task, r) for t, r in zip(*tr.lidar) if t < stop]
    distance = [(t - t_task, wall_m(p[0], p[1], b))
                for t, p in zip(*tr.pos) if t < stop]
    setpoint = [(t - t_task, wall_m(xy[0], xy[1], b))
                for t, xy, _ in tr.px4 if t < stop]
    status = [(t - t_task, v) for t, v in zip(*tr.status) if t < stop]
    unsafe, start = [], None
    for (t, v), nxt in zip(status, status[1:] + [None]):
        if v < STATUS_UNSAFE and start is None:
            start = t
        if start is not None and (nxt is None or nxt[1] >= STATUS_UNSAFE):
            unsafe.append((start, nxt[0] if nxt else t))
            start = None
    trip = next((t for t, r in lidar if t >= 0.0 and r < TRIP_M), None)
    ends = [p[-1][0] for p in (lidar, distance, setpoint, status) if p]
    return Verdicts(bag_dir, vehicle_name(sid - 1), lidar, distance,
                    setpoint, unsafe, trip,
                    None if t_end is None else t_end - t_task,
                    max(ends) if ends else 0.0)


# =============================================================================
# Figures
# =============================================================================
def draw_map(ax, world: World) -> None:
    from matplotlib.patches import Polygon, Rectangle
    if world.sea:
        x, y, w, h = world.sea
        ax.add_patch(Rectangle((x, y), w, h, facecolor=SEA,
                               edgecolor="none", zorder=0))
    for outline in world.solids:
        ax.add_patch(Polygon(outline, closed=True, facecolor=SOLID,
                             edgecolor=SOLID_EDGE, linewidth=0.4, zorder=1))
    if world.buoys:
        ax.plot(*zip(*world.buoys), linestyle="none", marker="^",
                markersize=4, color=MUTED, zorder=2, label="acoustic buoy")
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.set_aspect("equal")
    ax.set_xlabel("east (m)")


def draw_run(ax, rec: Recording, building: Optional[Building]) -> None:
    from matplotlib import patheffects
    from matplotlib.patches import Polygon
    impact = None
    if building is not None:
        ax.add_patch(Polygon(box_outline(building.x, building.y, building.yaw,
                                         building.size_x, building.size_y),
                             closed=True, facecolor=HIGHLIGHT, edgecolor=INK,
                             linewidth=0.8, zorder=1.5,
                             label="building of the faulty worker"))
    for instance, track in sorted(rec.tracks.items()):
        if not track:
            continue
        subject = instance == rec.task_instance
        if subject and building is not None and rec.task_t is not None:
            impact = impact_of(track, rec.task_t, building)
            if impact is not None:
                track = track[:impact + 1]
        xs, ys = [p[1] for p in track], [p[2] for p in track]
        ax.plot(xs, ys, color=BLUE if subject else MUTED,
                linewidth=1.6 if subject else 0.9,
                linestyle="-" if subject or instance != UGV_INSTANCE
                else "--", zorder=4 if subject else 3,
                label="UAV with the first task" if subject else None)
        ax.plot(xs[0], ys[0], marker="o", markersize=3.5,
                color=BLUE if subject else MUTED, zorder=4)
        ax.annotate(vehicle_name(instance), (xs[0], ys[0]), xytext=(0, -5),
                    textcoords="offset points", ha="center", va="top",
                    fontsize=6.5, color=INK2, zorder=5,
                    path_effects=[patheffects.withStroke(
                        linewidth=2.0, foreground="white")])
    if rec.intruder:
        xs, ys = [p[1] for p in rec.intruder], [p[2] for p in rec.intruder]
        ax.plot(xs, ys, color=ORANGE, linewidth=1.4, zorder=4,
                label="intruder")
        # The direction of motion, halfway along the path on the map: the
        # points 1 m or more apart, so that a hover adds none.
        path: List[Tuple[float, float]] = []
        for x, y in zip(xs, ys):
            if XLIM[0] <= x <= XLIM[1] and YLIM[0] <= y <= YLIM[1] and (
                    not path or math.dist(path[-1], (x, y)) >= 1.0):
                path.append((x, y))
        if len(path) > 8:
            j = len(path) // 2
            ax.annotate("", path[j], xytext=path[j - 4],
                        arrowprops=dict(arrowstyle="-|>", color=ORANGE,
                                        linewidth=1.4), zorder=4)
        if rec.task_t is not None:
            t, x, y = min(rec.intruder, key=lambda p: abs(p[0] - rec.task_t))
            ax.plot(x, y, marker="o", markersize=6, markerfacecolor="white",
                    markeredgecolor=ORANGE, markeredgewidth=1.4,
                    linestyle="none", zorder=5,
                    label="intruder at the first task")
    if impact is not None:
        track = rec.tracks[rec.task_instance]
        ax.plot(track[impact][1], track[impact][2], marker="X", markersize=8,
                color=CRITICAL, markeredgecolor="white", markeredgewidth=0.6,
                linestyle="none", zorder=6, label="impact")


def plot_trajectories(plt, world: World, nominal: Recording,
                      fault: Recording, out: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 5.0), sharey=True)
    for ax, rec, title in ((axes[0], nominal, "(a) Nominal run"),
                           (axes[1], fault, "(b) Faulty UAV worker")):
        draw_map(ax, world)
        building = None
        if rec is fault and rec.task_instance is not None:
            building = UAVS[rec.task_instance + 1][2]
        draw_run(ax, rec, building)
        ax.set_title(title, loc="left", fontsize=8, color=INK)
    axes[0].set_ylabel("north (m)")
    handles, labels = {}, []
    for ax in axes:
        for h, label in zip(*ax.get_legend_handles_labels()):
            if label not in handles:
                handles[label] = h
                labels.append(label)
    fig.legend([handles[k] for k in labels], labels, loc="lower center",
               ncol=3, frameon=False)
    fig.tight_layout(rect=(0.0, 0.08, 1.0, 1.0))
    save(fig, out, "trajectories")


def with_gaps(points: List[Tuple[float, float]], gap: float
              ) -> Tuple[List[float], List[float]]:
    """x and y of a series, with a break wherever two samples are farther
    apart than gap."""
    xs, ys = [], []
    for i, (t, v) in enumerate(points):
        if i and t - points[i - 1][0] > gap:
            xs.append(math.nan)
            ys.append(math.nan)
        xs.append(t)
        ys.append(v)
    return xs, ys


def plot_verdicts(plt, fault: Verdicts, gate: Verdicts, out: str,
                  column: bool = False) -> None:
    """The verdicts figure; with column, its one-column version."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    trips = [v.trip for v in (fault, gate) if v.trip is not None]
    x1 = min(max(v.end for v in (fault, gate)),
             (max(trips) if trips else 0.0) + AFTER_TRIP_S)
    low = min([0.0] + [d for v in (fault, gate)
                       for t, d in v.setpoint + v.distance
                       if -BEFORE_TASK_S <= t <= x1])
    size = COLUMN_IN if column else (3.5, 5.2)
    fig, axes = plt.subplots(2, 1, figsize=size, sharex=True, sharey=True)
    for ax, v, title in (
            (axes[0], fault, "(a) Veto left to the faulty worker"),
            (axes[1], gate, "(b) Veto applied by the safety gate")):
        for a, b in v.unsafe:
            ax.axvspan(a, b, color=CRITICAL, alpha=0.14, linewidth=0,
                       zorder=0)
        ax.axhline(TRIP_M, color=MUTED, linestyle="--", linewidth=0.8,
                   zorder=1)
        ax.axhline(0.0, color=INK2, linewidth=0.8, zorder=1)
        ax.annotate("threshold {:.0f} m".format(TRIP_M), (1.0, TRIP_M),
                    xycoords=("axes fraction", "data"), xytext=(-2, 2),
                    textcoords="offset points", ha="right", va="bottom",
                    fontsize=6.5, color=INK2)
        ax.annotate("wall", (1.0, 0.0), xycoords=("axes fraction", "data"),
                    xytext=(-2, 2), textcoords="offset points", ha="right",
                    va="bottom", fontsize=6.5, color=INK2)
        ax.plot(*with_gaps(v.lidar, GAP_S), color=AQUA, linewidth=1.1,
                zorder=3)
        if v.distance:
            ax.plot(*zip(*v.distance), color=BLUE, linewidth=1.6, zorder=4)
        if v.setpoint:
            ax.plot(*zip(*v.setpoint), color=ORANGE, linewidth=1.2,
                    drawstyle="steps-post", zorder=2)
        if v.impact is not None:
            ax.axvline(v.impact, color=CRITICAL, linestyle=":",
                       linewidth=1.2, zorder=4)
            ax.annotate("impact", (v.impact, 1.0),
                        xycoords=("data", "axes fraction"), xytext=(-3, -3),
                        textcoords="offset points", ha="right", va="top",
                        fontsize=6.5, color=INK2)
        ax.set_title("{} ({})".format(title, v.uav), loc="left", fontsize=8,
                     color=INK)
        ax.set_ylabel("distance (m)")
    axes[0].set_xlim(-BEFORE_TASK_S, x1)
    axes[0].set_ylim(low - 2.0, MAX_DISTANCE_M)
    axes[1].set_xlabel("simulated time from the first UAV task (s)")
    handles = [Line2D([], [], color=BLUE, linewidth=1.6),
               Line2D([], [], color=ORANGE, linewidth=1.2),
               Line2D([], [], color=AQUA, linewidth=1.1),
               Patch(facecolor=CRITICAL, alpha=0.14, linewidth=0)]
    if column:
        fig.legend(handles, ["UAV to wall", "setpoint to wall", "lidar range",
                             "unsafe (veto)"],
                   loc="lower center", ncol=4, frameon=False, fontsize=6.5,
                   handlelength=1.4, handletextpad=0.4, columnspacing=0.9)
        fig.tight_layout(rect=(0.0, 0.07, 1.0, 1.0), h_pad=0.6)
        save(fig, out, "verdicts-column")
        return
    fig.legend(handles, ["UAV, distance to the wall",
                         "setpoint at PX4, distance to the wall",
                         "lidar range, read by the Safety Board",
                         "Safety Board unsafe (veto)"],
               loc="lower center", ncol=1, frameon=False)
    fig.tight_layout(rect=(0.0, 0.17, 1.0, 1.0))
    save(fig, out, "verdicts")


def save(fig, out: str, name: str) -> None:
    for ext in ("pdf", "png"):
        path = os.path.join(out, "{}.{}".format(name, ext))
        fig.savefig(path, dpi=300)
        print("[figures] {}".format(path), file=sys.stderr)


def style(plt) -> None:
    plt.rcParams.update({
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "axes.edgecolor": INK2, "axes.labelcolor": INK, "text.color": INK,
        "xtick.color": INK2, "ytick.color": INK2,
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        # TrueType fonts in the PDF, as publishers' checks require.
        "pdf.fonttype": 42, "ps.fonttype": 42})


# =============================================================================
# Main
# =============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Figures of the coastal scenario from recorded runs "
                    "(read-only).")
    ap.add_argument("--nominal", help="bag of a nominal run")
    ap.add_argument("--fault", help="bag of a run with a faulty UAV worker "
                                    "and the veto left to the worker")
    ap.add_argument("--gate", help="bag of a run with a faulty UAV worker "
                                   "and the veto applied by the safety gate")
    ap.add_argument("--out", default=os.path.join("results", "figures"),
                    help="output folder (default: results/figures)")
    ap.add_argument("--world", default=WORLD, help="coastal.sdf")
    ap.add_argument("--fleet", default=FLEET, help="coastal_fleet.yaml")
    args = ap.parse_args()

    for bag in (args.nominal, args.fault, args.gate):
        if bag and not os.path.isfile(os.path.join(bag, "metadata.yaml")):
            print("{}: not a bag directory".format(bag), file=sys.stderr)
            return 2
    trajectories = bool(args.nominal and args.fault)
    verdicts = bool(args.fault and args.gate)
    if not trajectories and not verdicts:
        print("give --nominal and --fault (trajectories), --fault and --gate "
              "(verdicts), or all three", file=sys.stderr)
        return 2
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        print("Cannot import matplotlib ({}).\n"
              "Install it (sudo apt install python3-matplotlib); the Ubuntu "
              "22.04 package needs NumPy 1.x.".format(e), file=sys.stderr)
        return 2
    style(plt)
    os.makedirs(args.out, exist_ok=True)

    try:
        if trajectories:
            world = read_world(args.world)
            spawn = read_fleet(args.fleet)
            runs = []
            for bag in (args.nominal, args.fault):
                rec = read_tracks(bag, spawn)
                print("[figures] {}: first UAV task to {}".format(
                    bag, "none" if rec.task_instance is None
                    else vehicle_name(rec.task_instance)), file=sys.stderr)
                runs.append(rec)
            plot_trajectories(plt, world, runs[0], runs[1], args.out)
        if verdicts:
            pair = []
            for bag in (args.fault, args.gate):
                v = read_verdicts(bag)
                print("[figures] {}: {}, lidar trip {}, impact {}".format(
                    bag, v.uav,
                    "none" if v.trip is None else "{:.2f} s".format(v.trip),
                    "none" if v.impact is None
                    else "{:.2f} s".format(v.impact)), file=sys.stderr)
                pair.append(v)
            plot_verdicts(plt, pair[0], pair[1], args.out)
            plot_verdicts(plt, pair[0], pair[1], args.out, column=True)
    except (OSError, ValueError, KeyError) as e:
        print("[figures] failed: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
