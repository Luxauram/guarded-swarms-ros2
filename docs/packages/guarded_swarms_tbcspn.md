# guarded_swarms_tbcspn

The coordination layer: the TB-CSPN transitions that turn the observations of
the sensing agents into missions, under the supervisor's authorisation, and the
missions into tasks for the vehicles. The transitions exchange tokens on shared
topics: each consumes the tokens it needs and publishes its own for the next.
Their place in the architecture is described in
[Architecture](../architecture.md#the-coordination-chain), and the fields of the
tokens in [`guarded_swarms_msgs`](guarded_swarms_msgs.md).

| Transition | Node in the launch | Executable                  | Consumes                                      | Produces                                       |
| ---------- | ------------------ | --------------------------- | --------------------------------------------- | ---------------------------------------------- |
| T1         | `t1_radar`         | `interpretation_node`       | A radar `ObsToken`                            | `PossibleUAV`                                  |
| T2         | `t2_rf`            | `interpretation_node`       | An RF `ObsToken`                              | `LikelyDroneLink`                              |
| T4         | `t4_eo`            | `interpretation_node`       | An EO `ObsToken`                              | `ConfirmedAerialObject`                        |
| T3         | `t3_candidate`     | `candidate_transition_node` | `PossibleUAV` and `LikelyDroneLink`           | `CandidateTarget`                              |
| T5         | `t5_threat`        | `candidate_transition_node` | `CandidateTarget` and `ConfirmedAerialObject` | `ConfirmedThreat`                              |
| T6         | `t6_mission`       | `mission_transition_node`   | `ConfirmedThreat` and an authorisation        | A `MissionToken`                               |
| T7         | `t7_dispatch`      | `dispatch_transition_node`  | A `MissionToken`                              | Two `VehicleTask`s: UAV intercept, UGV observe |

The workers that execute the tasks, T8 and T9, are in
[`guarded_swarms_control`](guarded_swarms_control.md). Every node of the layer
runs with `use_sim_time`, so every time and validity is in simulated time.

## interpretation_node

T1, T2 and T4: one parametric node, started three times. For each observation on
`/obs_tokens` it applies two guards, and if both pass it publishes one
interpretation on `/interp_tokens`:

1. the `source` of the observation is `accept_source`;
2. its confidence is at least `min_confidence`.

The interpretation takes the label `emit_label`, the identifier of the
observation as its `origin`, the confidence and the time `t` of the
observation, and the validity `interp_ttl_s`. Keeping the time of the
observation keeps the age of the evidence: a late observation yields an
interpretation that is just as late. The position is that of a `track`
observation, zero for the others.

The node does not check the validity of the observation, and it interprets an
observation with an empty `target_id` like any other. With the confidences of
the coastal agents, every true observation passes the floor of 0.4: radar 0.5
to 0.9, RF 0.7, EO 0.95. A false RF signature, at 0.35, does not.

| Topic            | Type                                  | Direction  | QoS                          |
| ---------------- | ------------------------------------- | ---------- | ---------------------------- |
| `/obs_tokens`    | `guarded_swarms_msgs/msg/ObsToken`    | Subscribed | Reliable, volatile, depth 50 |
| `/interp_tokens` | `guarded_swarms_msgs/msg/InterpToken` | Published  | Reliable, volatile, depth 50 |

| Parameter        | Type   | Default       | Meaning                                           |
| ---------------- | ------ | ------------- | ------------------------------------------------- |
| `accept_source`  | string | `radar`       | Source of the observations it interprets          |
| `emit_label`     | string | `PossibleUAV` | Label of the interpretations it publishes         |
| `min_confidence` | double | `0.4`         | Lowest confidence of an observation it interprets |
| `interp_ttl_s`   | double | `4.0`         | Validity of an interpretation, s                  |

`tbcspn.launch.py` sets `accept_source` and `emit_label` of each instance and
keeps the defaults of the other two parameters.

## candidate_transition_node

T3 and T5: a time-windowed join of two interpretations from different
modalities, started twice with different labels.

1. Of the interpretations on `/interp_tokens` it keeps those labelled `label_a`
   or `label_b`, each until its validity ends at `t + ttl_s`. One already
   expired on arrival is dropped.
2. At each arrival it looks for a pair, one of each label, for the same target
   and with validities that end close together:
   `|(t_b + ttl_b) − (t_a + ttl_a)| ≤ sync_threshold_s`. It takes the first
   such pair in order of arrival, publishes one interpretation labelled
   `emit_label`, and removes the pair, so a pair fires once. It fires at most
   once per arrival.
3. It removes expired tokens every 200 ms of wall time, and before each search.

The joined interpretation has the time of the join, the validity `emit_ttl_s`,
the product of the two confidences, the `origin` of both and their identifiers,
and the position of the first that has one.

The three guards decide the outcome of the chain:

- **Same target.** Only interpretations of the same target are joined.
- **Concordance.** Only `label_a` with `label_b`. When T2 reads the RF emissions
  as `LikelyCivilianTraffic`, T3 has no `LikelyDroneLink` to join, and no
  `CandidateTarget` forms.
- **Time window.** In the coastal scenario all the interpretations joined by
  T3 and T5 have a validity of 4 s, so the window compares their times: T3
  joins a radar and an RF observation taken at most `sync_threshold_s` apart,
  and T5 an EO observation taken at most that far from the formation of the
  `CandidateTarget`. An EO observation outside that window, or whose
  interpretation has already expired when it reaches T5, forms no
  `ConfirmedThreat`.

| Topic            | Type                                  | Direction  | QoS                          |
| ---------------- | ------------------------------------- | ---------- | ---------------------------- |
| `/interp_tokens` | `guarded_swarms_msgs/msg/InterpToken` | Subscribed | Reliable, volatile, depth 50 |
| `/interp_tokens` | `guarded_swarms_msgs/msg/InterpToken` | Published  | Reliable, volatile, depth 50 |

| Parameter          | Type   | Default           | Meaning                                                       |
| ------------------ | ------ | ----------------- | ------------------------------------------------------------- |
| `label_a`          | string | `PossibleUAV`     | First label of the pair                                       |
| `label_b`          | string | `LikelyDroneLink` | Second label of the pair                                      |
| `emit_label`       | string | `CandidateTarget` | Label of the joined interpretation                            |
| `sync_threshold_s` | double | `2.0`             | Window: largest gap between the ends of the two validities, s |
| `emit_ttl_s`       | double | `4.0`             | Validity of the joined interpretation, s                      |

In `tbcspn.launch.py`:

| Parameter          | T3                                                              | T5                                   |
| ------------------ | --------------------------------------------------------------- | ------------------------------------ |
| `label_a`          | `PossibleUAV`                                                   | `CandidateTarget`                    |
| `label_b`          | `LikelyDroneLink`                                               | `ConfirmedAerialObject`              |
| `emit_label`       | `CandidateTarget`                                               | `ConfirmedThreat`                    |
| `sync_threshold_s` | `T3_WINDOW_S` if set, else the `sync_threshold_s` argument, 3.0 | The `sync_threshold_s` argument, 3.0 |
| `emit_ttl_s`       | `4.0`, the default                                              | The `threat_ttl_s` argument, 10.0    |

## mission_transition_node

T6, the release of a mission under the supervisor's authorisation. It releases
an intercept mission for a target while it holds both a valid `ConfirmedThreat`
and a valid authorisation for that target, whichever arrived first.

- **Threats.** It keeps the interpretations labelled `require_label`, the
  freshest for each target, until their validity ends. One already expired on
  arrival is dropped.
- **Authorisations.** It keeps the `authorise` decisions, the freshest for each
  target, until their validity ends. A decision with an unset `t` is taken as
  made on arrival, so a decision published by hand needs no timestamp. A
  decision with an empty `authorised_by` is ignored, with a warning.
- **Denials.** A `deny` is logged and releases nothing. It does not withdraw an
  authorisation already held for the target.
- **Release.** When a threat and an authorisation for the same target are both
  held, it publishes the mission on `/mission_tokens` and discards both. One
  authorisation therefore releases one mission; another mission for the target
  needs another authorisation.

Expired tokens are removed every 200 ms of wall time and before each release.
Without an authorisation, or with a denial, no mission is released: a threat
waits for a decision as long as it is valid, `threat_ttl_s` in the coastal
scenario.

| Topic              | Type                                     | Direction  | QoS                                 |
| ------------------ | ---------------------------------------- | ---------- | ----------------------------------- |
| `/interp_tokens`   | `guarded_swarms_msgs/msg/InterpToken`    | Subscribed | Reliable, volatile, depth 50        |
| `/supervisor_auth` | `guarded_swarms_msgs/msg/SupervisorAuth` | Subscribed | Reliable, transient local, depth 10 |
| `/mission_tokens`  | `guarded_swarms_msgs/msg/MissionToken`   | Published  | Reliable, volatile, depth 10        |

The subscription to the decisions is transient local, so that a decision
published before T6 matched its publisher is not lost. A publisher of decisions
must offer the same durability, or ROS 2 does not connect the two.

| Parameter       | Type   | Default           | Meaning                                              |
| --------------- | ------ | ----------------- | ---------------------------------------------------- |
| `require_label` | string | `ConfirmedThreat` | Label of the interpretations that call for a release |
| `mission_type`  | string | `intercept`       | Type of the missions released                        |
| `mission_ttl_s` | double | `10.0`            | Validity of a mission, s                             |

The decisions come from the supervisor console, from the scripted supervisor of
[`guarded_swarms_supervisor`](guarded_swarms_supervisor.md), or by hand:

```bash
ros2 topic pub --once --keep-alive 5 \
  --qos-durability transient_local /supervisor_auth \
  guarded_swarms_msgs/msg/SupervisorAuth \
  "{target_id: 'intruder', authorised_by: 'operator', \
    decision: 'authorise', ttl_s: 15.0}"
```

`--keep-alive` keeps the publisher, and its decision, alive while T6 matches it.

## dispatch_transition_node

T7: the dispatch of a mission to the vehicles. For the first mission of each
target it publishes two tasks on `/vehicle_tasks`:

- an intercept task to the UAV nearest to the target position of the mission,
  by the three-dimensional distance from the latest position of each UAV;
- an observe task to the UGV.

It remembers the targets it has dispatched, and ignores any later mission for
them: the UAV assigned first follows the target on its own. It does not check
the validity of the mission. If no UAV position has arrived yet, it assigns the
first UAV of `uav_systems`, with a warning.

The node reads the position of each UAV from the local position PX4 publishes
for it, north-east-down from its spawn point, and places it in the world with
the spawn point of the UAV, as the EO agent does (see
[`guarded_swarms_sensing`](guarded_swarms_sensing.md#eo_agent_node)).

| Topic                           | Type                                   | Direction  | QoS                                    |
| ------------------------------- | -------------------------------------- | ---------- | -------------------------------------- |
| `/mission_tokens`               | `guarded_swarms_msgs/msg/MissionToken` | Subscribed | Reliable, volatile, depth 10           |
| Each topic of `uav_pose_topics` | `px4_msgs/msg/VehicleLocalPosition`    | Subscribed | Best effort, transient local, depth 10 |
| `/vehicle_tasks`                | `guarded_swarms_msgs/msg/VehicleTask`  | Published  | Reliable, volatile, depth 10           |

| Parameter         | Type      | Default                                                                              | Meaning                                        |
| ----------------- | --------- | ------------------------------------------------------------------------------------ | ---------------------------------------------- |
| `uav_systems`     | integer[] | `[1, 2]`                                                                             | MAV_SYS_ID of each UAV                         |
| `uav_pose_topics` | string[]  | `["/fmu/out/vehicle_local_position_v1", "/px4_1/fmu/out/vehicle_local_position_v1"]` | Local position topic of each UAV               |
| `uav_spawns`      | double[]  | `[-24.0, -24.0, 0.0, 24.0, -24.0, 0.0]`                                              | Spawn point of each UAV, x, y, z, world ENU, m |
| `ugv_system`      | integer   | `3`                                                                                  | MAV_SYS_ID of the UGV                          |

The three UAV lists are index-aligned, with three values per UAV in
`uav_spawns`. `tbcspn.launch.py` fills them from the fleet of the scenario.

## tbcspn.launch.py

Starts the seven transitions, with `use_sim_time`.

| Argument           | Default | Meaning                                                |
| ------------------ | ------- | ------------------------------------------------------ |
| `sync_threshold_s` | `3.0`   | Window of T5, and of T3 unless `T3_WINDOW_S` is set, s |
| `threat_ttl_s`     | `10.0`  | Validity of a `ConfirmedThreat`, s                     |
| `mission_ttl_s`    | `10.0`  | Validity of a mission, s                               |

| Variable      | Default           | Meaning                                                                      |
| ------------- | ----------------- | ---------------------------------------------------------------------------- |
| `RF_LABEL`    | `LikelyDroneLink` | Label T2 emits; `LikelyCivilianTraffic` gives the conflicting interpretation |
| `T3_WINDOW_S` | unset             | Window of T3 alone, s; unset, T3 uses `sync_threshold_s`                     |
| `N_UAVS`      | `2`               | Number of UAVs T7 dispatches to, from 2 to the number in the fleet file      |

`RF_LABEL` and `T3_WINDOW_S` are environment variables rather than arguments
because the launch file needs their values when it builds the nodes. `N_UAVS`
must be the same as for the scenario: T7 takes the UGV and the first `N_UAVS`
UAVs of `coastal_fleet.yaml` (in `guarded_swarms_bringup`), with the system ID
of each, PX4 instance plus one, the topic of its local position and its spawn
point. The banner logs the window of T3 and the fleet of T7.

The time constants of the chain, in the coastal scenario:

| Constant                                    | Value | Set by                                                       |
| ------------------------------------------- | ----- | ------------------------------------------------------------ |
| Validity of an observation                  | 2–3 s | The configuration of each agent, in `guarded_swarms_sensing` |
| Validity of an interpretation of T1, T2, T4 | 4 s   | `interp_ttl_s`, the default                                  |
| Validity of a `CandidateTarget`             | 4 s   | `emit_ttl_s` of T3, the default                              |
| Window of T3 and T5                         | 3 s   | `sync_threshold_s`; `T3_WINDOW_S` for T3                     |
| Validity of a `ConfirmedThreat`             | 10 s  | `threat_ttl_s`                                               |
| Validity of a mission                       | 10 s  | `mission_ttl_s`                                              |

The validity of a `ConfirmedThreat` is also how long it waits in T6 for an
authorisation: too short, and an authorisation that arrives a moment later
finds no threat to release.

```bash
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py
RF_LABEL=LikelyCivilianTraffic \
  ros2 launch guarded_swarms_tbcspn tbcspn.launch.py
ros2 launch guarded_swarms_tbcspn tbcspn.launch.py threat_ttl_s:=6.0
```

The chain needs the observations of the sensing layer, so the coastal scenario,
the intruder and `sensing.launch.py` must be running.
`scripts/pipeline/test_pipeline.sh` starts it with the settings of the run (see
[Pipeline run scripts](../scripts/pipeline.md)).
