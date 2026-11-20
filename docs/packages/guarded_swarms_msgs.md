# guarded_swarms_msgs

Messages of the coordination layer: the tokens that carry a detection from the
sensing agents, through the TB-CSPN transitions and the supervisor's decision,
to a task for a vehicle. Their role in the chain is described in
[Architecture](../architecture.md#tokens); this page is the reference of their
fields and constants.

| Message          | Topic              | Produced by                                        | Consumed by                                                                   |
| ---------------- | ------------------ | -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `ObsToken`       | `/obs_tokens`      | The sensing agents of `guarded_swarms_sensing`     | T1, T2 and T4                                                                 |
| `InterpToken`    | `/interp_tokens`   | T1 to T5                                           | T3 and T5, T6, the scripted supervisor, the console bridge, `uav_worker_node` |
| `SupervisorAuth` | `/supervisor_auth` | The supervisor console and the scripted supervisor | T6                                                                            |
| `MissionToken`   | `/mission_tokens`  | T6                                                 | T7                                                                            |
| `VehicleTask`    | `/vehicle_tasks`   | T7                                                 | `uav_worker_node` and `ugv_worker_node`                                       |

T1, T2 and T4 are instances of `interpretation_node`, T3 and T5 of
`candidate_transition_node`, T6 is `mission_transition_node` and T7
`dispatch_transition_node`, all in `guarded_swarms_tbcspn`.

Every token has a time `t` and a validity `ttl_s` in seconds: a token is valid
from `t` to `t + ttl_s`, and the joins (T3, T5 and T6) combine only tokens that
are still valid. All the nodes of the coordination layer run with
`use_sim_time`, so `t` is simulated time.

The messages use `geometry_msgs/Point` for positions and
`builtin_interfaces/Time` for times.

## ObsToken

A raw observation of one sensing agent. It states what a sensor measured, not
what the measurement means.

| Field        | Type                      | Meaning                                                                                              |
| ------------ | ------------------------- | ---------------------------------------------------------------------------------------------------- |
| `id`         | `string`                  | Unique identifier, the handle by which an `InterpToken` names the observation in its `origin`        |
| `target_id`  | `string`                  | Target of the observation; empty when the agent attributes it to no target, as for a false detection |
| `source`     | `string`                  | Emitting modality, one of the `SOURCE_*` constants                                                   |
| `kind`       | `string`                  | Layout of `value`, one of the `KIND_*` constants                                                     |
| `value`      | `float64[]`               | Payload, read according to `kind`                                                                    |
| `confidence` | `float64`                 | Detection confidence in [0, 1], as reported by the agent                                             |
| `t`          | `builtin_interfaces/Time` | Simulated time of the observation                                                                    |
| `ttl_s`      | `float64`                 | Validity in seconds                                                                                  |

| Source constant   | Value      | Agent                 | Interpreted by |
| ----------------- | ---------- | --------------------- | -------------- |
| `SOURCE_RADAR`    | `radar`    | `radar_agent_node`    | T1             |
| `SOURCE_RF`       | `rf`       | `rf_agent_node`       | T2             |
| `SOURCE_ACOUSTIC` | `acoustic` | `acoustic_agent_node` | none           |
| `SOURCE_EO`       | `eo`       | `eo_agent_node`       | T4             |

| Kind constant    | Value       | `value`                                                                | Emitted by |
| ---------------- | ----------- | ---------------------------------------------------------------------- | ---------- |
| `KIND_TRACK`     | `track`     | x, y, z, vx, vy, vz: position in metres and velocity in m/s, world ENU | Radar      |
| `KIND_BEARING`   | `bearing`   | bearing and elevation in radians, range in metres, sensor frame        | Acoustic   |
| `KIND_SIGNATURE` | `signature` | centre frequency and bandwidth in Hz, received signal strength in dBm  | RF         |
| `KIND_VISUAL`    | `visual`    | x, y, z: position in metres, world ENU                                 | EO         |

No transition of the chain interprets the acoustic observations: the agent
publishes them, and the chain forms its threats from radar, RF and EO.

In the digital twin the agents synthesise their observations from the ground
truth of the intruder, with a model of range, latency, noise and confidence for
each modality. Detection and data association are out of scope, so the agent
knows the `target_id` of what it observes instead of inferring it.

## InterpToken

An interpretation: an observation, or a pair of interpretations, to which a
transition has given a meaning, named by its `label`.

| Field        | Type                      | Meaning                                                                    |
| ------------ | ------------------------- | -------------------------------------------------------------------------- |
| `id`         | `string`                  | Unique identifier, `<label>-<n>`, numbered by the transition that emits it |
| `target_id`  | `string`                  | Target of the interpretation                                               |
| `label`      | `string`                  | Meaning, one of the `LABEL_*` constants                                    |
| `origin`     | `string[]`                | Identifiers of the tokens it was derived from; never empty                 |
| `confidence` | `float64`                 | Confidence in [0, 1]                                                       |
| `t`          | `builtin_interfaces/Time` | Simulated time; see below                                                  |
| `ttl_s`      | `float64`                 | Validity in seconds, set by the transition that emits it                   |
| `position`   | `geometry_msgs/Point`     | Best position estimate of the target, world ENU; zero when none is known   |

The fields are filled differently by the two kinds of transition:

| Field        | First-level interpretation (T1, T2, T4)                        | Join (T3, T5)                                            |
| ------------ | -------------------------------------------------------------- | -------------------------------------------------------- |
| `origin`     | The `id` of the observation                                    | The `origin` of both fused tokens, then the `id` of both |
| `confidence` | The confidence of the observation                              | The product of the confidences of the two fused tokens   |
| `t`          | The `t` of the observation, so the age of the evidence is kept | The time of the join                                     |
| `position`   | The position of a `track` observation; zero for the others     | The position of the first fused token that has one       |

| Label constant                  | Value                   | Emitted by                                                |
| ------------------------------- | ----------------------- | --------------------------------------------------------- |
| `LABEL_POSSIBLE_UAV`            | `PossibleUAV`           | T1, from a radar observation                              |
| `LABEL_LIKELY_DRONE_LINK`       | `LikelyDroneLink`       | T2, from an RF observation                                |
| `LABEL_CONFIRMED_AERIAL_OBJECT` | `ConfirmedAerialObject` | T4, from an EO observation                                |
| `LABEL_CANDIDATE_TARGET`        | `CandidateTarget`       | T3, joining `PossibleUAV` and `LikelyDroneLink`           |
| `LABEL_CONFIRMED_THREAT`        | `ConfirmedThreat`       | T5, joining `CandidateTarget` and `ConfirmedAerialObject` |
| `LABEL_LIKELY_CIVILIAN_TRAFFIC` | `LikelyCivilianTraffic` | T2, when the RF interpretation is set to it               |

The label each transition emits is a parameter of the node, set in
`tbcspn.launch.py`. With `RF_LABEL=LikelyCivilianTraffic`, T2 reads the RF
emissions as civilian traffic: T3 has nothing to join with the radar, and no
`CandidateTarget` forms.

The console bridge republishes the `ConfirmedThreat` tokens on
`/console/threat`, for the supervisor console.

## SupervisorAuth

The supervisor's decision on one target: authorise the release of a mission,
or refuse it.

| Field           | Type                      | Meaning                                                                     |
| --------------- | ------------------------- | --------------------------------------------------------------------------- |
| `target_id`     | `string`                  | Target of the decision; must match the `target_id` of the `ConfirmedThreat` |
| `authorised_by` | `string`                  | Identity of the supervisor, carried into the mission                        |
| `decision`      | `string`                  | One of the `DECISION_*` constants                                           |
| `t`             | `builtin_interfaces/Time` | Simulated time of the decision                                              |
| `ttl_s`         | `float64`                 | Validity in seconds                                                         |

| Constant             | Value       |
| -------------------- | ----------- |
| `DECISION_AUTHORISE` | `authorise` |
| `DECISION_DENY`      | `deny`      |

T6 releases a mission while a `ConfirmedThreat` and an authorisation for the
same target are both valid. A denial is logged and releases nothing. T6 ignores
an authorisation with an empty `authorised_by`, and takes an unset `t` as the
time the authorisation arrives, so a decision published by hand needs no
timestamp.

The supervisor console signs its decisions as `console`; the scripted
supervisor signs them with its `authorised_by` parameter (see
[`guarded_swarms_supervisor`](guarded_swarms_supervisor.md)).

## MissionToken

A mission released by T6.

| Field             | Type                      | Meaning                                                       |
| ----------------- | ------------------------- | ------------------------------------------------------------- |
| `mission_id`      | `string`                  | Unique identifier, `mission-<n>`                              |
| `type`            | `string`                  | What is asked of the swarm, one of the `TYPE_*` constants     |
| `target_id`       | `string`                  | Target of the mission                                         |
| `target_position` | `geometry_msgs/Point`     | Position of the `ConfirmedThreat` that released it, world ENU |
| `justification`   | `string[]`                | Provenance of the mission; see [Provenance](#provenance)      |
| `authorised_by`   | `string`                  | The `authorised_by` of the authorisation that released it     |
| `t`               | `builtin_interfaces/Time` | Simulated time of the release                                 |
| `ttl_s`           | `float64`                 | Validity in seconds, the `mission_ttl_s` parameter of T6      |

| Constant         | Value       | Use                                                         |
| ---------------- | ----------- | ----------------------------------------------------------- |
| `TYPE_INTERCEPT` | `intercept` | Released by T6, the default of its `mission_type` parameter |
| `TYPE_OBSERVE`   | `observe`   | Defined; no transition of the chain uses it                 |
| `TYPE_RECOVER`   | `recover`   | Defined; no transition of the chain uses it                 |

## VehicleTask

A task for one vehicle, dispatched by T7. T7 dispatches each target once: an
intercept task to the UAV nearest to the target, and an observe task to the
UGV. A worker ignores the tasks of the other kind of vehicle and those assigned
to another vehicle.

| Field             | Type                      | Meaning                                                        |
| ----------------- | ------------------------- | -------------------------------------------------------------- |
| `task_id`         | `string`                  | Unique identifier, `<mission_id>-uav` or `<mission_id>-ugv`    |
| `mission_id`      | `string`                  | Mission the task was dispatched from                           |
| `target_id`       | `string`                  | Target of the mission                                          |
| `target_position` | `geometry_msgs/Point`     | The `target_position` of the mission                           |
| `vehicle_kind`    | `string`                  | Kind of vehicle, one of the `KIND_*` constants                 |
| `assigned_system` | `uint8`                   | MAV_SYS_ID of the vehicle assigned to the task                 |
| `task_type`       | `string`                  | What the vehicle is asked to do, one of the `TASK_*` constants |
| `justification`   | `string[]`                | Provenance of the task; see [Provenance](#provenance)          |
| `t`               | `builtin_interfaces/Time` | Simulated time of the dispatch                                 |
| `ttl_s`           | `float64`                 | Validity in seconds, the `ttl_s` of the mission                |

| Constant         | Value       | Use                              |
| ---------------- | ----------- | -------------------------------- |
| `KIND_UAV`       | `uav`       | Tasks for a UAV                  |
| `KIND_UGV`       | `ugv`       | Tasks for the UGV                |
| `TASK_INTERCEPT` | `intercept` | The task of the UAV              |
| `TASK_OBSERVE`   | `observe`   | The task of the UGV              |
| `TASK_RECOVER`   | `recover`   | Defined; T7 does not dispatch it |

## Provenance

Each token names the tokens it comes from, so that a task executed by a
vehicle can be traced back to the observations and to the decision that
released it. For a threat confirmed by radar, RF and EO, the `justification`
of each task lists, in order:

1. the radar observation;
2. the RF observation;
3. the `PossibleUAV` of T1;
4. the `LikelyDroneLink` of T2;
5. the EO observation;
6. the `CandidateTarget` of T3;
7. the `ConfirmedAerialObject` of T4;
8. the `ConfirmedThreat` of T5;
9. `auth:<authorised_by>`, for the supervisor's decision;
10. `mission:<mission_id>`, for the mission of T6.

Entries 1 to 7 are the `origin` of the `ConfirmedThreat`. T6 appends entries 8
and 9 to form the `justification` of the mission, and T7 appends entry 10 to
form that of each task.
