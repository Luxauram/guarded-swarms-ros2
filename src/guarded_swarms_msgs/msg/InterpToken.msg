# InterpToken - interpreted, semantic observation
#
# Structure from Borghoff, Bottoni and Pareschi (2026), IET Radar, Sonar and
# Navigation, Section 3.2:  InterpToken = <label, origin, confidence, t, ttl>
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

# Semantic label. Use the LABEL_* constants, which follow the naming of
# Figure 4 in the paper.
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

# Validity window in seconds. Expiry is what makes the time-windowed joins of
# Section 5.3 fail to combine when a confirmation arrives too late, which is
# one of the counterfactual trajectories the evaluation has to reproduce.
float64 ttl_s

# Best available position estimate for the target, world ENU. Not part of the
# structure in the paper, but the worker agents need somewhere to be sent, and
# carrying it here keeps them from having to re-read the observations.
geometry_msgs/Point position

# Labels, following Figure 4
string LABEL_POSSIBLE_UAV=PossibleUAV
string LABEL_LIKELY_DRONE_LINK=LikelyDroneLink
string LABEL_CONFIRMED_AERIAL_OBJECT=ConfirmedAerialObject
string LABEL_CANDIDATE_TARGET=CandidateTarget
string LABEL_CONFIRMED_THREAT=ConfirmedThreat
