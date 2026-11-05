# guarded_swarms_supervisor

Supervisor side of the mission-release transition (T6).

In the Guarded Swarms architecture no mission is released without an explicit
human decision: T6 turns a `ConfirmedThreat` into an `InterceptMission` only
when a `SupervisorAuth` that authorises the same target is also live. In an
interactive run the decision comes from the supervisor console. In an
experiment campaign it must be repeatable, and this package provides the
scripted supervisor that issues it.

| Item                          | Purpose                                                    |
| ----------------------------- | ---------------------------------------------------------- |
| `scripted_supervisor_node`    | Issues one decision per target, after a configurable delay |
| `launch/supervisor.launch.py` | Starts the node, configured from environment variables     |

## scripted_supervisor_node

### Behaviour

1. Listens to `/interp_tokens` for `ConfirmedThreat` tokens.
2. At the first `ConfirmedThreat` of a target, starts a timer of
   `decision_delay_s` seconds of simulated time.
3. When the timer expires, publishes one `SupervisorAuth` for that target on
   `/supervisor_auth`, carrying the configured decision.

The node decides once per target in a run: later `ConfirmedThreat` tokens for a
target already decided are ignored. Since T6 consumes an authorisation when it
releases a mission, one decision releases at most one mission. With
`decision: none` the node publishes nothing, which reproduces a supervisor who
never answers.

The delay starts when the `ConfirmedThreat` reaches the node and is measured on
the simulation clock (`use_sim_time`), so it does not depend on the real-time
factor of the run.

### Topics

| Topic              | Type                                     | Direction  | QoS                                 |
| ------------------ | ---------------------------------------- | ---------- | ----------------------------------- |
| `/interp_tokens`   | `guarded_swarms_msgs/msg/InterpToken`    | Subscribed | Reliable, volatile, depth 50        |
| `/supervisor_auth` | `guarded_swarms_msgs/msg/SupervisorAuth` | Published  | Reliable, transient local, depth 10 |

The publisher offers the durability that T6 requests and lives for the whole
run, so a subscriber that joins late, such as T6 or a bag recorder, still
receives the decision.

### Parameters

| Parameter          | Type   | Default               | Meaning                                                              |
| ------------------ | ------ | --------------------- | -------------------------------------------------------------------- |
| `decision`         | string | `authorise`           | `authorise`, `deny` or `none`                                        |
| `decision_delay_s` | double | `0.0`                 | Decision time in simulated seconds; must be ≥ 0                      |
| `ttl_s`            | double | `15.0`                | Validity of the decision in seconds; must be > 0                     |
| `authorised_by`    | string | `scripted_supervisor` | Identity recorded in the decision and in the mission's justification |
| `require_label`    | string | `ConfirmedThreat`     | Interpretation label that calls for a decision                       |

An invalid value stops the node at start-up, with an error that names the
parameter.

### The decision message

| Field           | Value                           |
| --------------- | ------------------------------- |
| `target_id`     | Target of the `ConfirmedThreat` |
| `authorised_by` | The `authorised_by` parameter   |
| `decision`      | `authorise` or `deny`           |
| `t`             | Simulated time of the decision  |
| `ttl_s`         | The `ttl_s` parameter           |

Since `t` is set, a recorded bag gives the exact instant of each decision on the
simulation clock.

## supervisor.launch.py

Starts the node with `use_sim_time` and reads its configuration from
environment variables, as the other scenario settings do, so that a batch
script can change it run by run.

| Variable       | Parameter          | Default     |
| -------------- | ------------------ | ----------- |
| `DECISION`     | `decision`         | `authorise` |
| `AUTH_DELAY_S` | `decision_delay_s` | `0.0`       |
| `AUTH_TTL_S`   | `ttl_s`            | `15.0`      |

An unset or empty variable takes the default; an invalid value stops the launch
with an error.

```bash
# Authorise as soon as the first ConfirmedThreat arrives (default)
ros2 launch guarded_swarms_supervisor supervisor.launch.py

# Deny, 5 simulated seconds after the first ConfirmedThreat
DECISION=deny AUTH_DELAY_S=5 ros2 launch guarded_swarms_supervisor supervisor.launch.py
```

## Use in the test scripts

`scripts/pipeline/test_pipeline.sh` starts the scripted supervisor with the
other layers, unless `MANUAL_AUTH=1`, in which case the supervisor console
decides. `scripts/record/record_run.sh` passes the three variables to the run:

```bash
# Nominal run, authorised immediately
./scripts/record/record_run.sh coastal

# Supervisor decision time of 10 s
AUTH_DELAY_S=10 ./scripts/record/record_run.sh delay-10

# Counterfactual: authorisation denied
DECISION=deny ./scripts/record/record_run.sh deny
```

## Monitoring and manual decisions

Watch the decisions:

```bash
ros2 topic echo --qos-durability transient_local /supervisor_auth
```

Requesting transient local durability lets the subscriber also receive a
decision published before it started.

Without the scripted supervisor, a decision can be published by hand. T6
requests transient local durability, so the publisher must offer it as well:

```bash
ros2 topic pub --once --keep-alive 5 --qos-durability transient_local \
  /supervisor_auth guarded_swarms_msgs/msg/SupervisorAuth \
  "{target_id: 'intruder', authorised_by: 'operator', decision: 'authorise', ttl_s: 15.0}"
```

T6 treats an unset `t` as the moment it receives the decision.

## Design notes

**Why a node.** Up to version 0.1.0 the test script authorised from the command
line, with three `gz model` calls followed by `ros2 topic pub`. That put 12–15 s
of test-harness overhead between the first `ConfirmedThreat` and the
authorisation, and a publisher that lived only a few seconds could miss T6
altogether. With the scripted supervisor the only delay is the configured one,
it is measured on the simulation clock, and the decision cannot be lost.

**Limitations.**

- The same decision and the same delay apply to every target of a run.
- A target is decided once per run: if a decision expires unused and the target
  is confirmed again later, no new decision is issued.
- The decision time is a fixed delay per run. Variability across supervisors,
  where needed, is modelled by varying `AUTH_DELAY_S` from run to run.
