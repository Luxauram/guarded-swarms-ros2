# Supervisor console

The console is where a human supervisor takes the decision of T6 in an
interactive run. It shows the `ConfirmedThreat` of a target with the chain of
tokens behind it, and publishes the decision of the supervisor, authorise or
deny, on `/supervisor_auth`. No mission is released without an authorisation.
In automated runs the scripted supervisor decides instead (see
[`guarded_swarms_supervisor`](packages/guarded_swarms_supervisor.md)).

| Part                               | Purpose                                                                                              |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `console/decision_panel.html`      | The panel, a single page opened in a browser                                                         |
| `console/console_bridge_node.py`   | Republishes the `ConfirmedThreat`s for the panel, on `/console/threat`                               |
| rosbridge (`rosbridge_server`)     | Carries the topics between ROS 2 and the browser, over a WebSocket                                   |
| `scripts/pipeline/demo_console.sh` | Starts the intruder, the sensing agents and the coordination layer, and prints each mission released |

## Running it

Four terminals, each at the root of the repository with the workspace sourced:

```bash
# 1. the scenario: Gazebo, PX4 and the vehicles
make demo-coastal
# 2. rosbridge, on ws://localhost:9090
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
# 3. the console bridge
python3 console/console_bridge_node.py
# 4. the intruder, the sensing agents and T1 to T7
./scripts/pipeline/demo_console.sh
```

Then open `console/decision_panel.html` in a browser. rosbridge must be started
with the workspace sourced, or it does not know the messages of
`guarded_swarms_msgs`. The panel loads roslib from a CDN, so the browser needs
network access.

The console can also decide in a run of `scripts/pipeline/test_pipeline.sh`:
with `MANUAL_AUTH=1` the test script does not start the scripted supervisor,
and the decision is left to the console (see
[Pipeline run scripts](scripts/pipeline.md#configuration)).

## The panel

`decision_panel.html` is a self-contained page: its styles and its script are
in the file, and the only thing it loads is roslib 1.4.1, the JavaScript client
of rosbridge.

- **Connection.** It connects to rosbridge at `ws://localhost:9090`, and shows
  the state of the connection in its header. When the connection closes, it
  retries every 2 s.
- **The threat.** Each `ConfirmedThreat` on `/console/threat` arms the panel,
  and shows its target, its confidence, its position in world ENU, how long ago
  it arrived, and its `origin`: the identifiers of the observations and
  interpretations it was formed from.
- **The decision.** "Authorise interception" and "Deny" publish one
  `SupervisorAuth` for the target shown, and add a line to the decision log of
  the page. The panel confirms that the decision was sent, and locks the
  buttons for 6 s; the next threat after that unlocks them.
- **A coasting track.** A `ConfirmedThreat` forms only while the intruder is in
  the cone of the EO camera, so the threats can stop for a while and resume.
  After 5 s without one the panel shows that its estimate is coasting, and
  keeps the buttons live; after 20 s it takes the track as lost, and disarms.

| Field of the decision | Value                          |
| --------------------- | ------------------------------ |
| `target_id`           | The target of the threat shown |
| `authorised_by`       | `console`                      |
| `decision`            | `authorise` or `deny`          |
| `t`                   | Zero                           |
| `ttl_s`               | 30 s                           |

The browser does not know the simulated clock, so the decision leaves `t` at
zero, which T6 takes as the time the decision arrives. Every time of the panel
is on the clock of the browser.

The panel does not see the missions. T6 holds an authorisation for its 30 s,
and releases the mission as soon as it also holds a valid `ConfirmedThreat` of
the target, valid for 10 s (see
[`guarded_swarms_tbcspn`](packages/guarded_swarms_tbcspn.md#mission_transition_node)).
An authorisation sent while the panel is coasting therefore waits in T6 for the
next threat. A denial releases nothing, and does not withdraw an authorisation
already sent. `demo_console.sh` prints each mission as T6 releases it.

The decision log lives in the page: reloading it clears the log.

## The console bridge

`console_bridge_node.py` subscribes to `/interp_tokens`, keeps the
`ConfirmedThreat`s, and republishes them unchanged on `/console/threat`, a topic
of which it is the only publisher. rosbridge sends every message of a
subscribed topic to the browser, as JSON over the WebSocket, so the panel
receives only the threats, not every interpretation of the chain.

| Topic             | Type                                  | Direction  | QoS                          |
| ----------------- | ------------------------------------- | ---------- | ---------------------------- |
| `/interp_tokens`  | `guarded_swarms_msgs/msg/InterpToken` | Subscribed | Reliable, volatile, depth 10 |
| `/console/threat` | `guarded_swarms_msgs/msg/InterpToken` | Published  | Reliable, volatile, depth 10 |

The node is not part of a package: it runs with `python3`, with the workspace
sourced for `guarded_swarms_msgs`. It logs at the first threat it forwards, and
then every 20.

## rosbridge

`install.sh` installs it, with `ros-humble-rosbridge-suite`. Its WebSocket
server listens on port 9090. It chooses the QoS of what it creates for the
panel; in the version of the Humble packages, 2.0:

- its publisher of `/supervisor_auth` offers transient local durability, with a
  lifespan of 1 s, as T6 requires (see [Interfaces](interfaces.md#qos));
- its subscription to `/console/threat` is best effort and volatile, which
  receives from the console bridge.

## demo_console.sh

Starts the rest of the chain for a demonstration of the console, without the
scripted supervisor:

1. the intruder, on a low path that ends inside the cone of the EO camera, so
   that the `ConfirmedThreat` holds while the supervisor decides;
2. the sensing agents;
3. the seven transitions of the coordination layer.

It then follows `/mission_tokens` and prints each mission T6 releases, with the
time: one line per authorisation that released a mission. With "Deny", or with
no decision, nothing is printed. Ctrl-C stops the nodes it started, and
leaves the scenario running.

| Variable               | Default                 | Meaning                                     |
| ---------------------- | ----------------------- | ------------------------------------------- |
| `IN_X`, `IN_Y`, `IN_Z` | `-24.0`, `180.0`, `2.0` | Start of the ingress, world ENU, m          |
| `TG_X`, `TG_Y`, `TG_Z` | `-24.0`, `20.0`, `2.0`  | End of the ingress, world ENU, m            |
| `INTRUDER_SPEED`       | `15.0`                  | Speed of the ingress, m/s                   |
| `INTRUDER_DELAY`       | `8.0`                   | Simulated time before the ingress starts, s |

The logs of the three launch files are in `/tmp/gs_demo_intruder.log`,
`/tmp/gs_demo_sensing.log` and `/tmp/gs_demo_tbcspn.log`.

## Troubleshooting

| Symptom                             | Check                                                                                                                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The header shows `connection error` | rosbridge is not running, or not on port 9090                                                                                                                                         |
| The panel stays empty               | `ros2 topic echo /console/threat`: if nothing arrives, the console bridge or the chain is not running; if threats arrive, check that rosbridge was started with the workspace sourced |
| A decision releases no mission      | `ros2 topic echo --qos-durability transient_local /supervisor_auth` shows the decision; T6 releases only while a `ConfirmedThreat` of the target is valid                             |
