# Stress Testing Guide - Guarded Swarms

## Why You Don't See Conflicts

**By Design** the default agent zones are intentionally separated to simulate realistic distributed operations:

```
Agent A: center (0,0)    ±5m → covers (-5,-5) to (5,5)
Agent B: center (15,0)   ±5m → covers (10,-5) to (20,5)
Agent C: center (0,15)   ±5m → covers (-5,10) to (5,20)
Agent D: center (15,15)  ±5m → covers (10,10) to (20,20)
```

**Minimum distance between zones: 5 meters** → NO overlap possible!

This is a **feature** for normal operations but prevents seeing arbitration logic in action.

---

## How to Force Conflicts (3 Methods)

### Method 1: Overlapping Zones (RECOMMENDED)

**Step 1:** Edit `src/guarded_swarms_coordinator/guarded_swarms_coordinator/agent_node.py`

Find this section (~line 111):

```python
def _initialize_operational_area(self) -> dict:
    zones = {
        "agent_A": {"center": [0.0, 0.0, 5.0], "size": 10.0},
        "agent_B": {"center": [15.0, 0.0, 5.0], "size": 10.0},
        "agent_C": {"center": [0.0, 15.0, 5.0], "size": 10.0},
        "agent_D": {"center": [15.0, 15.0, 5.0], "size": 10.0},
    }
```

**Replace with:**

```python
def _initialize_operational_area(self) -> dict:
    zones = {
        "agent_A": {"center": [0.0, 0.0, 5.0], "size": 15.0},   # ±7.5m
        "agent_B": {"center": [3.0, 3.0, 5.0], "size": 15.0},   # Overlaps A
        "agent_C": {"center": [-3.0, 3.0, 5.0], "size": 15.0},  # Overlaps A & B
        "agent_D": {"center": [0.0, -3.0, 5.0], "size": 15.0},  # Overlaps all
    }
```

**Step 2:** Rebuild

```bash
make ros2-coordinator-reb
```

**Step 3:** Test

```bash
make demo-coordinator
# Agents: 4
# Mode: 2 (priority)
# Priorities: A=10, B=7, C=5, D=3
```

**Expected Results:**

- ✗ **High rejection rate** (~30-50%)
- ⚠ **Frequent revocations** when high-priority conflicts
- ✓ **A (priority 10) dominates** the shared space
- Dashboard shows mode detection working

---

### Method 2: Larger Bounding Boxes

**Edit `agent_node.py` line ~125:**

Change from:

```python
STANDARD_BBOX_WIDTH = 5.0
STANDARD_BBOX_HEIGHT = 5.0
STANDARD_BBOX_DEPTH = 3.0
```

To:

```python
STANDARD_BBOX_WIDTH = 15.0   # Much larger requests
STANDARD_BBOX_HEIGHT = 15.0
STANDARD_BBOX_DEPTH = 3.0
```

**Result:** Even with separated zones, large bboxes will overlap!

---

### Method 3: Many Agents (Manual Launch)

**Terminal 1:** Launch coordinator only

```bash
cd ~/path/to/guarded-swarms-ros2
source install/setup.bash
ros2 run guarded_swarms_coordinator coordinator_node \
    --ros-args -p coordinator_id:=coordinator_R1 -p arbitration_mode:=priority
```

**Terminal 2:** Launch many agents in the same zone

```bash
cd ~/path/to/guarded-swarms-ros2
source install/setup.bash

# Launch 10 agents - all will compete for the same zone
for i in {1..10}; do
    ros2 run guarded_swarms_coordinator agent_node \
        --ros-args -p agent_id:=stress_agent_$i -p priority:=$((RANDOM % 10)) &
done
```

**Note:** These agents will use default zone (0,0), so they will all conflict.

**Expected:** High rejection rate, constant preemptions.

---

## Test Scenarios After Modification

### Scenario 1: Priority Dominance

```bash
make demo-coordinator
# Agents: 4
# Mode: 2 (priority)
# Priorities: A=10, B=3, C=3, D=3
```

**Expected:**

- A gets almost everything (10 vs 3)
- B, C, D constantly rejected when conflicting with A
- Some B/C/D approvals when A not in area

---

### Scenario 2: Equal Priority Chaos

```bash
make demo-coordinator
# Agents: 4
# Mode: 1 (fcfs)
# Priorities: A=5, B=5, C=5, D=5
```

**Expected:**

- Pure FCFS, no preemptions
- Random distribution of approvals
- ~25% success rate per agent

---

### Scenario 3: Hybrid Threshold Test

```bash
make demo-coordinator
# Agents: 4
# Mode: 3 (hybrid)
# Priorities: A=10, B=7, C=4, D=1
```

**Expected with threshold=3:**

- A (10) can preempt B (7): diff=3 ≥ threshold ✓
- A (10) can preempt C (4): diff=6 ≥ threshold ✓
- B (7) can preempt C (4): diff=3 ≥ threshold ✓
- B (7) CANNOT preempt A (10): diff=-3, uses FCFS
- C (4) CANNOT preempt B (7): diff=-3, uses FCFS

---

## Metrics to Monitor

### Dashboard Indicators

- **Rejection Rate:** Should be 30-70% with overlapping zones
- **Revocation Count:** Should be >0 in priority/hybrid mode
- **Mode Detection:** Should show "PRIORITY", "FCFS", or "HYBRID"
- **Border Colors:** High priority = red/orange, visible preemption

### Terminal Logs

Look for:

```
REJECTED: agent_B ... conflict_with_agent_A_priority_10
REVOKED: agent_C ... preempted_by_agent_A_priority_10
```
