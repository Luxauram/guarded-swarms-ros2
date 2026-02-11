# Authorization token - approval/rejection from coordinator

# Base token fields
Token base_token

# Reference to the geometry token being authorized
string geometry_token_id

# Authorization decision
bool approved

# Coordinator ID that made the decision
string coordinator_id

# Reason for decision (e.g., "approved", "conflict_detected", "expired")
string reason
