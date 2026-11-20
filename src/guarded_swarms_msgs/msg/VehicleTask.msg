# VehicleTask - a dispatched, vehicle-specific task
#
# Produced by the dispatch transition (T7) from an authorised InterceptMission,
# and consumed by a worker agent. The architecture names two tokens here,
# UAVTask and UGVTask; this is one message with a vehicle_kind field, so the
# two worker agents subscribe to one topic and each filters for its own kind.
#
# A worker agent is the translation bridge across the digital-physical
# boundary: it turns this coordination-level task into platform-specific
# commands (waypoints, an interception trajectory, an observation goal). The
# executor platforms never see this token; they only execute what their worker
# agent produces.

# Identifier of this task.
string task_id

# The mission this task was dispatched from, and the target it concerns.
string mission_id
string target_id
geometry_msgs/Point target_position

# Which class of vehicle this task is for. A worker agent ignores tasks not of
# its kind.
string vehicle_kind

# The specific vehicle assigned, as a MAV_SYS_ID. The dispatch transition
# chooses it (e.g. the nearest UAV); the worker agent for that vehicle acts on
# it. 0 means "any vehicle of this kind" if assignment is left to the worker.
uint8 assigned_system

# What the vehicle is being asked to do.
string task_type

# Full provenance, carried from the MissionToken: the justification chain plus
# the mission id, so a command executed at the edge can still be traced back to
# the observations and the human authorisation that produced it.
string[] justification

# Simulated time of dispatch, and validity.
builtin_interfaces/Time t
float64 ttl_s

# Vehicle kinds (the UAVTask / UGVTask distinction)
string KIND_UAV=uav
string KIND_UGV=ugv

# Task types
string TASK_INTERCEPT=intercept
string TASK_OBSERVE=observe
string TASK_RECOVER=recover
