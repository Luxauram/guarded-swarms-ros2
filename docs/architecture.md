# Architecture

Guarded Swarms separates two layers. A digital coordination layer turns sensor
observations into missions, through a chain of TB-CSPN transitions that a human
supervisor must authorise. A safety layer on each vehicle can veto its commands,
whatever the coordination layer decides. This page describes how the digital
twin implements them in the coastal scenario.

```
 radar, RF, acoustic, EO agents ──► ObsToken            /obs_tokens
        │
        ▼  TB-CSPN coordination layer
 interpretation, then time-windowed joins:
   radar + RF ──► CandidateTarget (T3)
   CandidateTarget + EO ──► ConfirmedThreat (T5)      /interp_tokens
        │
 supervisor decision ──► SupervisorAuth               /supervisor_auth
        │
 ConfirmedThreat + authorisation ──► MissionToken (T6) /mission_tokens
        │
 dispatch ──► VehicleTask per vehicle (T7)            /vehicle_tasks
        │
        ▼  vehicle side
 UAV worker ──► safety gate ──► PX4       UGV worker ──► PX4
      ▲              ▲                         ▲
      └─ Safety Board ┘                    Safety Board
         (veto)                            (veto)
```

## The coastal scenario

The world is generated with a fixed seed: a town behind a beach, a harbour, and
the sea to the north. Two UAVs hover over their launch pads, UAV0 at 12 m and
UAV1 at 20 m, and a UGV patrols the shore road. With `N_UAVS` from 2 to 8 the
fleet grows by interceptor UAVs on further pads along the coast; the fleet is
described in `src/guarded_swarms_bringup/config/coastal_fleet.yaml`. Every
vehicle runs its own PX4 instance and uXRCE-DDS agent, in its own namespace.

The intruder is a scripted, open-loop UAV that approaches the coast at 6 m/s in
simulated time, along one of three ingress paths: frontal, east-deep or rear.
With its `transmitting` parameter off, it keeps radio silence, so that the RF
agent has nothing to detect.

## Tokens

The tokens carry a stamp in simulated time and a time to live (`ttl_s`). An
interpretation also carries, in `origin`, the ids of the tokens it was derived
from, so a mission can be traced back through the threat to the observations
behind it.

| Token            | Topic              | Producer                                                           |
| ---------------- | ------------------ | ------------------------------------------------------------------ |
| `ObsToken`       | `/obs_tokens`      | The sensing agents                                                 |
| `InterpToken`    | `/interp_tokens`   | The interpretation and join transitions                            |
| `SupervisorAuth` | `/supervisor_auth` | The supervisor: the console, a command, or the scripted supervisor |
| `MissionToken`   | `/mission_tokens`  | T6                                                                 |
| `VehicleTask`    | `/vehicle_tasks`   | T7                                                                 |

## Sensing

Four agents (`guarded_swarms_sensing`) observe the intruder, each with its own
coverage and error model: a radar and an RF receiver inland, acoustic buoys at
sea, and an electro-optical camera carried by UAV0. Each agent has a `seed`
parameter, so that the runs of a campaign repeat the same random draws.

## The coordination chain

The transitions of `guarded_swarms_tbcspn` read and write tokens:

- **Interpretation.** Each observation becomes an interpretation: `PossibleUAV`
  from the radar, `LikelyDroneLink` from the RF receiver,
  `ConfirmedAerialObject` from the EO camera.
- **T3** joins a `PossibleUAV` and a `LikelyDroneLink` of the same target,
  within a time window (3 s, or `T3_WINDOW_S`), into a `CandidateTarget`.
- **T5** joins a `CandidateTarget` and a `ConfirmedAerialObject` into a
  `ConfirmedThreat`, valid for 10 s. The acoustic modality is not required by
  either join.
- **T6** releases a `MissionToken` when a `ConfirmedThreat` and an authorise
  decision for the same target are valid at the same time. Without an
  authorisation, or with a denial, no mission is formed: the threat waits for
  a decision only while it is valid.
- **T7** dispatches the mission: an intercept task to the UAV nearest the
  target, among all the UAVs of the fleet, and an observe task to the UGV.

## The supervisor

T6 needs a `SupervisorAuth` for the target. In a live demonstration the
supervisor decides in the browser decision panel of the supervisor console
(`console/`). In automated runs `scripted_supervisor_node`
(`guarded_swarms_supervisor`) takes one decision per target, authorise, deny or
none, a set delay after the first `ConfirmedThreat`; an authorisation is valid
for 15 s. See
[`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md).

## The vehicles

Each vehicle has one worker (`guarded_swarms_control`), its only controller:

- `uav_worker_node` keeps its UAV in hover over its pad. On an intercept task it
  flies toward the target at a bounded speed, facing the direction of travel,
  and follows the live track of the target; when the mission expires it returns
  to its pad.
- `ugv_worker_node` keeps the UGV on its patrol and, on an observe task, drives
  it to a shore observation point.

See [`guarded_swarms_control`](packages/guarded_swarms_control.md).

## The safety layer

Every vehicle has a Safety Board (`safety_board_node`, in
`guarded_swarms_safety`) that knows nothing of the coordination layer. It reads
the vehicle's proximity lidar, attitude, battery and altitude, and vetoes with
OR logic: one reading out of bounds, or older than 5 s, is enough. It publishes
its state on `safety_status`, and its verdict on each command of the worker on
`actuator_cmd_safe`. The thresholds are set per vehicle type. On the UAVs the
proximity veto trips below 10 m, so that a UAV at transit speed can brake before
an obstacle, and the attitude veto beyond 60°, since the autopilot tilts a UAV
up to 45° to accelerate.

On the UAVs, `px4_safety_gate_node` sits on the setpoint path between the worker
and PX4. By default it forwards the worker's setpoints, and the worker itself
holds the UAV under a veto. With `veto_by` set to `gate`, the gate holds the UAV
at its position while the board reports unsafe, whatever the worker proposes, so
a faulty worker cannot drive the vehicle into danger.

## Time

The intruder, the sensing agents, the transitions and the scripted supervisor
run on simulated time, so the latencies measured in simulated time do not depend
on the load of the machine. The timers of the workers and of the Safety Board
run on the wall clock: with the simulation slower than real time, they send more
messages per second of simulated time (see
[Analysis](experiments/analysis.md#fleet-size)).
