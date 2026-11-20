# MissionToken - authorised mission, ready for dispatch
#
# Structure:
#   MissionToken = <mission_id, type, target, justification, t, ttl>
#
# Produced by the mission-release transition, which fires only when a
# ConfirmedThreat is present AND a human supervisor has provided the required
# authorisation token. The human-in-the-loop is part of the architecture, not
# an optional safeguard: no mission is synthesised without it.
#
# Consumed by the worker agents, which translate it into platform commands.

# Unique identifier of this mission.
string mission_id

# What is being asked of the swarm. Use the TYPE_* constants.
string type

# Target this mission is about.
string target_id

# Last known target position, world ENU, at the time of release.
geometry_msgs/Point target_position

# Full provenance chain: the identifiers of the InterpTokens, and through them
# the ObsTokens, that led to this mission. This is the audit trail shown to the
# supervisor before authorisation, and the record of why the swarm acted.
string[] justification

# Identifier of the supervisor who authorised the release. Empty is not a valid
# state for a dispatched mission: an empty value means the release transition
# fired without authorisation, which is a fault.
string authorised_by

# Simulated time of release.
builtin_interfaces/Time t

# Validity window in seconds. A mission that outlives its target's track should
# expire rather than be flown blind.
float64 ttl_s

# Mission types
string TYPE_INTERCEPT=intercept
string TYPE_OBSERVE=observe
string TYPE_RECOVER=recover
