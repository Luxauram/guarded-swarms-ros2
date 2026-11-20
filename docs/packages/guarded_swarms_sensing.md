# guarded_swarms_sensing

The sensing layer: four consultant agents, one for each modality of the coastal
scenario. Each publishes what its sensor would observe as `ObsToken` messages
on `/obs_tokens`, the input of the coordination chain (see
[`guarded_swarms_msgs`](guarded_swarms_msgs.md#obstoken)).

The agents synthesise their observations from the ground truth of the targets,
with a model of coverage, error and rate for each modality. That model is part
of the simulation, not of the architecture: real detection and data
association are out of scope, so an agent knows which target it observes.

| Agent                 | Modality                  | `kind`      | Coverage                                               | Configuration         |
| --------------------- | ------------------------- | ----------- | ------------------------------------------------------ | --------------------- |
| `radar_agent_node`    | Coastal radar             | `track`     | A sector facing the sea, from a fixed mast             | `radar_agent.yaml`    |
| `rf_agent_node`       | Passive RF monitoring     | `signature` | A range around a fixed mast, transmitting targets only | `rf_agent.yaml`       |
| `acoustic_agent_node` | Acoustic buoys            | `bearing`   | A short range around each buoy, at sea                 | `acoustic_agent.yaml` |
| `eo_agent_node`       | EO camera carried by UAV0 | `visual`    | A cone from the live position of the UAV               | `eo_agent_uav0.yaml`  |

The configuration files are in `config/`. Each sets `use_sim_time` and the
values of the agent's parameters, which are the same as its defaults.

## Common behaviour

- **Targets.** An agent subscribes to one ground-truth topic per target,
  `geometry_msgs/msg/PoseStamped` in world ENU, listed in `ground_truth_topics`
  with the matching identifier in `target_ids`. If the lists differ in length,
  `transmitting_topics` included for the RF agent, the agent logs an error and
  tracks nothing. It scans a target from its first pose on, against the latest
  pose received, which it keeps if the topic stops.
- **Scans.** A timer on the node clock runs `update_rate_hz` scans per
  simulated second, whatever the real-time factor. At each scan the agent tests
  each target against its coverage. A target in coverage is missed with
  probability `1 - detection_prob`, and otherwise yields one `ObsToken`.
- **Latency.** An observation is published at once, with its time `t` set
  `latency_s` in the past, so the latency adds no scheduling jitter.
- **Random draws.** A Mersenne Twister generator draws the noise, the misses and
  the false alarms, seeded by the `seed` parameter, from 0 to 4294967295. With
  `0` the agent draws a seed at random. The seed in use is logged at start-up,
  so the draws of a run can be reproduced.
- **Identifiers.** `radar-<n>`, `rf-<n>`, `acoustic-<n>` and
  `eo-<carrier>-<n>`, numbered by each agent from 0.

The subscriptions and the publisher use the default QoS (reliable, volatile,
depth 10), except the subscription of the EO agent to the position of its
carrier. The parameters are read at start-up.

| Parameter             | Type     | Meaning                                                                 |
| --------------------- | -------- | ----------------------------------------------------------------------- |
| `seed`                | integer  | Seed of the random draws; `0` draws one at random                       |
| `target_ids`          | string[] | Identifier of each target, default `["intruder"]`                       |
| `ground_truth_topics` | string[] | Ground-truth topic of each target, default `["/intruder/ground_truth"]` |
| `detection_prob`      | double   | Probability that a target in coverage is detected at a scan             |
| `latency_s`           | double   | Age of an observation when it is published, s                           |
| `ttl_s`               | double   | Validity of an observation, s                                           |
| `update_rate_hz`      | double   | Scans per simulated second                                              |

The intruder of `guarded_swarms_control` publishes the ground truth of the
target `intruder` (see [`guarded_swarms_control`](guarded_swarms_control.md)).

## radar_agent_node

A coastal radar. A target is in coverage when it is:

- within `max_range_m` of the radar, at (`pos_x`, `pos_y`, `pos_z`);
- at an altitude of at least `min_altitude_m`;
- within `half_angle_deg` of the bore, measured in the horizontal plane. The
  bore is an angle counterclockwise from east: 90° points north, towards the
  sea.

A target that comes from the sea enters the sector early; one that comes over
the town enters it late or never.

The `value` of a track is the position with Gaussian noise of
`position_noise_m` on each axis, and the velocity between the true positions of
two consecutive detections, zero at the first. The confidence falls linearly
with the range, from `confidence_near` at the radar to `confidence_far` at
`max_range_m`.

With `false_positive_hz` above 0, each scan also emits a false track with
probability `false_positive_hz / update_rate_hz`: an empty `target_id`, a random
point of the sector between 20 m and `max_range_m`, an altitude of 15 m, zero
velocity and the confidence `confidence_far`.

The agent tracks up to 64 targets.

| Parameter                 | Default                 | Meaning                                                     |
| ------------------------- | ----------------------- | ----------------------------------------------------------- |
| `pos_x`, `pos_y`, `pos_z` | `0.0`, `-160.0`, `20.0` | Position of the radar, world ENU, m                         |
| `bore_deg`                | `90.0`                  | Direction of the sector, degrees counterclockwise from east |
| `half_angle_deg`          | `70.0`                  | Half-width of the sector, degrees                           |
| `max_range_m`             | `260.0`                 | Range, m                                                    |
| `min_altitude_m`          | `2.0`                   | Lowest altitude of a target in coverage, m                  |
| `position_noise_m`        | `3.0`                   | Standard deviation of the position noise, m                 |
| `detection_prob`          | `0.95`                  |                                                             |
| `false_positive_hz`       | `0.0`                   | Rate of false tracks, per simulated second                  |
| `latency_s`               | `0.2`                   |                                                             |
| `ttl_s`                   | `3.0`                   |                                                             |
| `update_rate_hz`          | `5.0`                   |                                                             |
| `confidence_near`         | `0.9`                   | Confidence of a track at the radar                          |
| `confidence_far`          | `0.5`                   | Confidence of a track at `max_range_m`                      |

## rf_agent_node

Passive RF monitoring. It does not locate a target: it reports that a radio
link is present, and its signature. A target is in coverage when it is within
`max_range_m` of the mast, in any direction, and is transmitting.

Each target has a `std_msgs/msg/Bool` topic, listed in `transmitting_topics`,
that says whether it transmits. A target counts as silent until its topic says
otherwise, so a target in radio silence is invisible to this agent.

The `value` of a signature is the centre frequency with Gaussian noise of
1 MHz, the bandwidth, and the received power: `tx_power_dbm` minus
20 log10 of the range, with the range at least 1 m, plus Gaussian noise of
1.5 dB. The confidence is `confidence`.

With `false_positive_hz` above 0, each scan also emits a false signature with
probability `false_positive_hz / update_rate_hz`: an empty `target_id`, the
nominal centre frequency and bandwidth, −90 dBm, and half the confidence.

| Parameter                 | Default                      | Meaning                                        |
| ------------------------- | ---------------------------- | ---------------------------------------------- |
| `pos_x`, `pos_y`, `pos_z` | `-150.0`, `-158.0`, `28.0`   | Position of the mast, world ENU, m             |
| `max_range_m`             | `320.0`                      | Range, m                                       |
| `centre_freq_hz`          | `2.44e9`                     | Centre frequency of the link, Hz               |
| `bandwidth_hz`            | `2.0e7`                      | Bandwidth of the link, Hz                      |
| `tx_power_dbm`            | `20.0`                       | Transmitted power, dBm                         |
| `detection_prob`          | `0.9`                        |                                                |
| `false_positive_hz`       | `0.0`                        | Rate of false signatures, per simulated second |
| `latency_s`               | `0.3`                        |                                                |
| `ttl_s`                   | `3.0`                        |                                                |
| `update_rate_hz`          | `4.0`                        |                                                |
| `confidence`              | `0.7`                        | Confidence of a signature                      |
| `transmitting_topics`     | `["/intruder/transmitting"]` | Transmitting topic of each target              |

## acoustic_agent_node

A network of acoustic sensors on buoys at the sea surface. It does not locate a
target either: the buoy nearest to the target, if within `max_range_m`, reports
the direction it hears it from. The buoys cover only the sea near the shore, so
a target that comes over the town is not heard.

The `value` of a bearing is measured from the reporting buoy, in the axes of the
world: the bearing, counterclockwise from east, and the elevation, each with
Gaussian noise of `bearing_noise_deg`, in radians, and the range with Gaussian
noise of `range_noise_m`. The token does not say which buoy reported it. The
confidence is `confidence` times `1 - 0.4 × range / max_range_m`.

The agent emits no false alarms. No transition of the chain interprets the
acoustic observations (see
[`guarded_swarms_msgs`](guarded_swarms_msgs.md#obstoken)).

| Parameter           | Default                                         | Meaning                                        |
| ------------------- | ----------------------------------------------- | ---------------------------------------------- |
| `buoy_positions`    | `[-130, 72, -70, 64, -10, 76, 55, 66, 120, 70]` | Buoys as x, y pairs, world ENU, m: five buoys  |
| `max_range_m`       | `90.0`                                          | Range of each buoy, m                          |
| `bearing_noise_deg` | `4.0`                                           | Standard deviation of the angle noise, degrees |
| `range_noise_m`     | `12.0`                                          | Standard deviation of the range noise, m       |
| `detection_prob`    | `0.85`                                          |                                                |
| `latency_s`         | `0.5`                                           |                                                |
| `ttl_s`             | `3.0`                                           |                                                |
| `update_rate_hz`    | `3.0`                                           |                                                |
| `confidence`        | `0.6`                                           | Confidence of a bearing at the buoy            |

## eo_agent_node

An electro-optical camera carried by a UAV, UAV0 in the coastal scenario. Its
coverage moves with the UAV: a target is in coverage when it is within
`max_range_m` of the UAV and inside the cone of the camera.

- **Position of the UAV.** The agent reads the local position PX4 publishes for
  its carrier, on `uav_pose_topic`, north-east-down from the spawn point, and
  places the UAV in the world: x is `spawn_x` plus east, y is `spawn_y` plus
  north, z is `spawn_z` minus down. The subscription is best effort and
  transient local, depth 10, as PX4 publishes. The agent does not scan until
  the first position arrives.
- **Cone.** The axis of the camera is fixed in the world: `cam_bearing_deg`
  counterclockwise from east, 90° pointing north, and `cam_pitch_deg` above the
  horizon, negative looking down. It does not turn with the heading of the
  UAV. A target is inside the cone within `half_angle_deg` of the axis.

The `value` of a visual observation is the position with Gaussian noise of
`position_noise_m` on each axis. The confidence is `confidence`.

**Delayed delivery.** With `emit_delay_s` above 0, the agent holds each
observation back for that many simulated seconds before it publishes it,
leaving its `t` as observed. The confirmation still arrives, but late: if the
`ConfirmedAerialObject` it produces reaches T5 after the `CandidateTarget` has
expired, no `ConfirmedThreat` forms. The `EO_DELAY_S` environment variable, if
set to a number, overrides the parameter.

| Parameter                       | Default                              | Meaning                                                            |
| ------------------------------- | ------------------------------------ | ------------------------------------------------------------------ |
| `carrier`                       | `uav0`                               | Name of the carrier, in the identifiers of the observations        |
| `spawn_x`, `spawn_y`, `spawn_z` | `-24.0`, `-24.0`, `0.0`              | Spawn point of the carrier, world ENU, m                           |
| `uav_pose_topic`                | `/fmu/out/vehicle_local_position_v1` | Local position of the carrier, `px4_msgs/msg/VehicleLocalPosition` |
| `cam_bearing_deg`               | `90.0`                               | Bearing of the camera axis, degrees counterclockwise from east     |
| `cam_pitch_deg`                 | `-20.0`                              | Pitch of the camera axis, degrees                                  |
| `half_angle_deg`                | `30.0`                               | Half-angle of the cone, degrees                                    |
| `max_range_m`                   | `120.0`                              | Range, m                                                           |
| `position_noise_m`              | `1.0`                                | Standard deviation of the position noise, m                        |
| `detection_prob`                | `0.98`                               |                                                                    |
| `latency_s`                     | `0.15`                               |                                                                    |
| `ttl_s`                         | `2.0`                                |                                                                    |
| `update_rate_hz`                | `5.0`                                |                                                                    |
| `confidence`                    | `0.95`                               | Confidence of a visual observation                                 |
| `emit_delay_s`                  | `0.0`                                | Delay of the delivery, simulated seconds                           |

The spawn point must be that of the carrier in the scenario: UAV0 stands at
(-24, -24) in `coastal_fleet.yaml`.

## sensing.launch.py

Starts the four agents, each with its configuration file and its own seed.

| Argument   | Default | Effect                   |
| ---------- | ------- | ------------------------ |
| `radar`    | `true`  | Start the radar agent    |
| `rf`       | `true`  | Start the RF agent       |
| `acoustic` | `true`  | Start the acoustic agent |
| `eo`       | `true`  | Start the EO agent       |

Switching a modality off is how the runs without one modality are made, and
`eo:=false` gives the limiting case of a confirmation that never arrives.

The `SEED` environment variable sets the seed of the run, from 1 to 4294967291.
Each agent gets its own seed from it: `SEED + 1` for the radar, `+ 2` for the
RF, `+ 3` for the acoustic and `+ 4` for the EO, so one number reproduces the
draws of all four. Without `SEED` the file draws a seed at random, and logs it
in its banner. `EO_DELAY_S`, if set, reaches the EO agent through the
environment.

```bash
ros2 launch guarded_swarms_sensing sensing.launch.py
SEED=1000 ros2 launch guarded_swarms_sensing sensing.launch.py eo:=false
```

The agents need the intruder's ground truth, and the EO agent the position of
UAV0, so the coastal scenario and the intruder must be running.
`scripts/pipeline/test_pipeline.sh` starts this file with the `SEED` and
`EO_DELAY_S` of the run (see [Pipeline run scripts](../scripts/pipeline.md)).
