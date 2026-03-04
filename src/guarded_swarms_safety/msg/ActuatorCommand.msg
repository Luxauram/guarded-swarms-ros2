# ActuatorCommand.msg
#
# Actuator command issued by the coordinator after token approval.
#
# This message flows through the SafetyBoard before reaching the Gazebo
# actuators. The SafetyBoard intercepts each instance, evaluates it against
# the current sensor snapshot, and either forwards it with safety_cleared
# set to true or replaces it with a zero-thrust veto command.
#
# Pipeline:
#   [coordinator_node] -> /actuator_cmd_raw -> [safety_board_node] -> /actuator_cmd_safe

# Identifier of the agent or coordinator that issued this command.
string source_id

# Identifier of the AuthToken that authorized this command.
string auth_token_id

# Identifier of the target robot (e.g. "uav_1", "ugv_1").
string robot_id

# Normalized thrust command in the range [0.0, 1.0].
float32 thrust

# Attitude setpoints in degrees.
float32 pitch_cmd
float32 roll_cmd
float32 yaw_cmd

# Unix timestamp at command generation time, in microseconds.
int64 timestamp

# Cleared flag set by safety_board_node before forwarding to actuators.
# False on coordinator output; true only after SafetyBoard approval.
bool safety_cleared
