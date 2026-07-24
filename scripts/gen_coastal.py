#!/usr/bin/env python3
"""
Generate coastal.sdf, the Guarded Swarms coastal surveillance world.

Deterministic: a fixed seed means every regeneration produces a byte-identical
world, which matters because the evaluation metrics are collected against it.

Scenery is emitted as nested models so that the Gazebo entity tree shows a
handful of folders (terrain, town, harbour, sensing, flight_ops, obstacles)
instead of a flat list of a hundred boxes. Vehicles spawned by PX4 at runtime
always appear at world level and cannot be grouped.

Usage:  python3 scripts/gen_coastal.py
Output: src/guarded_swarms_gz/worlds/coastal.sdf
"""

import os
import random

random.seed(20260723)

OUT_PATH = os.environ.get(
    "COASTAL_OUT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "src", "guarded_swarms_gz", "worlds", "coastal.sdf"),
)

out = []
SOLIDS = []   # (name, x, y, size_x, size_y) of every model with collision


def W(line=""):
    out.append(line)


# =============================================================================
# Emitters
# =============================================================================

IND = 6  # indentation of a model nested one level inside a group


def _material(r, g, b, spec):
    return [
        f"<material>",
        f"  <ambient>{r:.2f} {g:.2f} {b:.2f} 1</ambient>",
        f"  <diffuse>{min(r * 1.12, 1):.2f} {min(g * 1.12, 1):.2f} "
        f"{min(b * 1.12, 1):.2f} 1</diffuse>",
        f"  <specular>{spec}</specular>",
        f"</material>",
    ]


def _emit(lines, indent):
    pad = " " * indent
    for ln in lines:
        W(pad + ln if ln else "")


def box_model(name, pose, size, colour, collision=True, shadows=True,
              indent=IND):
    x, y, z, yaw = pose
    sx, sy, sz = size
    r, g, b = colour
    if collision:
        SOLIDS.append((name, x, y, sx, sy))
    body = [
        f'<model name="{name}">',
        f"  <static>true</static>",
        f"  <pose>{x} {y} {z} 0 0 {yaw}</pose>",
        f'  <link name="link">',
    ]
    if collision:
        body += [
            f'    <collision name="collision">',
            f"      <geometry><box><size>{sx} {sy} {sz}</size></box></geometry>",
            f"    </collision>",
        ]
    body += [
        f'    <visual name="visual">',
        f'      <cast_shadows>{"true" if shadows else "false"}</cast_shadows>',
        f"      <geometry><box><size>{sx} {sy} {sz}</size></box></geometry>",
    ]
    body += ["      " + m for m in _material(r, g, b, "0.12 0.12 0.12 1")]
    body += [
        f"    </visual>",
        f"  </link>",
        f"</model>",
        "",
    ]
    _emit(body, indent)


def cyl_model(name, pose, radius, length, colour, collision=True, indent=IND):
    x, y, z, yaw = pose
    r, g, b = colour
    if collision:
        SOLIDS.append((name, x, y, radius * 2, radius * 2))
    body = [
        f'<model name="{name}">',
        f"  <static>true</static>",
        f"  <pose>{x} {y} {z} 0 0 {yaw}</pose>",
        f'  <link name="link">',
    ]
    if collision:
        body += [
            f'    <collision name="collision">',
            f"      <geometry><cylinder><radius>{radius}</radius>"
            f"<length>{length}</length></cylinder></geometry>",
            f"    </collision>",
        ]
    body += [
        f'    <visual name="visual">',
        f"      <geometry><cylinder><radius>{radius}</radius>"
        f"<length>{length}</length></cylinder></geometry>",
    ]
    body += ["      " + m for m in _material(r, g, b, "0.15 0.15 0.15 1")]
    body += [
        f"    </visual>",
        f"  </link>",
        f"</model>",
        "",
    ]
    _emit(body, indent)


def group_open(name, comment):
    W(f"    <!-- ============ {comment} ============ -->")
    W(f'    <model name="{name}">')
    W("      <static>true</static>")
    W("      <pose>0 0 0 0 0 0</pose>")
    W("")


def group_close():
    W("    </model>")
    W("")



# =============================================================================
# Clearance check
#
# Vehicles are spawned by PX4 at poses configured in make/vars.mk. If a spawn
# pose falls inside a building footprint the vehicle appears embedded in
# geometry, so the check is asserted here rather than discovered in Gazebo.
# Keep SPAWN_POSES in sync with UAV0_POSE / UAV1_POSE / COASTAL_UGV_POSE.
# =============================================================================

SPAWN_POSES = {
    "UAV0": (-24.0, -24.0),
    "UAV1": (24.0, -24.0),
    "UGV": (-60.0, -14.0),
}

CLEARANCE_M = 6.0


def check_clearance():
    """Fail loudly if any solid box sits too close to a spawn pose."""
    problems = []
    for label, (px, py) in SPAWN_POSES.items():
        worst = None
        for (name, bx, by, bsx, bsy) in SOLIDS:
            dx = max(abs(px - bx) - bsx / 2.0, 0.0)
            dy = max(abs(py - by) - bsy / 2.0, 0.0)
            gap = (dx ** 2 + dy ** 2) ** 0.5
            if worst is None or gap < worst[0]:
                worst = (gap, name)
        if worst is None:
            continue
        gap, name = worst
        if gap < CLEARANCE_M:
            problems.append(f"{label} at ({px}, {py}): {gap:.1f} m from {name}")
        else:
            print(f"clearance {label}: {gap:.1f} m (nearest: {name})")
    if problems:
        raise SystemExit(
            "SPAWN CLEARANCE FAILURE\n  " + "\n  ".join(problems)
            + f"\nEach spawn pose needs at least {CLEARANCE_M} m of free space."
        )


# =============================================================================
# Header
# =============================================================================

W('<?xml version="1.0" encoding="UTF-8"?>')
W("""<!--
  Guarded Swarms === Coastal Surveillance World

  GENERATED FILE. Regenerate with 'make gen-coastal' (deterministic seed).
  Do not hand-edit: change scripts/gen_coastal.py instead.

  Implements the case study of Borghoff, Bottoni and Pareschi (2026),
  "Sensor-Driven Mission Synthesis for UAV/UGV Swarms", IET Radar, Sonar and
  Navigation, Section 5.1: a coastal perimeter monitored by a coastal radar,
  passive RF monitoring equipment, a network of acoustic buoys near the
  shoreline, and UAV-mounted electro-optical cameras. The swarm comprises two
  UAV platforms for aerial interception and one UGV positioned near the
  shoreline for ground observation and target recovery.

  SCALE NOTE
  ==========
  The scenario is compressed to a 400x400 m area. A real coastal radar covers
  kilometres, but PX4 lockstep simulation with three vehicles does not scale to
  that footprint on a single workstation. The compression is geometric only:
  sensor ranges, detection thresholds and time windows are configured in the
  consultant agents rather than in this world, so the coordination behaviour
  under study is unaffected. State this as a limitation in the thesis.

  COORDINATE FRAMES (read before editing poses)
  =============================================
  This world is ENU, like PX4's own worlds:  Gazebo X = East, Gazebo Y = North.
  PX4 vehicles reason in NED:                NED North = Gazebo Y
                                             NED East  = Gazebo X
  A rover patrolling ALONG the shore (Gazebo X) must therefore vary the SECOND
  component of its NED waypoints, not the first.

  ENTITY TREE
  ===========
  Scenery is grouped into nested models: terrain, town, harbour, sensing,
  flight_ops, obstacles. Vehicles spawned by PX4 at runtime appear at world
  level and cannot be grouped.

  LAYOUT (top view, Gazebo ENU, 1 unit = 1 m)
  ===========================================

      Y = +200  . . . . . . . open sea . . . . . . . . . . . . . .
      Y = +120        o          o          o          o   outer buoys
      Y =  +70   o         o          o          o          o
                        maritime approach corridor
      Y =  +34   [====== breakwater ======]        (^) lighthouse
      Y =  +16   |pier W|      |pier E|            moored boats
      Y =    0  ================ shoreline =========================
      Y =   =8   ============= promenade ==========================
      Y =  =14   ============= shore road (UGV patrol) ============
      Y =  =24   [pad 0]                  [pad 1]     UAV launch pads
      Y =  =34   ####  town blocks: 4 rows x 10 columns  ##########
      Y = =110   ####  (^) radar hill      (^) RF mast  ##########
      Y = =200  . . . . . . . . . inland . . . . . . . . . . . . .

            X = =200                                        X = +200

  Vehicle spawn poses live in make/vars.mk, not here.
  The intruder aerial target is NOT part of this world: it is spawned and
  driven separately so its trajectory can be scripted and replayed identically.
-->""")

W("""<sdf version="1.9">
  <world name="coastal">

    <physics type="ode">
      <max_step_size>0.002</max_step_size>
      <real_time_factor>1.0</real_time_factor>
      <real_time_update_rate>500</real_time_update_rate>
    </physics>

    <gravity>0 0 -9.8</gravity>
    <magnetic_field>6e-06 2.3e-05 -4.2e-05</magnetic_field>
    <atmosphere type="adiabatic"/>

    <scene>
      <grid>false</grid>
      <ambient>0.45 0.45 0.45 1</ambient>
      <background>0.62 0.74 0.86 1</background>
      <shadows>true</shadows>
    </scene>

    <light name="sunUTC" type="directional">
      <pose>0 0 500 0 0 0</pose>
      <cast_shadows>true</cast_shadows>
      <intensity>1</intensity>
      <direction>0.001 0.625 -0.78</direction>
      <diffuse>0.904 0.904 0.904 1</diffuse>
      <specular>0.271 0.271 0.271 1</specular>
      <attenuation>
        <range>2000</range>
        <linear>0</linear>
        <constant>1</constant>
        <quadratic>0</quadratic>
      </attenuation>
      <spot>
        <inner_angle>0</inner_angle>
        <outer_angle>0</outer_angle>
        <falloff>0</falloff>
      </spot>
    </light>

    <!-- Infinite collision plane: guarantees nothing falls through.
         Kept at world level because it is physics, not scenery.
         All visible surfaces are thin boxes laid on top of it. -->
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry>
            <plane><normal>0 0 1</normal><size>1 1</size></plane>
          </geometry>
          <surface>
            <friction><ode><mu>2</mu><mu2>2</mu2></ode></friction>
            <bounce/>
            <contact>
              <collide_bitmask>65535</collide_bitmask>
              <ode><min_depth>0.005</min_depth><kp>1e8</kp></ode>
            </contact>
          </surface>
        </collision>
        <pose>0 0 0 0 0 0</pose>
        <inertial>
          <mass>1</mass>
          <inertia><ixx>1</ixx><ixy>0</ixy><ixz>0</ixz>
                   <iyy>1</iyy><iyz>0</iyz><izz>1</izz></inertia>
        </inertial>
      </link>
    </model>
""")

# =============================================================================
# terrain
# =============================================================================

group_open("terrain", "Terrain and road surfaces")

box_model("sea_surface", (0, 100, -0.05, 0), (400, 200, 0.1),
          (0.08, 0.24, 0.36), collision=False, shadows=False)
box_model("inland_terrain", (0, -100, -0.04, 0), (400, 200, 0.1),
          (0.46, 0.44, 0.36), collision=False, shadows=False)
box_model("beach_strip", (0, -3, -0.03, 0), (400, 6, 0.1),
          (0.76, 0.71, 0.58), collision=False, shadows=False)
box_model("promenade", (0, -8, -0.025, 0), (340, 5, 0.1),
          (0.72, 0.70, 0.66), collision=False, shadows=False)
box_model("shore_road", (0, -14, -0.02, 0), (360, 8, 0.1),
          (0.24, 0.24, 0.25), collision=False, shadows=False)

for i, x in enumerate(range(-160, 200, 40)):
    box_model(f"street_ns_{i}", (x, -82, -0.02, 0), (7, 100, 0.1),
              (0.26, 0.26, 0.27), collision=False, shadows=False)
for i, y in enumerate((-58, -82, -106)):
    box_model(f"street_ew_{i}", (0, y, -0.02, 0), (340, 7, 0.1),
              (0.26, 0.26, 0.27), collision=False, shadows=False)

group_close()

# =============================================================================
# town
# =============================================================================

group_open("town",
           "Town blocks: heights 8 to 34 m, so UAVs must clear the skyline")

palette = [
    (0.62, 0.58, 0.50), (0.58, 0.60, 0.62), (0.66, 0.60, 0.54),
    (0.54, 0.58, 0.56), (0.64, 0.62, 0.58), (0.56, 0.54, 0.58),
    (0.68, 0.64, 0.56), (0.50, 0.54, 0.58),
]

rows_y = [-46, -70, -94, -118]
cols_x = list(range(-180, 200, 40))

n_buildings = 0
for ri, cy in enumerate(rows_y):
    for ci, cx in enumerate(cols_x):
        if (ri, ci) in {(1, 4), (2, 7)}:   # two open squares, for variety
            continue
        h = random.choice([8, 11, 14, 14, 18, 22, 26, 30, 34])
        sx = random.choice([16, 20, 22, 26])
        sy = random.choice([14, 16, 18])
        jx = random.uniform(-3, 3)
        jy = random.uniform(-3, 3)
        col = palette[(ri * 3 + ci) % len(palette)]
        box_model(f"building_{ri}_{ci}",
                  (round(cx + jx, 2), round(cy + jy, 2), h / 2,
                   round(random.uniform(-0.05, 0.05), 3)),
                  (sx, sy, h), col)
        n_buildings += 1

group_close()

# =============================================================================
# harbour
# =============================================================================

group_open("harbour", "Harbour: breakwater, piers, quay, warehouses, boats")

box_model("breakwater_main", (-40, 34, 1.5, 0), (150, 6, 3), (0.42, 0.40, 0.38))
box_model("breakwater_arm", (34, 22, 1.5, 1.05), (40, 6, 3), (0.42, 0.40, 0.38))
box_model("pier_west", (-95, 16, 0.9, 0), (10, 40, 1.8), (0.50, 0.46, 0.40))
box_model("pier_east", (-45, 16, 0.9, 0), (10, 40, 1.8), (0.50, 0.46, 0.40))
box_model("quay", (-70, -1, 1.0, 0), (110, 8, 2.0), (0.52, 0.50, 0.46))

for i, x in enumerate((-115, -92, -69, -46)):
    box_model(f"warehouse_{i}", (x, -28, 5, 0), (20, 10, 10), (0.48, 0.50, 0.52))

for i, (x, y) in enumerate([(-88, 22), (-88, 10), (-102, 26),
                            (-52, 24), (-52, 12), (-38, 20)]):
    yaw = round(random.uniform(-0.1, 0.1), 3)
    box_model(f"boat_{i}_hull", (x, y, 0.6, yaw), (3.2, 8.0, 1.2),
              (0.86, 0.86, 0.84))
    box_model(f"boat_{i}_cabin", (x, y + 1.0, 1.7, yaw), (2.2, 2.6, 1.0),
              (0.30, 0.42, 0.60))

group_close()

# =============================================================================
# sensing
# =============================================================================

group_open("sensing",
           "Sensing infrastructure: visual references only, detection logic "
           "lives in the consultant agents")

cyl_model("radar_hill", (0, -160, 3, 0), 26, 6, (0.44, 0.46, 0.34))
box_model("radar_base", (0, -160, 8, 0), (7, 7, 4), (0.55, 0.55, 0.52))
cyl_model("radar_mast", (0, -160, 15, 0), 0.7, 10, (0.45, 0.45, 0.48))
box_model("radar_dish", (0, -160, 21.5, 0.35), (12, 0.8, 3.2),
          (0.72, 0.72, 0.74))

cyl_model("rf_mast", (-150, -158, 14, 0), 0.6, 28, (0.50, 0.50, 0.52))
box_model("rf_antenna_upper", (-150, -158, 28.6, 0), (6.0, 0.25, 0.25),
          (0.68, 0.64, 0.20), collision=False)
box_model("rf_antenna_mid", (-150, -158, 26.4, 0), (4.4, 0.25, 0.25),
          (0.68, 0.64, 0.20), collision=False)
box_model("rf_antenna_lower", (-150, -158, 24.2, 0), (3.0, 0.25, 0.25),
          (0.68, 0.64, 0.20), collision=False)

buoys = [(-130, 72), (-70, 64), (-10, 76), (55, 66), (120, 70),
         (-95, 124), (-20, 132), (60, 120), (130, 128)]
for i, (x, y) in enumerate(buoys, start=1):
    cyl_model(f"acoustic_buoy_{i}_hull", (x, y, 0.5, 0), 0.9, 2.0,
              (0.84, 0.36, 0.05), collision=False)
    cyl_model(f"acoustic_buoy_{i}_mast", (x, y, 2.3, 0), 0.10, 1.8,
              (0.18, 0.18, 0.18), collision=False)

cyl_model("lighthouse_tower", (52, 12, 12, 0), 2.6, 24, (0.88, 0.88, 0.88))
cyl_model("lighthouse_lantern", (52, 12, 25.4, 0), 1.9, 2.8,
          (0.62, 0.14, 0.11), collision=False)

group_close()

# =============================================================================
# flight_ops
# =============================================================================

group_open("flight_ops",
           "UAV launch pads, clear of the shore road so the rover never "
           "crosses one")

for i, x in enumerate((-24, 24)):
    box_model(f"uav_pad_{i}", (x, -24, -0.01, 0), (14, 14, 0.1),
              (0.18, 0.18, 0.20), collision=False, shadows=False)
    box_model(f"uav_pad_{i}_marking", (x, -24, 0.05, 0), (9, 0.8, 0.02),
              (0.90, 0.90, 0.90), collision=False, shadows=False)

group_close()

# =============================================================================
# adversary
#
# Deliberately NOT inside a group: Gazebo refuses to apply velocity commands
# to nested models ("Unable to set linear velocity for nested models"), so the
# intruder must sit at world level like the PX4 vehicles do.
# =============================================================================

W('    <!-- ============ Hostile aerial target ============')
W('         Driven kinematically by intruder_node, so the trajectory is')
W('         identical on every run. At world level: see above.')
W('         ============================================================== -->')
W('    <include>')
W('      <uri>model://intruder</uri>')
W('      <name>intruder</name>')
W('      <pose>0 180 15 0 0 0</pose>')
W('    </include>')
W("")

# =============================================================================
# obstacles
# =============================================================================

group_open("obstacles",
           "Shore obstacles on the UGV patrol line: the digital layer keeps "
           "issuing the patrol command while the analogue board vetoes")

box_model("beached_container", (62, -14, 1.3, 0.12), (7.0, 2.6, 2.6),
          (0.34, 0.30, 0.22))
box_model("shore_rocks", (-78, -14, 0.8, 0), (4.5, 3.0, 1.6),
          (0.38, 0.36, 0.34))
box_model("road_barrier", (-8, -14, 0.5, 0), (3.0, 1.2, 1.0),
          (0.72, 0.70, 0.68))

group_close()

# =============================================================================
# Footer
# =============================================================================

W("""    <!-- Same origin as the PX4 default world, so GPS-derived state
         matches the other scenarios. -->
    <spherical_coordinates>
      <surface_model>EARTH_WGS84</surface_model>
      <world_frame_orientation>ENU</world_frame_orientation>
      <latitude_deg>47.397971057728974</latitude_deg>
      <longitude_deg>8.546163739800146</longitude_deg>
      <elevation>0</elevation>
    </spherical_coordinates>

  </world>
</sdf>""")

check_clearance()

text = "\n".join(out) + "\n"

os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
with open(OUT_PATH, "w") as f:
    f.write(text)

print(f"wrote  : {os.path.abspath(OUT_PATH)}")
print(f"lines  : {text.count(chr(10))}")
print(f"groups : 6")
print(f"models : {text.count('<model name=')}")
print(f"buildings: {n_buildings}")