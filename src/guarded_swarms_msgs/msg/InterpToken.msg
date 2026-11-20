# InterpToken - interpreted, semantic observation
#
# Structure:  InterpToken = <label, origin, confidence, t, ttl>
#
# Produced by a TB-CSPN transition that reads one or more ObsTokens and assigns
# them a meaning. This is where raw sensing becomes something the coordination
# layer can reason about.
#
# `origin` is what makes the chain auditable: every interpretation names the
# tokens it was derived from, so a mission can be traced back to the specific
# observations that justified it. That traceability is a stated property of the
# architecture, not a debugging convenience, and it is what a human supervisor
# is shown before authorising a mission.

# Unique identifier of this interpretation.
string id

# Target this interpretation refers to.
string target_id

# Semantic label. Use the LABEL_* constants.
string label

# Identifiers of the tokens this interpretation was derived from: ObsToken.id
# for a first-level interpretation, InterpToken.id when transitions are
# chained. Never empty for a well-formed token.
string[] origin

# Confidence in [0, 1]. How it combines the confidences of the origin tokens is
# a property of the transition that produced it, not of this message.
float64 confidence

# Simulated time at which the interpretation was produced.
builtin_interfaces/Time t

# Validity window in seconds. Expiry is what makes the time-windowed joins fail
# to combine when a confirmation arrives too late, so that no mission forms on
# stale evidence.
float64 ttl_s

# Best available position estimate for the target, world ENU. Not part of the
# token structure above, but the worker agents need somewhere to be sent, and
# carrying it here keeps them from having to re-read the observations.
geometry_msgs/Point position

# Labels of the TB-CSPN chain
string LABEL_POSSIBLE_UAV=PossibleUAV
string LABEL_LIKELY_DRONE_LINK=LikelyDroneLink
string LABEL_CONFIRMED_AERIAL_OBJECT=ConfirmedAerialObject
string LABEL_CANDIDATE_TARGET=CandidateTarget
string LABEL_CONFIRMED_THREAT=ConfirmedThreat

# Conflicting interpretation: the RF consultant reads the same time window as
# legitimate civilian telemetry.
# The concordance guard on the CandidateTarget transition then blocks, and the
# candidate is never formed.
string LABEL_LIKELY_CIVILIAN_TRAFFIC=LikelyCivilianTraffic
