cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_msgs)

# ============================================================================
# Dependencies
# ============================================================================
find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

# ============================================================================
# Message generation
#
# The TB-CSPN pipeline tokens (ObsToken -> InterpToken -> MissionToken) plus
# the human authorisation (SupervisorAuth) and dispatched work (VehicleTask).
# ============================================================================
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ObsToken.msg"
  "msg/InterpToken.msg"
  "msg/MissionToken.msg"
  "msg/SupervisorAuth.msg"
  "msg/VehicleTask.msg"
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces
)

ament_package()