# Scaling bench

How the real-time factor of the simulation falls as PX4 instances are added:
it tells how large a scenario a machine can run. PX4 SITL runs in lockstep
with Gazebo, so every instance is a point of synchronisation, and the cost of
a fleet is not the sum of the costs of its vehicles: it has to be measured.

## Running it

With nothing else running:

```bash
bash scripts/bench/bench_vehicles.sh                   # 6 lidar UAVs, headless
MODEL=gz_x500 bash scripts/bench/bench_vehicles.sh     # without lidar
HEADLESS=0 MAX=4 bash scripts/bench/bench_vehicles.sh  # window, up to 4
```

The script starts Gazebo with the world, through `gz_launch.sh`, waits 12 s for
it to come up, and measures the real-time factor with no vehicle. Then it adds
one PX4 instance at a time, waits `SETTLE_S` for it to boot and settle, and
measures again. It prints one line per step, and the table at the end:

```text
==========================================
Results: gz_x500_lidar_front, headless=1
==========================================
  vehicles   RTF
  0          <rtf>
  1          <rtf>
  ...
```

- **The measurement.** Each figure is the mean of `SAMPLES` readings of
  `real_time_factor` from `/world/<world>/stats`, since a single reading swings
  by tens of percent. A reading that does not arrive within 10 s is left out,
  and a step with no reading at all shows `n/a`.
- **The instances.** Each instance is a PX4 SITL started against the running
  Gazebo (`PX4_GZ_STANDALONE=1`), with the model `MODEL` and the airframe
  `AUTOSTART`. A step whose instance does not start shows `failed`, with the
  log of PX4 in `/tmp/bench_px4_<i>.log`.
- **Only the simulation.** No uXRCE-DDS agent and no ROS 2 node run: the
  figures are the cost of Gazebo and PX4 alone.

The instances spawn along the UAV launch pads, at y = -24 in world ENU, on free
ground at least 10 m from any building or obstacle, so that no contact loads
the physics:

| Instance | 0   | 1   | 2   | 3   | 4   | 5   | 6   | 7   | 8    |
| -------- | --- | --- | --- | --- | --- | --- | --- | --- | ---- |
| x, m     | -24 | 24  | 48  | 72  | 96  | 120 | 144 | 168 | -150 |

The first two are the pads of the coastal scenario. `MAX` can be at most 9, one
spawn point per instance.

The script cleans up before it starts and when it ends, Ctrl-C included: it
kills every PX4 instance and runs `gz_kill.sh` (see
[Simulation scripts](../scripts/simulation.md#gz_killsh)), since leftover
instances holding the shell lock of PX4 make the figures meaningless. For the
same reason it must not run alongside a scenario.

## Configuration

| Variable    | Default               | Meaning                                            |
| ----------- | --------------------- | -------------------------------------------------- |
| `WORLD`     | `coastal`             | The world                                          |
| `MODEL`     | `gz_x500_lidar_front` | The model of PX4; `gz_x500` has no lidar           |
| `AUTOSTART` | `4017`                | The airframe of PX4                                |
| `MAX`       | `6`                   | The largest number of instances, at most 9         |
| `HEADLESS`  | `1`                   | `1`: the Gazebo server alone; `0`: with the window |
| `SETTLE_S`  | `15`                  | The wait after each instance starts, s             |
| `SAMPLES`   | `5`                   | The readings averaged for each figure              |
| `PX4_DIR`   | `~/PX4-Autopilot`     | The PX4 tree, built with `make px4_sitl_default`   |

Two comparisons are the point of the variables:

- **`MODEL`.** `gz_x500_lidar_front` carries the 640-ray GPU lidar of the
  coastal scenario, `gz_x500` does not: the difference is the cost of the
  sensor, the rest the cost of the vehicle.
- **`HEADLESS`.** The Gazebo window alone takes about two CPU cores, so the
  measurements run headless, and the window is kept for videos.

The script runs `awk` in the C locale: in a locale with a decimal comma, such
as `it_IT`, `awk` would read back `0,987` as 987.

## Reading it

A simulated minute takes `1 / RTF` real minutes. Below about 0.4 a campaign of
recorded runs becomes impractical: size the scenario down, or reduce the
samples of the lidar and the rate of the physics. The logs of Gazebo and of
each instance are in `/tmp/bench_gz.log` and `/tmp/bench_px4_<i>.log`.
