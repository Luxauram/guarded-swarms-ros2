cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_msgs)

find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Token.msg"
  "msg/GeometryToken.msg"
  "msg/AuthToken.msg"
  DEPENDENCIES std_msgs
)

ament_package()
