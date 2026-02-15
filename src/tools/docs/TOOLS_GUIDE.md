# Tools Directory

Utility tools for testing and visualizing the Guarded Swarms coordination system.

## Contents

### `dashboard.py`

Real-time visualization dashboard for monitoring coordination system activity.

**What it does:**

- Displays spatial map with agent requests (2D top view)
- Shows live event log with authorization decisions
- Tracks approval/rejection statistics per agent
- Color-coded visualization by agent (A=blue, B=red, C=green, D=orange)
- Priority-coded border colors (red=emergency, orange=high, blue=normal, gray=low)

**Usage:**

```bash
ros2 run guarded_swarms_coordinator dashboard
```

**Notes:**

- Requires coordinator and agents to be running
- Subscribes to `/geometry_tokens` and `/auth_tokens`
- Runs in separate window with Tkinter GUI
- Auto-detects arbitration mode from conflict patterns

---

### `demo.launch.py`

Launch file to start the complete coordination system in one command.

**What it does:**

- Launches 1 coordinator node
- Launches 1-4 agent nodes (configurable)
- Configures all nodes with specified parameters

**Basic Usage:**

```bash
# Default configuration (4 agents, priority mode)
ros2 launch guarded_swarms_coordinator demo.launch.py

# Custom configuration via Makefile (recommended)
make demo-coordinator  # Interactive menu
```

**Available Parameters:**

- `arbitration_mode`: fcfs | priority | hybrid (default: priority)
- `coordinator_id`: Coordinator identifier (default: coordinator_R1)
- `num_agents`: Number of agents 1-4 (default: 4)
- `priority_A/B/C/D`: Agent priorities 0-10 (default: 5)

---

## Test Scenarios

### 1. Conflict-Free Operation (All Approved)

**Scenario:** Agents in separate zones, no spatial overlap

```bash
make demo-coordinator
# Agents: 4
# Mode: 2 (priority)
# Priorities: A=5, B=5, C=5, D=5
```

**Expected:** All requests approved ✓

---

### 2. Priority-Based Preemption

**Scenario:** Emergency agent preempts normal operations

```bash
make demo-coordinator
# Agents: 2
# Mode: 2 (priority)
# Priorities: A=10 (emergency), B=3 (low)
```

**Expected:** When overlap occurs, A preempts B

**To force conflicts:** Agents spawn in default zones. Wait ~10-20 seconds for random positions to overlap.

---

### 3. FCFS with Equal Priority

**Scenario:** First-come-first-serve, no preemption

```bash
make demo-coordinator
# Agents: 4
# Mode: 1 (fcfs)
# Priorities: A=5, B=5, C=5, D=5
```

**Expected:** First token in conflict zone wins, no revocations

---

### 4. Hybrid Mode with Threshold

**Scenario:** Priority difference must exceed threshold (3) for preemption

```bash
make demo-coordinator
# Agents: 3
# Mode: 3 (hybrid)
# Priorities: A=10, B=7, C=3
```

**Expected:**

- A (10) can preempt C (3) - diff = 7 > threshold
- A (10) can preempt B (7) - diff = 3 >= threshold
- B (7) cannot preempt C (3) - diff = 4, uses FCFS

---

### 5. High-Conflict Stress Test

**Scenario:** Force maximum spatial conflicts

**Method 1 - Modify agent zones temporarily:**
Edit `agent_node.py` zones to overlap:

```python
zones = {
    "agent_A": {"center": [0.0, 0.0, 5.0], "size": 10.0},
    "agent_B": {"center": [2.0, 2.0, 5.0], "size": 10.0},  # Overlaps A
    "agent_C": {"center": [1.0, 1.0, 5.0], "size": 10.0},  # Overlaps A & B
    "agent_D": {"center": [3.0, 3.0, 5.0], "size": 10.0},  # Overlaps all
}
```

Then run:

```bash
make coordinator-rebuild  # Rebuild with changes
make demo-coordinator
# Agents: 4
# Mode: 2 (priority)
# Priorities: A=10, B=7, C=5, D=3
```

**Expected:** Frequent rejections and revocations, A dominates

**Method 2 - Run multiple demos simultaneously:**

```bash
# Terminal 1
make demo-coordinator
# Agents: 4, Mode: priority

# Terminal 2 (after coordinator is running)
# Manually launch extra agents:
make docker-shell
source /workspace/install/setup.bash
ros2 run guarded_swarms_coordinator agent_node --ros-args -p agent_id:=agent_E -p priority:=8 &
ros2 run guarded_swarms_coordinator agent_node --ros-args -p agent_id:=agent_F -p priority:=6 &
ros2 run guarded_swarms_coordinator agent_node --ros-args -p agent_id:=agent_G -p priority:=4 &
```

**Expected:** 7 agents competing, high rejection rate, priority-based wins

---

## Quick Start

1. Launch the system:

   ```bash
   make demo-coordinator  # Follow interactive prompts
   ```

2. Open dashboard in another terminal:

   ```bash
   make demo-tkinter
   ```

3. Watch real-time coordination decisions on the GUI
