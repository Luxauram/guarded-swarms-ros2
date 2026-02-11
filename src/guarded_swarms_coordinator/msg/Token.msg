# Base token message for Guarded Swarms coordination

# Unique token identifier
string token_id

# Timestamp when token was created
int64 timestamp

# Agent ID that created this token
string agent_id

# Token type: "geometry" or "authorization"
string token_type

# Digital signature (simulated - SHA256 hash)
string signature
