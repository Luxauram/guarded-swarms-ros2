# Geometry token - defines spatial area request

# Base token fields
Token base_token

# Requested geometry (simplified as bounding box)
# Position: center point [x, y, z] in meters
float32[3] position

# Dimensions: [width, height, depth] in meters
float32[3] dimensions

# Duration: how long agent needs this area (seconds)
float32 duration
