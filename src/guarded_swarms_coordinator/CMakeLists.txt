cmake_minimum_required(VERSION 3.8)
project(guarded_swarms_coordinator)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Token.msg"
  "msg/GeometryToken.msg"
  "msg/AuthToken.msg"
  DEPENDENCIES std_msgs
)

# ============================================================================
# Install
# ============================================================================
install(PROGRAMS
  ${PROJECT_NAME}/agent_node.py
  ${PROJECT_NAME}/coordinator_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch/
  DESTINATION share/${PROJECT_NAME}/launch
  OPTIONAL
)

# ============================================================================
# Testing
# ============================================================================
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()

install(FILES
  ${PROJECT_NAME}/__init__.py
  ${PROJECT_NAME}/token.py
  ${PROJECT_NAME}/agent_node.py
  ${PROJECT_NAME}/coordinator_node.py
  DESTINATION local/lib/python3.10/dist-packages/${PROJECT_NAME}
)
