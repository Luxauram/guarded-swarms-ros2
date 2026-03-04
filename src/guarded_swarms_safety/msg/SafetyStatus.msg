# SafetyStatus.msg
#
# Safety evaluation result published by the SafetyBoard node.
#
# Reflects the outcome of all physical safety checks performed against
# the latest sensor snapshot. Published at a fixed rate on /safety_status
# for dashboard monitoring and incident logging.
#
# Evaluation policy: OR-logic. A single check failure sets is_safe to false
# and populates violation_reason with the first detected violation.

# Unix timestamp of this evaluation, in microseconds.
int64 timestamp

# Overall safety verdict.
# True if all checks passed; false if at least one violation was detected.
bool is_safe

# Per-check results. Any false value implies is_safe is false.
bool proximity_ok
bool attitude_ok
bool battery_ok
bool altitude_ok

# Human-readable description of the first violation detected.
# Empty string when is_safe is true.
string violation_reason

# Raw sensor values captured at evaluation time, included for logging
# and dashboard display.
float32 proximity_distance_m
float32 pitch_deg
float32 roll_deg
float32 battery_percent
float32 altitude_m
