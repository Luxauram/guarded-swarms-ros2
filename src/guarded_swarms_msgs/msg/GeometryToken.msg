# Geometry token - defines spatial area request

# Base token fields
guarded_swarms_msgs/Token base_token

# Requested geometry (simplified as bounding box)
# Position: center point [x, y, z] in meters
float32[3] position

# Dimensions: [width, height, depth] in meters
float32[3] dimensions

# Duration: how long agent needs this area (seconds)
float32 duration

# Priority level (0=lowest, 10=emergency)
# 0-2: Training/Testing
# 3-4: Low priority routine
# 5-6: Normal operations
# 7-8: High priority surveillance
# 9-10: Emergency (SAR, medical)
uint8 priority
