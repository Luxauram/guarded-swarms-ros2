# SupervisorAuth - human authorisation to release a mission
#
# Governed action release: no mission is executed without an authorisation
# from a supervisor.
#
# Issued by a human supervisor (through the console) to authorise, or by its
# absence to withhold, the interception of a specific target. The
# mission-release transition (T6) fires only when a ConfirmedThreat for the
# target and an authorisation for the same target are valid at the same time,
# each within its own ttl_s. No authorisation, no mission: this is the
# human-in-the-loop.

# The target this authorisation refers to. Must match the target_id of the
# ConfirmedThreat it is meant to release.
string target_id

# Identity of the supervisor issuing the authorisation. Carried into the
# MissionToken.authorised_by field, so every dispatched mission records who
# authorised it. Never empty for a genuine authorisation.
string authorised_by

# The decision. AUTHORISE releases the mission; DENY is an explicit refusal,
# recorded for audit rather than merely being the absence of a token.
string decision

# Simulated time the decision was taken.
builtin_interfaces/Time t

# Validity window in seconds. An authorisation is not open-ended: T6 releases a
# mission only while both the authorisation and a ConfirmedThreat for the same
# target are valid, so a stale authorisation cannot release a mission against
# an expired threat.
float64 ttl_s

string DECISION_AUTHORISE=authorise
string DECISION_DENY=deny
