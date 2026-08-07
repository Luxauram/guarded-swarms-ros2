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
#
# Token, GeometryToken and AuthToken are LEGACY (the pre-TB-CSPN coordinator's
# types); still generated because legacy nodes and tests reference them, to be
# removed together with that layer. See LEGACY_REMOVAL_PLAN.
# ============================================================================
rosidl_generate_interfaces(${PROJECT_NAME}
  # -- Live: TB-CSPN + coordination --
  "msg/ObsToken.msg"
  "msg/InterpToken.msg"
  "msg/MissionToken.msg"
  "msg/SupervisorAuth.msg"
  "msg/VehicleTask.msg"
  # -- Legacy: to remove with the old coordinator --
  "msg/Token.msg"
  "msg/GeometryToken.msg"
  "msg/AuthToken.msg"
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces
)

ament_package()