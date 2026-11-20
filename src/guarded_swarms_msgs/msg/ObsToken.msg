# ObsToken - raw sensor observation
#
# Structure:  ObsToken = <id, value, source, confidence, t, ttl>
#
# Emitted by a consultant agent when its modality registers something. It
# carries no interpretation: an ObsToken states that a sensor saw a value, not
# what that value means. Meaning is assigned by the transitions that consume it
# and produce an InterpToken.
#
# SIMULATION NOTE
# ---------------
# In this digital twin the observations are synthesised by the consultant
# agents from the intruder's ground-truth odometry, with per-modality range,
# latency, noise and confidence models. Real detection and data association are
# out of scope: target_id is therefore known to the emitting agent rather than
# inferred, which keeps the focus on coordination instead of on tracking. This
# is a limitation of the simulation, not of the architecture.

# Unique identifier of this observation, used as the provenance handle that
# InterpToken.origin refers back to.
string id

# Which target this observation belongs to. Empty when the modality cannot
# attribute the observation to a specific target.
string target_id

# Emitting modality. Use the SOURCE_* constants.
string source

# Shape of the payload in `value`. Use the KIND_* constants. Modalities carry
# different physical quantities, so the payload is generic and this field says
# how to read it.
string kind

# Payload, interpreted according to `kind`:
#   KIND_TRACK      x, y, z, vx, vy, vz   world ENU, metres and metres/second
#   KIND_BEARING    bearing_rad, elevation_rad, range_m   sensor frame
#   KIND_SIGNATURE  centre_freq_hz, bandwidth_hz, rssi_dbm
#   KIND_VISUAL     x, y, z   world ENU, metres
float64[] value

# Detection confidence in [0, 1], as reported by the modality.
float64 confidence

# Simulated time of the observation. Every node in this layer runs with
# use_sim_time: the real-time factor is below 1, so wall-clock stamps would
# make latency figures incomparable between runs.
builtin_interfaces/Time t

# Validity window in seconds. An observation older than this is expired and
# must not take part in a synchronisation window.
float64 ttl_s

# Emitting modalities
string SOURCE_RADAR=radar
string SOURCE_RF=rf
string SOURCE_ACOUSTIC=acoustic
string SOURCE_EO=eo

# Payload shapes
string KIND_TRACK=track
string KIND_BEARING=bearing
string KIND_SIGNATURE=signature
string KIND_VISUAL=visual
